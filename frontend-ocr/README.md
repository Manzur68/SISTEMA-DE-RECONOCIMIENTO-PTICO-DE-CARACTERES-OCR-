# OCR Scanner — Frontend

Aplicación React (Vite) para el sistema de evaluación automática de exámenes.
Conecta con el API Gateway del backend (VM1).

## Instalación

```bash
npm install
```

## Desarrollo (con proxy CORS)

```bash
# El proxy redirige /api → http://192.168.18.97:8000
npm run dev
# Abrir http://localhost:5173
```

## Producción (apunta directo al backend)

```bash
# Editar .env con la IP real del backend:
echo "VITE_API_URL=http://192.168.18.97:8000" > .env

npm run build
# Servir la carpeta dist/ con cualquier servidor estático
npx serve dist
```

## Variables de entorno

| Variable       | Descripción                              | Por defecto                    |
|----------------|------------------------------------------|--------------------------------|
| `VITE_API_URL` | URL completa del API Gateway (VM1)       | `http://192.168.18.97:8000`    |

## Flujo de pantallas

```
Login → Cursos → Solucionarios → RegistroExamenes ←→ EscanearExamen
                                        ↓
                                  ResumenFinal (CSV)
```

## Datos locales (localStorage)

El frontend guarda en localStorage:
- `ocr_examen_map`: mapeo examen_id → {curso_id, solucionario_id, alumno, archivo}
- `ocr_sol_curso_map`: mapeo solucionario_id → curso_id
- `ocr_cursos`: lista de cursos (editable)
- `token` / `usuario`: sesión activa

Los cursos se administran localmente (el backend no tiene entidad Curso).
Los solucionarios se crean directamente en el backend vía `POST /solucionario`.
