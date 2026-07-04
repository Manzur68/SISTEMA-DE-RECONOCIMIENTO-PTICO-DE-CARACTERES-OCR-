import { BookOpen, ChevronRight } from 'lucide-react';

export default function CursoCard({ curso, onClick }) {
  return (
    <button className="card curso-card" onClick={onClick}>
      <div className={`card-icon ${curso.color || 'green'}`}><BookOpen size={26} /></div>
      <div className="card-body">
        <h3>{curso.nombre}</h3>
        <p>Sección {curso.seccion} · {curso.periodo}</p>
        <span className={`docente-label ${curso.color || 'green'}`}>{curso.docente || 'Sin docente'}</span>
      </div>
      <ChevronRight className="chevron-icon" />
    </button>
  );
}
