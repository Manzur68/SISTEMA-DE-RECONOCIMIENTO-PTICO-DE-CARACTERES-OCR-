import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Camera, Trash2, RefreshCw } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import ExamenCard from '../components/ExamenCard.jsx';
import {
  getCursoById,
  getExamenesPorCurso,
  getSolucionarioById,
  limpiarMock,
} from '../services/api.js';

const POLL_INTERVAL = 3000;

export default function RegistroExamenes() {
  const { cursoId, solucionarioId } = useParams();
  const navigate = useNavigate();

  const [curso,        setCurso]        = useState(null);
  const [solucionario, setSolucionario] = useState(null);
  const [examenes,     setExamenes]     = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [error,        setError]        = useState('');
  const intervalRef = useRef(null);

  const cargar = async (silencioso = false) => {
    if (!silencioso) setLoading(true);
    setError('');
    try {
      const [cursoData, solData, exs] = await Promise.all([
        getCursoById(cursoId),
        getSolucionarioById(solucionarioId),
        getExamenesPorCurso(cursoId, solucionarioId),
      ]);
      setCurso(cursoData);
      setSolucionario(solData);
      setExamenes(exs);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargar();
    intervalRef.current = setInterval(() => cargar(true), POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [cursoId, solucionarioId]);

  const irARevision = (examenId) => {
    navigate(
      `/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes/${examenId}/revision`
    );
  };

  const borrarTodo = () => {
    if (!confirm('¿Limpiar todos los exámenes registrados en este dispositivo?')) return;
    limpiarMock();
    setExamenes([]);
  };

  const hayProcesando = examenes.some(
    e => ['preprocesando', 'procesando_ocr', 'recibido'].includes(e.estado)
  );

  return (
    <main className="phone-shell green-shell">
      <AppHeader
        title="Registros de Exámenes"
        subtitle={curso && solucionario ? `${curso.nombre} · ${solucionario.nombre}` : ''}
        backTo={`/cursos/${cursoId}/solucionarios`}
      />

      <section className="scan-action-section">
        <button
          className="scan-button"
          onClick={() => navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/escanear`)}
        >
          <Camera size={30} />
          ESCANEAR EXAMEN
        </button>
      </section>

      <section className="content list-content">
        <div className="list-title-row">
          <h2>
            Lista de exámenes
            {hayProcesando && (
              <RefreshCw
                size={14}
                style={{ marginLeft: 8, verticalAlign: 'middle', animation: 'spin 1.5s linear infinite' }}
              />
            )}
          </h2>
          <button className="link-button" onClick={borrarTodo}>
            <Trash2 size={16} /> Limpiar
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        {loading ? (
          <div className="loader">Cargando exámenes...</div>
        ) : examenes.length === 0 ? (
          <div className="empty-box">
            Aún no hay exámenes escaneados.<br />
            Presiona "ESCANEAR EXAMEN" para comenzar.
          </div>
        ) : (
          examenes.map((examen, index) => (
            <ExamenCard
              key={examen.id}
              examen={examen}
              index={index}
              onRevisar={irARevision}
            />
          ))
        )}
      </section>

      <footer className="bottom-bar">
        <button
          className="secondary-button"
          onClick={() => navigate(`/cursos/${cursoId}/solucionarios`)}
        >
          Atrás
        </button>
        <button
          className="primary-button"
          onClick={() => navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/resumen`)}
        >
          Ver resumen
        </button>
      </footer>

      <style>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>
    </main>
  );
}
