# 📝 Sistema OCR para Evaluación de Pruebas de Respuesta Corta

Sistema de **Reconocimiento Óptico de Caracteres (OCR)** que automatiza la calificación de exámenes físicos de respuesta corta. Convierte una fotografía imperfecta de un examen (tomada con cualquier celular) en una nota digital, sin necesidad de que la institución invierta en tabletas, laptops o plataformas de examen 100% digitales.

> Proyecto desarrollado por estudiantes de la Facultad de Ingeniería Eléctrica y Electrónica (FIEE) — Universidad Nacional de Ingeniería (UNI).

---

## 📌 Tabla de contenidos

- [Motivación](#-motivación)
- [¿Qué hace el sistema?](#-qué-hace-el-sistema)
- [Arquitectura](#-arquitectura)
- [Stack tecnológico](#-stack-tecnológico)
- [Estructura del repositorio](#-estructura-del-repositorio)
- [Modelo de bases de datos](#-modelo-de-bases-de-datos)
- [Requisitos previos](#-requisitos-previos)
- [Instalación y despliegue](#-instalación-y-despliegue)
- [Configuración de red entre VMs](#-configuración-de-red-entre-vms)
- [Configuración del frontend](#-configuración-del-frontend)
- [CI/CD con Jenkins](#-cicd-con-jenkins)
- [Roadmap / Pendientes](#-roadmap--pendientes)
- [Equipo](#-equipo)
- [Documentación adicional](#-documentación-adicional)
- [Licencia](#-licencia)

---

## 💡 Motivación

En muchas escuelas, institutos y universidades el examen en papel sigue siendo la principal herramienta de evaluación, ya que no todas las instituciones cuentan con un dispositivo por alumno. Digitalizar esos exámenes con OCR genérico suele fallar ante sombras, hojas inclinadas o mala iluminación, obligando al docente a corregir todo a mano.

Este proyecto construye un puente entre el examen físico y la gestión digital de notas: el docente sigue evaluando en papel, pero el sistema se encarga de leer, calificar y exportar las notas automáticamente.

## ✅ ¿Qué hace el sistema?

1. El docente fotografía o escanea cada examen con su celular.
2. El sistema **corrige automáticamente** la perspectiva, el ruido y la iluminación de la imagen.
3. Extrae mediante **OCR (Tesseract)** la identificación del alumno y sus respuestas marcadas.
4. **Compara** las respuestas extraídas contra un solucionario cargado previamente.
5. **Calcula la nota** automáticamente y marca con alertas los casos de baja confianza de lectura para revisión manual.
6. **Exporta** un archivo Excel/CSV con todas las notas del salón listo para usar.

## 🏗️ Arquitectura

El sistema está diseñado como una arquitectura de **microservicios distribuidos en dos máquinas virtuales**, separando el procesamiento pesado de imágenes del resto de la lógica de negocio.

```
                         VM1 — Servidor principal                      VM2 — Servidor de OCR
                    ┌───────────────────────────────┐            ┌───────────────────────────┐
 Frontend ───POST──▶│  api_gateway (FastAPI)         │            │  ms_preprocesamiento       │
                    │        │                       │   AMQP     │  (OpenCV: rotación,        │
                    │        ▼                       │◀──────────▶│   binarización, ruido)     │
                    │  RabbitMQ  ──────────────────┐  │            │        │                   │
                    │  (colas de mensajería)       │  │            │        ▼                   │
                    │        │                     │  │            │  ms_ocr (Tesseract)        │
                    │        ▼                     ▼  │            └───────────────────────────┘
                    │  ms_calificacion   ms_reporte    │
                    │        │                │        │
                    │        ▼                ▼        │
                    │  bd_calificacion   bd_reporte     │
                    │  (Postgres)        (Postgres)     │
                    │  bd_gateway (Postgres)            │
                    └───────────────────────────────┘
```

- **VM1 (servidor principal):** `api_gateway`, `RabbitMQ`, `ms_calificacion`, `ms_reporte` y sus bases de datos PostgreSQL (una por servicio: `bd_gateway`, `bd_calificacion`, `bd_reporte`).
- **VM2 (servidor de OCR):** `ms_preprocesamiento` (OpenCV) y `ms_ocr` (Tesseract). No requiere IP fija ni puertos entrantes; solo necesita alcanzar el puerto `5672` de la VM1.
- Toda la comunicación entre VMs ocurre exclusivamente vía **RabbitMQ (AMQP)**, lo que desacopla los servicios: si la VM2 se cae, los mensajes quedan en cola hasta que vuelve a estar disponible.

**Flujo resumido:** `Frontend → api_gateway → cola_preprocesamiento → ms_preprocesamiento → cola_ocr → ms_ocr → cola_calificacion → ms_calificacion → (revisión manual si aplica) → cola_reporte → ms_reporte → Reporte final (PDF/Excel)`

> 📎 Los diagramas completos (BPMN AS-IS/TO-BE, WBS, arquitectura detallada y diagrama de secuencia) están disponibles en la documentación técnica del proyecto (`/docs`).

## 🛠️ Stack tecnológico

| Categoría | Tecnología |
|---|---|
| Backend / API | Python, FastAPI |
| Mensajería | RabbitMQ (AMQP) |
| Base de datos | PostgreSQL (una instancia por microservicio) |
| Visión por computadora | OpenCV |
| Motor OCR | Tesseract OCR |
| Contenedores | Docker, Docker Compose v2 |
| CI/CD | Jenkins (Master/Agent + Testcontainers) |
| Frontend | Vite + JS/TS (`frontend-ocr`) |

## 📂 Estructura del repositorio

```
proyecto_examenes/
├── vm1/                        # Servidor principal
│   ├── api_gateway.py
│   ├── ms_calificacion.py
│   ├── ms_reporte.py
│   ├── database.py
│   ├── rabbitmq_config.py
│   ├── init-db.sql
│   ├── requirements-vm1.txt
│   ├── Dockerfile.vm1
│   ├── docker-compose.vm1.yml
│   └── .env.vm1.example
│
├── vm2/                        # Servidor de OCR
│   ├── ms_preprocesamiento.py
│   ├── ms_ocr.py
│   ├── rabbitmq_config.py
│   ├── requirements-vm2.txt
│   ├── Dockerfile.vm2
│   ├── docker-compose.vm2.yml
│   └── .env.vm2.example
│
├── jenkins/                     # Pipeline de CI/CD
│   ├── docker-compose.jenkins.yml
│   ├── setup-jenkins-vm1.sh
│   └── setup-agent-vm2.sh
│
├── frontend-ocr/                 # Interfaz web
│   ├── vite.config.js
│   └── .env.example
│
└── docs/                        # Documentación técnica (WBS, BPMN, UML, arquitectura)
```

> ⚠️ Los archivos `.env.vm1` y `.env.vm2` **no se versionan**: deben crearse localmente a partir de sus respectivos `.example`.

## 🗄️ Modelo de bases de datos

| Base de datos | Usada por | Contenido |
|---|---|---|
| `bd_gateway` | `api_gateway` | Cursos, solucionarios |
| `bd_calificacion` | `ms_calificacion` | Exámenes, respuestas de alumnos |
| `bd_reporte` | `ms_reporte` | Reportes generados |

Cada microservicio tiene su propia base de datos (principio *database-per-service*); no hay acceso cruzado directo entre bases, toda comunicación entre servicios pasa por RabbitMQ.

## 📋 Requisitos previos

| Requisito | VM1 | VM2 |
|---|---|---|
| Docker Engine | Requiere | Requiere |
| Docker Compose v2 | Requiere | Requiere |
| Puertos abiertos | `8000`, `5672`, `15672` | — (solo sale, no recibe) |
| RAM mínima | 4 GB | 4 GB (Tesseract consume CPU/RAM) |
| Conectividad | VM2 debe alcanzar el puerto 5672 de VM1 | Debe alcanzar `VM1:5672` |

Instalar Docker en **ambas VMs**:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

Abrir puertos necesarios (**solo en VM1**):

```bash
sudo ufw allow 8000/tcp    # API Gateway
sudo ufw allow 5672/tcp    # RabbitMQ (AMQP) — VM2 debe poder llegar aquí
sudo ufw allow 15672/tcp   # Panel de administración RabbitMQ (opcional)
sudo ufw reload
```

## 🚀 Instalación y despliegue

Clonar el repositorio:

```bash
git clone <URL_DEL_REPOSITORIO>
cd proyecto_examenes
```

Crear los archivos de entorno a partir de las plantillas:

```bash
cp vm1/.env.vm1.example vm1/.env.vm1
cp vm2/.env.vm2.example vm2/.env.vm2
```

### Checklist de arranque completo

| Paso | VM | Comando | Verificación |
|---|---|---|---|
| 1 | VM1 | `docker compose -f docker-compose.vm1.yml up -d` | Esperar ~30s a que Postgres y RabbitMQ estén `healthy` |
| 2 | VM1 | `curl http://localhost:8000/health` | Confirmar status `"ok"` |
| 3 | VM2 | `docker compose -f docker-compose.vm2.yml up -d` | (requiere VM1 ya levantada y accesible) |
| 4 | VM2 | `docker logs ms_preprocesamiento_vm2` | Confirmar `"Conectado a RabbitMQ en <IP_VM1>:5672"` |
| 5 | Frontend | `npm run build && npx serve dist` (o `npm run dev`) | App disponible en el navegador |

## 🌐 Configuración de red entre VMs

La IP de la VM1 debe configurarse manualmente en **dos** lugares cada vez que cambie:

**1. `vm2/.env.vm2` (en VM2):**

```env
RABBITMQ_HOST=192.168.18.97   # ← IP real de VM1
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin123    # ← debe coincidir con .env.vm1
RABBITMQ_VHOST=/
```

**2. `frontend-ocr/.env` (o `.env.production`):**

```env
VITE_API_URL=http://192.168.18.97:8000   # ← IP real de VM1
```

## 🖥️ Configuración del frontend

El frontend puede ejecutarse en VM1, VM2 o cualquier tercera máquina (incluso el propio navegador del docente); solo necesita alcanzar el puerto `8000` de la VM1.

```bash
cd frontend-ocr
npm install
npm run build
npx serve dist -p 5173
```

Modo desarrollo con proxy (evita problemas de CORS): editar `vite.config.js` con la IP real de la VM1 y luego:

```bash
npm run dev
```

## 🔄 CI/CD con Jenkins

El pipeline se distribuye entre **Jenkins Master (VM1)** y **Jenkins Agent (VM2)**:

| Etapa | Corre en | Descripción |
|---|---|---|
| Stage 1: Checkout | VM1 | Descarga del código fuente |
| Stage 2: Tests VM1 | VM1 | Testcontainers (Postgres + RabbitMQ) |
| Stage 3: Tests VM2 | VM2 (agent) | Testcontainers (RabbitMQ + Tesseract real) |
| Stage 4: Deploy VM1 | VM1 | `docker compose` de VM1 |
| Stage 5: Deploy VM2 | VM2 (agent) | `docker compose` de VM2 |
| Stage 6: Tests E2E | VM1 | Pruebas HTTP contra `localhost:8000` |

Levantar Jenkins en VM1:

```bash
sudo docker compose -f jenkins/docker-compose.jenkins.yml up -d
bash jenkins/setup-jenkins-vm1.sh
```

Registrar VM2 como agente:

```bash
bash jenkins/setup-agent-vm2.sh "ssh-rsa AAAA... root@vm1"
```

Luego, desde el panel web de Jenkins (`http://<IP_VM1>:8080`), instalar los plugins sugeridos, crear el usuario administrador y registrar el nodo `vm2-agent` en **Manage Jenkins → Nodes**.

## 🗺️ Roadmap / Pendientes

- [ ] Diagramas UML (clases, casos de uso, secuencia detallada a nivel de código)
- [ ] Métricas de precisión y desempeño del OCR sobre exámenes reales
- [ ] Resultados de calibración del sistema
- [ ] Manual de usuario final para el docente

## 👥 Equipo

Proyecto desarrollado por estudiantes de la FIEE — UNI:

- Quino Sanchez Luis Eusebio
- Arteaga Choccare Fabrizzio Félix
- Vivian
- Rosado Silva Manzur Arturo

## 📚 Documentación adicional

La documentación técnica completa del proyecto (pitch, WBS, BPMN AS-IS/TO-BE, arquitectura detallada, modelo de datos y guía de despliegue extendida) se encuentra en la carpeta [`/docs`](./docs) del repositorio.

## 📄 Licencia

Proyecto académico desarrollado en el marco de un curso de la Facultad de Ingeniería Eléctrica y Electrónica (FIEE), Universidad Nacional de Ingeniería (UNI). Uso educativo.
