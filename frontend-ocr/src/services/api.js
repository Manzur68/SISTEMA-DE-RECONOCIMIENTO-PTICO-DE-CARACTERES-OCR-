/**
 * api.js — Servicio completo conectado al backend real (VM1).
 * Cursos y Solucionarios se gestionan en la BD vía API.
 * Exámenes mantienen un índice local para mapear examen_id → curso+solucionario.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://192.168.18.97:8000';

// ─── HTTP helper ──────────────────────────────────────────────────────────
async function request(path, options = {}) {
  const headers = { ...options.headers };
  if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let msg = `Error ${res.status}`;
    try { const d = await res.json(); msg = d.detail || d.message || msg; } catch (_) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

const get    = (path)        => request(path, { method: 'GET' });
const post   = (path, body)  => request(path, { method: 'POST',   body: body instanceof FormData ? body : JSON.stringify(body) });
const patch  = (path, body)  => request(path, { method: 'PATCH',  body: JSON.stringify(body) });
const del    = (path)        => request(path, { method: 'DELETE' });

// ─── AUTH ─────────────────────────────────────────────────────────────────
export async function loginMock({ usuario, password }) {
  if (!usuario || !password) throw new Error('Ingresa usuario y contraseña');
  await get('/health');
  return { token: `ocr-session-${Date.now()}`, usuario: { id: 1, nombre: usuario, rol: 'docente' } };
}

// ─── CURSOS (backend real) ────────────────────────────────────────────────
export async function getCursos()             { return get('/cursos'); }
export async function getCursoById(id)        { return get(`/cursos/${id}`); }
export async function crearCurso(data)        { return post('/cursos', data); }
export async function actualizarCurso(id, d)  { return patch(`/cursos/${id}`, d); }
export async function eliminarCurso(id)       { return del(`/cursos/${id}`); }

// ─── SOLUCIONARIOS (backend real) ─────────────────────────────────────────
export async function getSolucionariosPorCurso(cursoId) {
  return get(`/cursos/${cursoId}/solucionarios`);
}
export async function getSolucionarioById(id) { return get(`/solucionarios/${id}`); }

export async function crearSolucionario({ cursoId, nombre, descripcion, respuestas, puntajeTotal, puntajesIndividuales }) {
  return post('/solucionario', {
    curso_id: Number(cursoId),
    nombre,
    descripcion,
    respuestas,
    puntaje_total: puntajeTotal,
    ...(puntajesIndividuales ? { puntajes_individuales: puntajesIndividuales } : {}),
  });
}

export async function actualizarSolucionario(id, data)  { return patch(`/solucionarios/${id}`, data); }
export async function eliminarSolucionario(id)          { return del(`/solucionarios/${id}`); }

// ─── EXÁMENES ─────────────────────────────────────────────────────────────
const EXAMEN_MAP_KEY = 'ocr_examen_map';
const getExamenMap   = () => { try { return JSON.parse(localStorage.getItem(EXAMEN_MAP_KEY) || '{}'); } catch { return {}; } };
const saveExamenMap  = (m) => localStorage.setItem(EXAMEN_MAP_KEY, JSON.stringify(m));

export async function subirExamenMock({ cursoId, solucionarioId, alumnoId, alumnoNombre, archivo }) {
  const form = new FormData();
  form.append('solucionario_id', solucionarioId);
  form.append('alumno_ids',      alumnoId);
  form.append('alumno_nombres',  alumnoNombre);
  form.append('archivos',        archivo, archivo.name);
  const res = await post('/examenes/subir', form);
  const e   = res.examenes_creados?.[0];
  if (!e) throw new Error('El backend no devolvió datos del examen');
  const map = getExamenMap();
  map[e.examen_id] = { curso_id: Number(cursoId), solucionario_id: Number(solucionarioId),
                       alumno_id: alumnoId, alumno_nombre: alumnoNombre,
                       archivo_nombre: archivo.name, created_at: new Date().toISOString() };
  saveExamenMap(map);
  return { mensaje: res.mensaje, examen: { id: e.examen_id, ...e } };
}

export async function getExamenesPorCurso(cursoId, solucionarioId) {
  const map = getExamenMap();
  const ids = Object.entries(map)
    .filter(([, v]) => v.curso_id === Number(cursoId) && v.solucionario_id === Number(solucionarioId))
    .map(([id]) => Number(id));
  if (!ids.length) return [];
  const resultados = await Promise.all(ids.map(async (examenId) => {
    try {
      const estado = await get(`/examenes/${examenId}/estado`);
      const meta   = map[examenId];
      return { id: examenId, ...meta, ...estado };
    } catch { return null; }
  }));
  return resultados.filter(Boolean);
}

// ─── REVISIÓN MANUAL ──────────────────────────────────────────────────────
export async function corregirPendienteMock(examenId) {
  const detalle    = await get(`/examenes/${examenId}/respuestas`);
  const pendientes = (detalle.respuestas || []).filter(r => r.estado === 'pendiente_revision');
  if (!pendientes.length) throw new Error('No hay respuestas pendientes');
  const p = pendientes[0];
  return patch(`/revision/${p.id}`, {
    respuesta_corregida: p.respuesta_ocr || p.respuesta_correcta || 'MANUAL',
    revisado_por: 'docente_app',
    observaciones: 'Corregido desde la app',
  });
}

export async function revisarRespuesta(id, { respuestaCorregida, revisadoPor, observaciones }) {
  return patch(`/revision/${id}`, { respuesta_corregida: respuestaCorregida,
                                    revisado_por: revisadoPor || 'docente_app', observaciones });
}

export async function getPendientesRevision() { return get('/revision/pendientes'); }

// ─── REPORTES ─────────────────────────────────────────────────────────────
export async function getResumenFinal(cursoId, solucionarioId) {
  const data = await get(`/reportes/solucionario/${solucionarioId}/directo`);
  return {
    total_examenes: data.total_examenes, calificados: data.calificados,
    pendientes_revision: data.pendientes_revision, promedio_notas: data.promedio_notas,
    aprobados: data.aprobados, desaprobados: data.desaprobados,
    detalle_alumnos: (data.detalle_alumnos || []).map(e => ({
      id: e.examen_id, alumno_id: e.alumno_id, alumno_nombre: e.alumno_nombre,
      estado: e.estado_examen, nota_final: e.nota_final,
      porcentaje_aciertos: e.porcentaje_aciertos, archivo_nombre: e.archivo_original || '',
    })),
  };
}

// ─── CSV ──────────────────────────────────────────────────────────────────
export function descargarCSV(resumen) {
  const filas = [['Codigo alumno','Alumno','Estado','Nota','Porcentaje'],
    ...resumen.detalle_alumnos.map(e => [e.alumno_id, e.alumno_nombre, e.estado,
      e.nota_final ?? 'Pendiente', e.porcentaje_aciertos != null ? `${e.porcentaje_aciertos}%` : 'Pendiente'])];
  const csv  = filas.map(f => f.map(x => `"${String(x).replaceAll('"','""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), { href: url, download: 'reporte_examenes_ocr.csv' });
  a.click(); URL.revokeObjectURL(url);
}

// ─── LIMPIEZA LOCAL ───────────────────────────────────────────────────────
export function limpiarMock() { localStorage.removeItem(EXAMEN_MAP_KEY); }
