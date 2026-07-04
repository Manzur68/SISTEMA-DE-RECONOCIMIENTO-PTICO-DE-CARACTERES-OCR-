import { CheckCircle, Clock, AlertTriangle, Loader2 } from 'lucide-react';

const estadoConfig = {
  recibido          : { label: 'Recibido en servidor',      className: 'info',    icon: Clock        },
  preprocesando     : { label: 'Preprocesando imagen',      className: 'warning', icon: Loader2      },
  procesando_ocr    : { label: 'Detectando respuestas OCR', className: 'info',    icon: Loader2      },
  ocr_completado    : { label: 'OCR completado',            className: 'info',    icon: Clock        },
  pendiente_revision: { label: 'Pendiente revisión manual', className: 'danger',  icon: AlertTriangle },
  calificado        : { label: 'Calificado',                className: 'success', icon: CheckCircle  },
  revision_completa : { label: 'Revisión completa',         className: 'success', icon: CheckCircle  },
};

const enProceso = ['recibido', 'preprocesando', 'procesando_ocr', 'ocr_completado'];

// onRevisar se pasa desde RegistroExamenes con la ruta ya calculada
export default function ExamenCard({ examen, index, onRevisar }) {
  const cfg      = estadoConfig[examen.estado] || estadoConfig.recibido;
  const Icon     = cfg.icon;
  const procesando = enProceso.includes(examen.estado);

  return (
    <div className="exam-card">
      <div className="exam-number">{index + 1}</div>
      <div className="exam-main">

        <div className="exam-top">
          <div>
            <h3>{examen.alumno_id} — {examen.alumno_nombre}</h3>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>
              {examen.archivo_nombre}
            </p>
          </div>
          <div className="score-box">
            <span>Nota</span>
            <strong style={{
              color: examen.nota_final >= 10.5
                ? 'var(--green-dark)'
                : examen.nota_final != null
                  ? 'var(--danger)'
                  : undefined
            }}>
              {examen.nota_final != null ? examen.nota_final : '--'}/20
            </strong>
          </div>
        </div>

        <div className="exam-footer">
          <span className={`badge ${cfg.className}`}>
            <Icon
              size={15}
              style={procesando ? { animation: 'spin 1.2s linear infinite' } : {}}
            />
            {cfg.label}
          </span>
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            {examen.porcentaje_aciertos != null
              ? `${examen.porcentaje_aciertos}% aciertos`
              : procesando ? 'Procesando...' : ''}
          </span>
        </div>

        {examen.estado === 'pendiente_revision' && (
          <button className="revision-button" onClick={() => onRevisar(examen.id)}>
            <AlertTriangle size={15} />
            Revisar {examen.respuestas_pendientes} respuesta
            {examen.respuestas_pendientes !== 1 ? 's' : ''} pendiente
            {examen.respuestas_pendientes !== 1 ? 's' : ''}
          </button>
        )}
      </div>

      <style>{`
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        .revision-button {
          width: 100%; margin-top: 10px;
          background: #fff4e5; color: #9a5a00;
          border: 1.5px solid #f5c97a; border-radius: 12px;
          padding: 10px 14px; font-weight: 700; font-size: 13px;
          display: flex; align-items: center; gap: 8px;
          transition: background .15s; cursor: pointer;
        }
        .revision-button:hover { background: #ffebd0; }
      `}</style>
    </div>
  );
}
