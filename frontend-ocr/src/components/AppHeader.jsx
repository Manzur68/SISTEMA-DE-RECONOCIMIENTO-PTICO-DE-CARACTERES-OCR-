import { ArrowLeft, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function AppHeader({ title, subtitle, backTo, showLogout = true }) {
  const navigate = useNavigate();

  const logout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('usuario');
    navigate('/');
  };

  return (
    <header className="app-header">
      <div className="header-row">
        {backTo ? (
          <button className="icon-button" onClick={() => navigate(backTo)}><ArrowLeft size={22} /></button>
        ) : <div className="header-space" />}
        <div className="header-title-wrap">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {showLogout ? (
          <button className="icon-button" onClick={logout}><LogOut size={21} /></button>
        ) : <div className="header-space" />}
      </div>
    </header>
  );
}
