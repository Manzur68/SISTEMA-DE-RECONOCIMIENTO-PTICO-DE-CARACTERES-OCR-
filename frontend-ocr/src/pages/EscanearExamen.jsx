import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { UploadCloud, Image as ImageIcon, CheckCircle } from 'lucide-react';
import AppHeader from '../components/AppHeader.jsx';
import { subirExamenMock } from '../services/api.js';

export default function EscanearExamen() {
  const { cursoId, solucionarioId } = useParams();
  const navigate  = useNavigate();
  const [alumnoId,     setAlumnoId]     = useState('');
  const [alumnoNombre, setAlumnoNombre] = useState('');
  const [archivo,  setArchivo]  = useState(null);
  const [preview,  setPreview]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [enviado,  setEnviado]  = useState(false);
  const [error,    setError]    = useState('');

  const seleccionarArchivo = (e) => {
    const file = e.target.files?.[0];
    setArchivo(file);
    setError('');
    if (file && file.type.startsWith('image/')) {
      setPreview(URL.createObjectURL(file));
    } else {
      setPreview(null);
    }
  };

  const procesar = async (e) => {
    e.preventDefault();
    setError('');
    if (!alumnoId.trim())     return setError('Ingresa el código del alumno');
    if (!alumnoNombre.trim()) return setError('Ingresa el nombre del alumno');
    if (!archivo)             return setError('Selecciona una imagen o PDF del examen');

    setLoading(true);
    try {
      await subirExamenMock({ cursoId, solucionarioId, alumnoId, alumnoNombre, archivo });
      setEnviado(true);
      setTimeout(() => navigate(`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`), 1500);
    } catch (err) {
      setError(err.message || 'Error al enviar el examen al backend');
    } finally {
      setLoading(false);
    }
  };

  if (enviado) {
    return (
      <main className="phone-shell">
        <AppHeader title="Escanear examen" backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`} />
        <section className="content" style={{ textAlign: 'center', paddingTop: 60 }}>
          <CheckCircle size={64} color="var(--green)" />
          <h2 style={{ marginTop: 16 }}>¡Examen enviado!</h2>
          <p style={{ color: 'var(--muted)' }}>Redirigiendo a la lista de exámenes...</p>
        </section>
      </main>
    );
  }

  return (
    <main className="phone-shell">
      <AppHeader
        title="Escanear examen"
        subtitle="Captura o carga el archivo del alumno"
        backTo={`/cursos/${cursoId}/solucionarios/${solucionarioId}/examenes`}
      />
      <section className="content">
        <form className="form-card" onSubmit={procesar}>
          <label>Código del alumno</label>
          <input
            value={alumnoId}
            onChange={(e) => setAlumnoId(e.target.value)}
            placeholder="Ej: 20230001"
          />

          <label>Nombre del alumno</label>
          <input
            value={alumnoNombre}
            onChange={(e) => setAlumnoNombre(e.target.value)}
            placeholder="Ej: Juan Pérez"
          />

          <label>Archivo del examen</label>
          <label className="upload-box">
            <UploadCloud size={34} />
            <strong>{archivo ? archivo.name : 'Subir imagen o PDF'}</strong>
            <span>JPG, PNG o PDF · También puedes usar la cámara</span>
            <input
              type="file"
              accept="image/*,.pdf"
              capture="environment"
              onChange={seleccionarArchivo}
              hidden
            />
          </label>

          {preview
            ? <img className="preview-img" src={preview} alt="Vista previa" />
            : <div className="preview-placeholder"><ImageIcon size={38} /> Vista previa del examen</div>
          }

          {error && <div className="error-box">{error}</div>}

          <button className="primary-button" disabled={loading}>
            {loading ? 'Enviando al backend OCR...' : 'Procesar examen'}
          </button>
        </form>
      </section>
    </main>
  );
}
