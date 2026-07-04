import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Download, FileText } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import { descargarCSV, getResumenFinal } from '../services/api.js';

export default function ResumenFinal() {
  const { cursoId, solucionarioId } = useParams();
  const navigate = useNavigate();
  const [resumen, setResumen] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getResumenFinal(cursoId, solucionarioId).then(setResumen).finally(() => setLoading(false));
  }, [cursoId, solucionarioId]);

  return (
    <main className="phone-shell">
      <AppHeader title="Resumen final" subtitle="Reporte de la jornada OCR" backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`} />
      <section className="content">
        {loading || !resumen ? <div className="loader">Generando resumen...</div> : (
          <>
            <div className="summary-hero">
              <FileText size={42} />
              <h2>Reporte generado</h2>
              <p>Promedio: <strong>{resumen.promedio_notas ?? '--'}</strong></p>
            </div>

            <div className="summary-grid">
              <div><span>Total</span><strong>{resumen.total_examenes}</strong></div>
              <div><span>Calificados</span><strong>{resumen.calificados}</strong></div>
              <div><span>Aprobados</span><strong>{resumen.aprobados}</strong></div>
              <div><span>Desaprobados</span><strong>{resumen.desaprobados}</strong></div>
              <div><span>Pendientes</span><strong>{resumen.pendientes_revision}</strong></div>
              <div><span>Promedio</span><strong>{resumen.promedio_notas ?? '--'}</strong></div>
            </div>

            <button className="download-button" onClick={() => descargarCSV(resumen)}>
              <Download size={22} /> Descargar CSV
            </button>

            <button className="secondary-button full" onClick={() => navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`)}>
              Volver a registros
            </button>
          </>
        )}
      </section>
    </main>
  );
}
