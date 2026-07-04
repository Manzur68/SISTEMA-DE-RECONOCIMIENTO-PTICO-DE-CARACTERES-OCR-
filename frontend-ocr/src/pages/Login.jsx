import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ScanLine, Wifi, WifiOff } from 'lucide-react';
import { loginMock } from '../services/api.js';

const API_URL = import.meta.env.VITE_API_URL || 'http://192.168.18.97:8000';

export default function Login() {
  const navigate = useNavigate();
  const [usuario,  setUsuario]  = useState('docente');
  const [password, setPassword] = useState('123456');
  const [error,    setError]    = useState('');
  const [loading,  setLoading]  = useState(false);

  const ingresar = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await loginMock({ usuario, password });
      localStorage.setItem('token',   res.token);
      localStorage.setItem('usuario', JSON.stringify(res.usuario));
      navigate('/cursos');
    } catch (err) {
      if (err.message.includes('fetch') || err.message.includes('Failed')) {
        setError(`No se pudo conectar al servidor (${API_URL}). Verifica que el backend esté corriendo.`);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="login-logo"><ScanLine size={42} /></div>
        <h1>OCR Scanner</h1>
        <p>Sistema de evaluación automática de exámenes</p>
        <form onSubmit={ingresar}>
          <label>Usuario</label>
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} placeholder="docente" />
          <label>Contraseña</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="123456" />
          {error && <div className="error-box">{error}</div>}
          <button className="primary-button" disabled={loading}>
            {loading ? 'Conectando al backend...' : 'Ingresar'}
          </button>
        </form>
        <small style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center', marginTop: 14 }}>
          <Wifi size={13} /> Conectado a: <code style={{ fontSize: 11 }}>{API_URL}</code>
        </small>
      </section>
    </main>
  );
}
