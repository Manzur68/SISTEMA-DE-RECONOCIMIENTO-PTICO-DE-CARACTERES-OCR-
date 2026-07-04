import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { CheckCircle, XCircle, AlertTriangle, ChevronRight } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import { revisarRespuesta } from '../services/api.js';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://192.168.18.97:8000';

export default function RevisionManual() {
  const { cursoId, solucionarioId, examenId } = useParams();
  const navigate = useNavigate();

  const [respuestas,  setRespuestas]  = useState([]);
  const [alumno,      setAlumno]      = useState(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState('');
  const [indice,      setIndice]      = useState(0);       // pregunta actual
  const [valorInput,  setValorInput]  = useState('');
  const [guardando,   setGuardando]   = useState(false);
  const [guardado,    setGuardado]    = useState(false);   // feedback visual
  const [notaFinal,   setNotaFinal]   = useState(null);

  // Cargar respuestas pendientes del examen
  useEffect(() => {
    const cargar = async () => {
      setLoading(true); setError('');
      try {
        const res = await fetch(`${BASE_URL}/examenes/${examenId}/respuestas`);
        if (!res.ok) throw new Error(`Error ${res.status}`);
        const data = await res.json();
        setAlumno({ id: data.alumno_id, nombre: data.alumno_nombre });
        setNotaFinal(data.nota_final);

        // Solo mostrar pendientes de revisión
        const pendientes = (data.respuestas || []).filter(
          r => r.estado === 'pendiente_revision'
        );
        setRespuestas(pendientes);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    cargar();
  }, [examenId]);

  // Al cambiar de pregunta, limpiar el input
  useEffect(() => {
    setValorInput('');
    setGuardado(false);
  }, [indice]);

  const respuestaActual = respuestas[indice];
  const esUltima        = indice === respuestas.length - 1;
  const esAlternativa   = !respuestaActual?.respuesta_correcta ||
                          respuestaActual.respuesta_correcta.length <= 1;

  const guardar = async () => {
    if (!valorInput.trim()) return;
    setGuardando(true); setError('');
    try {
      const resultado = await revisarRespuesta(respuestaActual.id, {
        respuestaCorregida: valorInput.trim(),
        revisadoPor       : 'docente_app',
        observaciones     : `Corregido manualmente. OCR extrajo: "${respuestaActual.respuesta_ocr}"`,
      });

      setGuardado(true);
      if (resultado.nota_final_examen != null) {
        setNotaFinal(resultado.nota_final_examen);
      }

      // Avanzar a la siguiente o terminar
      setTimeout(() => {
        if (esUltima) {
          navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`);
        } else {
          setIndice(i => i + 1);
        }
      }, 800);
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="phone-shell">
        <AppHeader
          title="Revisión Manual"
          backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`}
        />
        <div className="loader" style={{ marginTop: 60 }}>Cargando respuestas...</div>
      </main>
    );
  }

  if (respuestas.length === 0) {
    return (
      <main className="phone-shell">
        <AppHeader
          title="Revisión Manual"
          backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`}
        />
        <section className="content" style={{ textAlign: 'center', paddingTop: 60 }}>
          <CheckCircle size={64} color="var(--green)" />
          <h2 style={{ marginTop: 16 }}>Sin pendientes</h2>
          <p style={{ color: 'var(--muted)', marginTop: 8 }}>
            Este examen no tiene respuestas pendientes de revisión.
          </p>
          <button
            className="primary-button"
            style={{ marginTop: 32 }}
            onClick={() => navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`)}
          >
            Volver a exámenes
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="phone-shell">
      <AppHeader
        title="Revisión Manual"
        subtitle={alumno ? `${alumno.id} — ${alumno.nombre}` : ''}
        backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`}
      />

      <section className="content">

        {/* Progreso */}
        <div className="revision-progress">
          <span>{indice + 1} de {respuestas.length} pendiente{respuestas.length !== 1 ? 's' : ''}</span>
          <div className="progress-dots">
            {respuestas.map((_, i) => (
              <span
                key={i}
                className={`progress-dot ${i < indice ? 'done' : i === indice ? 'active' : ''}`}
              />
            ))}
          </div>
        </div>

        {/* Tarjeta de la pregunta */}
        {respuestaActual && (
          <div className="revision-card">

            {/* Número de pregunta */}
            <div className="revision-num-row">
              <div className="revision-badge">
                <AlertTriangle size={14} />
                Pregunta {respuestaActual.numero_pregunta}
              </div>
              <span className="conf-label">
                Confianza OCR: {respuestaActual.confianza_ocr != null
                  ? `${(respuestaActual.confianza_ocr * 100).toFixed(0)}%`
                  : 'N/D'}
              </span>
            </div>

            {/* Lo que leyó el OCR */}
            <div className="ocr-section">
              <label>Texto extraído por OCR</label>
              <div className="ocr-text">
                {respuestaActual.respuesta_ocr
                  ? `"${respuestaActual.respuesta_ocr}"`
                  : <em style={{ color: 'var(--muted)' }}>OCR no pudo leer nada</em>}
              </div>
            </div>

            {/* Respuesta correcta según solucionario */}
            <div className="correct-section">
              <label>Respuesta correcta (solucionario)</label>
              <div className="correct-text">
                {respuestaActual.respuesta_correcta || '—'}
              </div>
            </div>

            {/* Separador */}
            <hr className="revision-divider" />

            {/* Input de corrección */}
            <label className="input-label">
              Ingresa la respuesta del alumno
            </label>

            {esAlternativa ? (
              /* Alternativas A B C D */
              <div className="alt-grid">
                {['A', 'B', 'C', 'D'].map(letra => (
                  <button
                    key={letra}
                    type="button"
                    className={`alt-btn ${valorInput.toUpperCase() === letra ? 'selected' : ''}`}
                    onClick={() => setValorInput(letra)}
                    disabled={guardando || guardado}
                  >
                    {letra}
                  </button>
                ))}
              </div>
            ) : (
              /* Texto libre */
              <textarea
                className="revision-textarea"
                placeholder="Escribe la respuesta del alumno tal como aparece en el examen..."
                value={valorInput}
                onChange={e => setValorInput(e.target.value)}
                rows={4}
                disabled={guardando || guardado}
              />
            )}

            {error && <div className="error-box">{error}</div>}

            {/* Botón guardar */}
            <button
              className={`primary-button revision-save-btn ${guardado ? 'saved' : ''}`}
              onClick={guardar}
              disabled={!valorInput.trim() || guardando || guardado}
            >
              {guardado
                ? <><CheckCircle size={18} /> Guardado</>
                : guardando
                  ? 'Guardando...'
                  : esUltima
                    ? 'Guardar y finalizar'
                    : 'Guardar y continuar'}
            </button>

          </div>
        )}

        {/* Nota actualizada */}
        {notaFinal != null && (
          <div className="nota-preview">
            <span>Nota actual del examen</span>
            <strong style={{ color: notaFinal >= 10.5 ? 'var(--green-dark)' : 'var(--danger)' }}>
              {notaFinal}/20
            </strong>
          </div>
        )}

      </section>

      <style>{`
        .revision-progress {
          display: flex; align-items: center; justify-content: space-between;
          margin-bottom: 16px;
          font-size: 13px; color: var(--muted); font-weight: 600;
        }
        .progress-dots { display: flex; gap: 6px; }
        .progress-dot {
          width: 10px; height: 10px; border-radius: 50%;
          background: #dde3de; transition: background .2s;
        }
        .progress-dot.active { background: var(--green); }
        .progress-dot.done   { background: var(--green-dark); }

        .revision-card {
          background: white; border-radius: 20px;
          padding: 20px; display: grid; gap: 14px;
          box-shadow: 0 2px 12px rgba(0,0,0,.08);
        }

        .revision-num-row {
          display: flex; align-items: center; justify-content: space-between;
        }
        .revision-badge {
          display: flex; align-items: center; gap: 6px;
          background: #fff4e5; color: #9a5a00;
          padding: 5px 12px; border-radius: 20px;
          font-size: 13px; font-weight: 700;
        }
        .conf-label { font-size: 12px; color: var(--muted); }

        .ocr-section label, .correct-section label, .input-label {
          font-size: 12px; font-weight: 700; color: var(--muted);
          text-transform: uppercase; letter-spacing: .05em;
        }
        .ocr-text {
          background: #f8f8f8; border-radius: 12px; padding: 12px 14px;
          font-size: 14px; color: var(--text); font-style: italic;
          border-left: 3px solid #dde3de; margin-top: 4px;
          word-break: break-word;
        }
        .correct-text {
          background: #edfbf3; border-radius: 12px; padding: 12px 14px;
          font-size: 14px; color: var(--green-dark); font-weight: 600;
          border-left: 3px solid var(--green); margin-top: 4px;
          word-break: break-word;
        }

        .revision-divider {
          border: none; border-top: 1px solid #eee; margin: 0;
        }

        /* Grilla A B C D */
        .alt-grid {
          display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
        }
        .alt-btn {
          height: 56px; border-radius: 14px; border: 2px solid #dde3de;
          font-size: 22px; font-weight: 900; color: var(--text);
          background: #f8f8f8; transition: all .15s;
        }
        .alt-btn:hover:not(:disabled) { border-color: var(--green); background: #f0fbf5; }
        .alt-btn.selected {
          border-color: var(--green); background: var(--green);
          color: white; transform: scale(1.05);
        }
        .alt-btn:disabled { opacity: .5; }

        /* Textarea texto libre */
        .revision-textarea {
          width: 100%; border-radius: 14px; border: 1.5px solid #dde3de;
          padding: 12px 14px; font-size: 14px; resize: none;
          font-family: inherit; line-height: 1.6;
        }
        .revision-textarea:focus { border-color: var(--green); outline: none; }

        .revision-save-btn {
          display: flex; align-items: center; justify-content: center; gap: 8px;
          transition: background .2s;
        }
        .revision-save-btn.saved { background: var(--green-dark); }
        .revision-save-btn:disabled:not(.saved) { opacity: .5; }

        .nota-preview {
          display: flex; align-items: center; justify-content: space-between;
          background: white; border-radius: 16px; padding: 16px 20px;
          margin-top: 12px; font-size: 14px; color: var(--muted);
          box-shadow: 0 2px 8px rgba(0,0,0,.06);
        }
        .nota-preview strong { font-size: 22px; }
      `}</style>
    </main>
  );
}
