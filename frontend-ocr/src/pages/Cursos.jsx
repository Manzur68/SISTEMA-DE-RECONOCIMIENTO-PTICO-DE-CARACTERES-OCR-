import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import CursoCard from '../components/CursoCard.jsx';
import Modal from '../components/Modal.jsx';
import { getCursos, crearCurso, actualizarCurso, eliminarCurso } from '../services/api.js';

const COLORES = ['green','blue','orange','purple','red'];
const VACIO   = { nombre:'', seccion:'A', periodo:'2026-1', docente:'', color:'green' };

export default function Cursos() {
  const navigate = useNavigate();
  const [cursos,   setCursos]   = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState('');
  const [modal,    setModal]    = useState(null);   // null | 'crear' | 'editar'
  const [editando, setEditando] = useState(null);   // objeto curso siendo editado
  const [form,     setForm]     = useState(VACIO);
  const [saving,   setSaving]   = useState(false);
  const [formErr,  setFormErr]  = useState('');

  const cargar = async () => {
    setLoading(true); setError('');
    try { setCursos(await getCursos()); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { cargar(); }, []);

  const abrirCrear = () => { setForm(VACIO); setFormErr(''); setModal('crear'); };
  const abrirEditar = (c, e) => { e.stopPropagation(); setEditando(c); setForm({ nombre:c.nombre, seccion:c.seccion, periodo:c.periodo, docente:c.docente||'', color:c.color||'green' }); setFormErr(''); setModal('editar'); };
  const cerrar = () => { setModal(null); setEditando(null); };

  const guardar = async () => {
    if (!form.nombre.trim()) return setFormErr('El nombre es obligatorio');
    setSaving(true); setFormErr('');
    try {
      if (modal === 'crear') await crearCurso(form);
      else await actualizarCurso(editando.id, form);
      await cargar(); cerrar();
    } catch (e) { setFormErr(e.message); }
    finally { setSaving(false); }
  };

  const borrar = async (c, e) => {
    e.stopPropagation();
    if (!confirm(`¿Eliminar "${c.nombre}"? Esta acción no se puede deshacer.`)) return;
    try { await eliminarCurso(c.id); await cargar(); }
    catch (e) { setError(e.message); }
  };

  const f = (k) => (e) => setForm(p => ({ ...p, [k]: e.target.value }));

  return (
    <main className="phone-shell">
      <AppHeader title="Cursos" subtitle="Selecciona un curso para iniciar la jornada" />

      <section className="content">
        {error && <div className="error-box">{error}</div>}

        {loading
          ? <div className="loader">Cargando cursos...</div>
          : cursos.length === 0
            ? <div className="empty-box">No hay cursos. Crea el primero.</div>
            : cursos.map(curso => (
                <div key={curso.id} className="card-wrapper">
                  <CursoCard curso={curso} onClick={() => navigate(`/cursos/${curso.id}/solucionarios`)} />
                  <div className="card-actions">
                    <button className="action-btn edit"  onClick={(e) => abrirEditar(curso, e)}><Pencil size={15}/></button>
                    <button className="action-btn trash" onClick={(e) => borrar(curso, e)}><Trash2 size={15}/></button>
                  </div>
                </div>
              ))
        }

        <button className="fab-button" onClick={abrirCrear}>
          <Plus size={26} /> Nuevo curso
        </button>
      </section>

      {modal && (
        <Modal titulo={modal === 'crear' ? 'Nuevo curso' : 'Editar curso'} onClose={cerrar}>
          <div className="modal-form">
            <label>Nombre del curso *</label>
            <input placeholder="Ej: Biología General" value={form.nombre} onChange={f('nombre')} />

            <div className="form-row">
              <div>
                <label>Sección</label>
                <input placeholder="A" value={form.seccion} onChange={f('seccion')} />
              </div>
              <div>
                <label>Período</label>
                <input placeholder="2026-1" value={form.periodo} onChange={f('periodo')} />
              </div>
            </div>

            <label>Docente</label>
            <input placeholder="Ej: Prof. García" value={form.docente} onChange={f('docente')} />

            <label>Color</label>
            <div className="color-picker">
              {COLORES.map(c => (
                <button key={c} type="button"
                  className={`color-dot ${c} ${form.color === c ? 'active' : ''}`}
                  onClick={() => setForm(p => ({...p, color: c}))}
                />
              ))}
            </div>

            {formErr && <div className="error-box">{formErr}</div>}

            <div className="modal-actions">
              <button className="secondary-button" onClick={cerrar} disabled={saving}>Cancelar</button>
              <button className="primary-button"   onClick={guardar} disabled={saving}>
                {saving ? 'Guardando...' : modal === 'crear' ? 'Crear curso' : 'Guardar cambios'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}
