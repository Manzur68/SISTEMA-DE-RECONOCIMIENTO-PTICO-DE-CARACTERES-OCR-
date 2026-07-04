import { Routes, Route, Navigate } from 'react-router-dom';
import Login            from './pages/Login.jsx';
import Cursos           from './pages/Cursos.jsx';
import Solucionarios    from './pages/Solucionarios.jsx';
import RegistroExamenes from './pages/RegistroExamenes.jsx';
import EscanearExamen   from './pages/EscanearExamen.jsx';
import RevisionManual   from './pages/RevisionManual.jsx';
import ResumenFinal     from './pages/ResumenFinal.jsx';

function PrivateRoute({ children }) {
  return localStorage.getItem('token') ? children : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />

      <Route path="/cursos" element={
        <PrivateRoute><Cursos /></PrivateRoute>
      } />

      <Route path="/cursos/:cursoId/solucionarios" element={
        <PrivateRoute><Solucionarios /></PrivateRoute>
      } />

      <Route path="/cursos/:cursoId/solucionarios/:solucionarioId/examenes" element={
        <PrivateRoute><RegistroExamenes /></PrivateRoute>
      } />

      <Route path="/cursos/:cursoId/solucionarios/:solucionarioId/escanear" element={
        <PrivateRoute><EscanearExamen /></PrivateRoute>
      } />

      <Route
        path="/cursos/:cursoId/solucionarios/:solucionarioId/examenes/:examenId/revision"
        element={<PrivateRoute><RevisionManual /></PrivateRoute>}
      />

      <Route path="/cursos/:cursoId/solucionarios/:solucionarioId/resumen" element={
        <PrivateRoute><ResumenFinal /></PrivateRoute>
      } />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
