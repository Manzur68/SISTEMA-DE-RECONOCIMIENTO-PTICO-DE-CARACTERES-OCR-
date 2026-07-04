const esperar = (ms = 700) => new Promise((resolve) => setTimeout(resolve, ms));

const cursosMock = [
  { id: 1, nombre: 'Matemática I', seccion: 'A', periodo: '2026-1', docente: 'Prof. García', color: 'green' },
  { id: 2, nombre: 'Comunicación', seccion: 'B', periodo: '2026-1', docente: 'Prof. Ramos', color: 'blue' },
  { id: 3, nombre: 'Física General', seccion: 'C', periodo: '2026-1', docente: 'Prof. Torres', color: 'orange' },
];

const solucionariosMock = [
  { id: 1, curso_id: 1, nombre: 'Parcial Matemática I', descripcion: 'Evaluación de 5 preguntas', num_preguntas: 5, puntaje_total: 20 },
  { id: 2, curso_id: 1, nombre: 'Práctica Calificada 1', descripcion: 'Evaluación rápida', num_preguntas: 4, puntaje_total: 20 },
  { id: 3, curso_id: 2, nombre: 'Parcial Comunicación', descripcion: 'Comprensión lectora', num_preguntas: 5, puntaje_total: 20 },
  { id: 4, curso_id: 3, nombre: 'Práctica Física', descripcion: 'Problemas de cinemática', num_preguntas: 6, puntaje_total: 20 },
];

let examenesMock = [];

const cargarExamenes = () => {
  const data = localStorage.getItem('examenesMock');
  examenesMock = data ? JSON.parse(data) : [];
};

const guardarExamenes = () => {
  localStorage.setItem('examenesMock', JSON.stringify(examenesMock));
};

const generarNota = () => {
  const notas = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20];
  return notas[Math.floor(Math.random() * notas.length)];
};

const actualizarEstadoExamen = (examenId, nuevoEstado, extras = {}) => {
  cargarExamenes();
  examenesMock = examenesMock.map((e) =>
    e.id === Number(examenId) ? { ...e, estado: nuevoEstado, ...extras } : e
  );
  guardarExamenes();
};

export const loginMock = async ({ usuario, password }) => {
  await esperar(600);
  if (!usuario || !password) throw new Error('Ingresa usuario y contraseña');
  return {
    token: 'mock-token-ocr-123',
    usuario: { id: 1, nombre: usuario || 'Docente Demo', rol: 'docente' },
  };
};

export const getCursos = async () => {
  await esperar(500);
  return cursosMock;
};

export const getCursoById = async (cursoId) => {
  await esperar(300);
  return cursosMock.find((c) => c.id === Number(cursoId));
};

export const getSolucionariosPorCurso = async (cursoId) => {
  await esperar(600);
  return solucionariosMock.filter((s) => s.curso_id === Number(cursoId));
};

export const getSolucionarioById = async (solucionarioId) => {
  await esperar(300);
  return solucionariosMock.find((s) => s.id === Number(solucionarioId));
};

export const subirExamenMock = async ({ cursoId, solucionarioId, alumnoId, alumnoNombre, archivo }) => {
  await esperar(900);
  cargarExamenes();

  const examenId = Date.now();
  const nuevoExamen = {
    id: examenId,
    curso_id: Number(cursoId),
    solucionario_id: Number(solucionarioId),
    alumno_id: alumnoId,
    alumno_nombre: alumnoNombre,
    archivo_nombre: archivo?.name || 'examen.jpg',
    estado: 'preprocesando',
    nota_final: null,
    porcentaje_aciertos: null,
    respuestas_pendientes: 0,
    created_at: new Date().toISOString(),
  };

  examenesMock.push(nuevoExamen);
  guardarExamenes();

  setTimeout(() => actualizarEstadoExamen(examenId, 'procesando_ocr'), 1200);
  setTimeout(() => {
    const nota = generarNota();
    const pendientes = Math.random() > 0.75 ? 1 : 0;
    actualizarEstadoExamen(examenId, pendientes > 0 ? 'pendiente_revision' : 'calificado', {
      nota_final: pendientes > 0 ? null : nota,
      porcentaje_aciertos: pendientes > 0 ? null : Math.round((nota / 20) * 100),
      respuestas_pendientes: pendientes,
    });
  }, 2800);

  return { mensaje: 'Examen enviado al pipeline OCR.', examen: nuevoExamen };
};

export const getEstadoExamenMock = async (examenId) => {
  await esperar(300);
  cargarExamenes();
  const examen = examenesMock.find((e) => e.id === Number(examenId));
  if (!examen) throw new Error('Examen no encontrado');
  return examen;
};

export const getExamenesPorCurso = async (cursoId, solucionarioId) => {
  await esperar(400);
  cargarExamenes();
  return examenesMock.filter(
    (e) => e.curso_id === Number(cursoId) && e.solucionario_id === Number(solucionarioId)
  );
};

export const corregirPendienteMock = async (examenId) => {
  await esperar(700);
  const nota = generarNota();
  actualizarEstadoExamen(Number(examenId), 'calificado', {
    nota_final: nota,
    porcentaje_aciertos: Math.round((nota / 20) * 100),
    respuestas_pendientes: 0,
  });
  return { mensaje: 'Respuesta corregida manualmente.' };
};

export const getResumenFinal = async (cursoId, solucionarioId) => {
  await esperar(500);
  cargarExamenes();
  const examenes = examenesMock.filter(
    (e) => e.curso_id === Number(cursoId) && e.solucionario_id === Number(solucionarioId)
  );
  const calificados = examenes.filter((e) => e.nota_final !== null);
  const notas = calificados.map((e) => e.nota_final);
  const promedio = notas.length ? Number((notas.reduce((a, b) => a + b, 0) / notas.length).toFixed(2)) : null;

  return {
    total_examenes: examenes.length,
    calificados: calificados.length,
    pendientes_revision: examenes.filter((e) => e.estado === 'pendiente_revision').length,
    promedio_notas: promedio,
    aprobados: notas.filter((n) => n >= 10.5).length,
    desaprobados: notas.filter((n) => n < 10.5).length,
    detalle_alumnos: examenes,
  };
};

export const descargarCSV = (resumen) => {
  const filas = [
    ['Codigo alumno', 'Alumno', 'Estado', 'Nota', 'Porcentaje'],
    ...resumen.detalle_alumnos.map((e) => [
      e.alumno_id,
      e.alumno_nombre,
      e.estado,
      e.nota_final ?? 'Pendiente',
      e.porcentaje_aciertos ?? 'Pendiente',
    ]),
  ];
  const csv = filas.map((fila) => fila.map((x) => `"${String(x).replaceAll('"', '""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'reporte_examenes_ocr.csv';
  link.click();
  URL.revokeObjectURL(url);
};

export const limpiarMock = () => {
  examenesMock = [];
  localStorage.removeItem('examenesMock');
};
