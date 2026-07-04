-- ─────────────────────────────────────────────
-- init-db.sql
-- Script de inicialización de PostgreSQL.
-- Se ejecuta automáticamente la primera vez que
-- se crea el contenedor de postgres.
-- ─────────────────────────────────────────────

-- Crear extensiones útiles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";    -- Para UUIDs
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- Para búsqueda de texto similar

-- Configurar zona horaria del servidor
SET timezone = 'America/Lima';

-- Comentario en la base de datos
COMMENT ON DATABASE bd_calificacion IS 
    'Base de datos del Sistema de Evaluación Automática de Exámenes - Proyecto Distribucido VM1';

-- Las tablas son creadas por SQLAlchemy (init_db() en database.py)
-- Este script solo configura el entorno inicial de PostgreSQL.
