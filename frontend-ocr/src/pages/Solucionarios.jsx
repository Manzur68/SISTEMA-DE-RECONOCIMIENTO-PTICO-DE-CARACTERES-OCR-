import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Plus, Pencil, Trash2, ChevronDown, ChevronUp } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import SolucionarioCard from '../components/SolucionarioCard.jsx';
import Modal from '../components/Modal.jsx';
import {
  getCursoById, getSolucionariosPorCurso,
  crearSolucionario, actualizarSolucionario, eliminarSolucionario,
} from '../services/api.js';

const VACIO_SOL = { nombre:'', descripcion:'', puntajeTotal:20 };

export default function Solucionarios() {
  const { cursoId } = useParams();
  const navigate    = useNavigate();

  const [curso,         setCurso]         = useState(null);
  const [solucionarios, setSolucionarios] = useState([]);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState('');

  // Modal
  const [modal,    setModal]    = useState(null);   // null|'crear'|'editar'
  const [editando, setEditando] = useState(null);
  const [saving,   setSaving]   = useState(false);
  const [formErr,  setFormErr]  = useState('');

  // Formulario del solucionario
  const [form,     setForm]     = useState(VACIO_SOL);

  // Respuestas: array de { pregunta, respuesta, puntaje }
  const [respuestas, setRespuestas] = useState([{ pregunta:'1', respuesta:'', puntaje:'' }]);
  const [puntajeUniforme, setPuntajeUniforme] = useState(true);
  const [showRespuestas,  setShowRespuestas]  = useState(false);

  const cargar = async () => {
    setLoading(true); setError('');
    try {
      const [c, sols] = await Promise.all([getCursoById(cursoId), getSolucionariosPorCurso(cursoId)]);
      setCurso(c); setSolucionarios(sols);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { cargar(); }, [cursoId]);

  // ── helpers de respuestas ──────────────────────────────────────────────
  const agregarFila = () =>
    setRespuestas(r => [...r, { pregunta: String(r.length + 1), respuesta:'', puntaje:'' }]);

  const quitarFila = (i) =>
    setRespuestas(r => r.filter((_,j) => j !== i).map((x,j) => ({...x, pregunta: String(j+1)})));

  const actualizarFila = (i, campo, val) =>
    setRespuestas(r => r.map((x,j) => j === i ? {...x, [campo]: val} : x));

  const calcSumaActual = () =>
    respuestas.reduce((acc, r) => acc + (parseFloat(r.puntaje)||0), 0);

  // ── abrir modal ────────────────────────────────────────────────────────
  const abrirCrear = () => {
    setForm(VACIO_SOL);
    setRespuestas([{ pregunta:'1', respuesta:'', puntaje:'' }]);
    setPuntajeUniforme(true);
    setShowRespuestas(false);
    setFormErr(''); setModal('crear');
  };

  const abrirEditar = (s, e) => {
    e.stopPropagation();
    setEditando(s);
    setForm({ nombre: s.nombre, descripcion: s.descripcion||'', puntajeTotal: s.puntaje_total });
    // Reconstruir filas desde respuestas del solucionario
    const pi = s.puntajes_individuales || {};
    const filas = Object.entries(s.respuestas || {}).map(([num, resp]) => ({
      pregunta: num, respuesta: resp, puntaje: pi[num] !== undefined ? String(pi[num]) : ''
    }));
    setRespuestas(filas.length ? filas : [{ pregunta:'1', respuesta:'', puntaje:'' }]);
    setPuntajeUniforme(!Object.keys(pi).length);
    setShowRespuestas(true);
    setFormErr(''); setModal('editar');
  };

  const cerrar = () => { setModal(null); setEditando(null); };

  // ── guardar ────────────────────────────────────────────────────────────
  const guardar = async () => {
    if (!form.nombre.trim()) return setFormErr('El nombre es obligatorio');
    const totalPts = parseFloat(form.puntajeTotal);
    if (!totalPts || totalPts <= 0) return setFormErr('El puntaje total debe ser mayor a 0');

    // Construir objeto respuestas
    const respObj = {};
    for (const fila of respuestas) {
      if (!fila.pregunta || !fila.respuesta.trim()) return setFormErr(`Completa la respuesta de la pregunta ${fila.pregunta}`);
      respObj[fila.pregunta] = fila.respuesta.trim().toUpperCase();
    }

    // Puntajes individuales
    let puntajesInd = null;
    if (!puntajeUniforme) {
      puntajesInd = {};
      let suma = 0;
      for (const fila of respuestas) {
        const p = parseFloat(fila.puntaje);
        if (!p || p <= 0) return setFormErr(`Ingresa el puntaje de la pregunta ${fila.pregunta}`);
        puntajesInd[fila.pregunta] = p;
        suma += p;
      }
      if (Math.round(suma * 100) !== Math.round(totalPts * 100))
        return setFormErr(`La suma de puntajes (${suma.toFixed(1)}) debe ser igual al puntaje total (${totalPts})`);
    }

    setSaving(true); setFormErr('');
    try {
      const payload = {
        cursoId, nombre: form.nombre, descripcion: form.descripcion,
        respuestas: respObj, puntajeTotal: totalPts,
        ...(puntajesInd ? { puntajesIndividuales: puntajesInd } : {}),
      };
      if (modal === 'crear') await crearSolucionario(payload);
      else await actualizarSolucionario(editando.id, {
        nombre: form.nombre, descripcion: form.descripcion,
        respuestas: respObj, puntaje_total: totalPts,
        ...(puntajesInd ? { puntajes_individuales: puntajesInd } : { puntajes_individuales: null }),
      });
      await cargar(); cerrar();
    } catch (e) { setFormErr(e.message); }
    finally { setSaving(false); }
  };

  const borrar = async (s, e) => {
    e.stopPropagation();
    if (!confirm(`¿Eliminar "${s.nombre}"?`)) return;
    try { await eliminarSolucionario(s.id); await cargar(); }
    catch (e) { setError(e.message); }
  };

  const puntajeUniforme_val = respuestas.length ? (parseFloat(form.puntajeTotal)||0) / respuestas.length : 0;

  return (
    <main className="phone-shell">
      <AppHeader
        title="Solucionarios"
        subtitle={curso ? `${curso.nombre} · Sección ${curso.seccion}` : ''}
        backTo="/cursos"
      />

      <section className="content">
        {error && <div className="error-box">{error}</div>}

        {loading
          ? <div className="loader">Cargando solucionarios...</div>
          : solucionarios.length === 0
            ? <div className="empty-box">No hay solucionarios. Crea el primero.</div>
            : solucionarios.map(s => (
                <div key={s.id} className="card-wrapper">
                  <SolucionarioCard
                    solucionario={s}
                    onClick={() => navigate(`/cursos/${cursoId}/solucionarios/${s.id}/examenes`)}
                  />
                  <div className="card-actions">
                    <button className="action-btn edit"  onClick={(e) => abrirEditar(s, e)}><Pencil size={15}/></button>
                    <button className="action-btn trash" onClick={(e) => borrar(s, e)}><Trash2 size={15}/></button>
                  </div>
                </div>
              ))
        }

        <button className="fab-button" onClick={abrirCrear}>
          <Plus size={26}/> Nuevo solucionario
        </button>
      </section>

      {modal && (
        <Modal
          titulo={modal === 'crear' ? 'Nuevo solucionario' : 'Editar solucionario'}
          onClose={cerrar}
        >
          <div className="modal-form">
            <label>Nombre *</label>
            <input placeholder="Ej: Examen Parcial Biología" value={form.nombre}
              onChange={e => setForm(p=>({...p, nombre:e.target.value}))} />

            <label>Descripción</label>
            <input placeholder="Descripción opcional" value={form.descripcion}
              onChange={e => setForm(p=>({...p, descripcion:e.target.value}))} />

            <label>Puntaje total</label>
            <input type="number" min="1" placeholder="20" value={form.puntajeTotal}
              onChange={e => setForm(p=>({...p, puntajeTotal:e.target.value}))} />

            {/* Toggle puntaje uniforme vs individual */}
            <div className="toggle-row">
              <span>Puntaje por pregunta</span>
              <div className="toggle-group">
                <button type="button"
                  className={`toggle-btn ${puntajeUniforme ? 'active':''}`}
                  onClick={() => setPuntajeUniforme(true)}>
                  Uniforme {puntajeUniforme && respuestas.length ? `(${puntajeUniforme_val.toFixed(1)} c/u)` : ''}
                </button>
                <button type="button"
                  className={`toggle-btn ${!puntajeUniforme ? 'active':''}`}
                  onClick={() => setPuntajeUniforme(false)}>
                  Individual
                </button>
              </div>
            </div>

            {/* Tabla de respuestas */}
            <button type="button" className="collapse-btn"
              onClick={() => setShowRespuestas(v => !v)}>
              {showRespuestas ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
              Respuestas correctas ({respuestas.length} preguntas)
            </button>

            {showRespuestas && (
              <div className="respuestas-table">
                <div className="resp-header">
                  <span>#</span>
                  <span>Respuesta correcta</span>
                  {!puntajeUniforme && <span>Puntaje</span>}
                  <span></span>
                </div>
                {respuestas.map((fila, i) => (
                  <div key={i} className="resp-row">
                    <span className="resp-num">{fila.pregunta}</span>
                    <input
                      placeholder="A / texto"
                      value={fila.respuesta}
                      onChange={e => actualizarFila(i, 'respuesta', e.target.value)}
                    />
                    {!puntajeUniforme && (
                      <input
                        type="number" min="0.5" step="0.5"
                        placeholder="pts"
                        value={fila.puntaje}
                        onChange={e => actualizarFila(i, 'puntaje', e.target.value)}
                        className="pts-input"
                      />
                    )}
                    <button type="button" className="del-row-btn"
                      onClick={() => quitarFila(i)} disabled={respuestas.length <= 1}>
                      ×
                    </button>
                  </div>
                ))}

                <button type="button" className="add-row-btn" onClick={agregarFila}>
                  + Agregar pregunta
                </button>

                {!puntajeUniforme && (
                  <div className={`pts-sum ${Math.abs(calcSumaActual() - parseFloat(form.puntajeTotal||0)) < 0.01 ? 'ok':'bad'}`}>
                    Suma actual: {calcSumaActual().toFixed(1)} / {form.puntajeTotal || 0}
                  </div>
                )}
              </div>
            )}

            {!showRespuestas && (
              <div className="hint-box">
                Despliega "Respuestas correctas" para ingresar las alternativas del solucionario.
              </div>
            )}

            {formErr && <div className="error-box">{formErr}</div>}

            <div className="modal-actions">
              <button className="secondary-button" onClick={cerrar} disabled={saving}>Cancelar</button>
              <button className="primary-button" onClick={guardar} disabled={saving}>
                {saving ? 'Guardando...' : modal === 'crear' ? 'Crear' : 'Guardar'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}
