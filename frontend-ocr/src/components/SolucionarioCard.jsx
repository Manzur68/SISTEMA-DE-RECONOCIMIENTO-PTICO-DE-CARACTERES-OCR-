import { FileCheck, ChevronRight } from 'lucide-react';

export default function SolucionarioCard({ solucionario, onClick }) {
  const numPreg = solucionario.num_preguntas
    ?? (solucionario.respuestas ? Object.keys(solucionario.respuestas).length : 0);
  return (
    <button className="card solucionario-card" onClick={onClick}>
      <div className="card-icon green"><FileCheck size={26} /></div>
      <div className="card-body">
        <h3>{solucionario.nombre}</h3>
        <p>{solucionario.descripcion || 'Sin descripción'}</p>
        <span>{numPreg} pregunta{numPreg !== 1 ? 's' : ''} · {solucionario.puntaje_total} pts</span>
      </div>
      <ChevronRight className="chevron-icon" />
    </button>
  );
}
