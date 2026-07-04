#!/bin/bash
# setup-agent-vm2.sh — VERSIÓN CORREGIDA
# Prepara VM2 como agente Jenkins.
# Corrige el problema de PATH con pip y usa --prefer-binary
# para evitar errores de compilación en Python 3.14.
#
# Uso:
#   bash setup-agent-vm2.sh "ssh-rsa AAAA... root@jenkins"

set -e

CLAVE_PUBLICA="$1"

if [ -z "$CLAVE_PUBLICA" ]; then
    echo "ERROR: Debes pasar la clave pública de Jenkins como argumento."
    echo "Uso: bash setup-agent-vm2.sh \"ssh-rsa AAAA...\""
    exit 1
fi

echo "=== Preparando VM2 como agente Jenkins ==="

# ── 1. Dependencias del sistema ───────────────────────────────────────────
echo "--- Instalando dependencias del sistema..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    openjdk-17-jre \
    python3 \
    python3-pip \
    python3-venv \
    docker.io \
    tesseract-ocr \
    tesseract-ocr-spa \
    poppler-utils \
    git \
    gcc \
    g++ \
    build-essential

echo "Java     : $(java -version 2>&1 | head -1)"
echo "Python   : $(python3 --version)"
echo "Tesseract: $(tesseract --version 2>&1 | head -1)"

# ── 2. Agregar /home/USUARIO/.local/bin al PATH permanentemente ───────────
echo "--- Configurando PATH..."

# Agregar al .bashrc para sesiones interactivas
if ! grep -q ".local/bin" ~/.bashrc; then
    echo '' >> ~/.bashrc
    echo '# Agregar pip local al PATH' >> ~/.bashrc
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# Agregar al .profile para sesiones no interactivas (Jenkins SSH)
if ! grep -q ".local/bin" ~/.profile; then
    echo '' >> ~/.profile
    echo '# Agregar pip local al PATH' >> ~/.profile
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
fi

# Aplicar en la sesión actual
export PATH="$HOME/.local/bin:$PATH"
echo "PATH configurado: $PATH"

# ── 3. Entorno virtual Python (evita conflictos con Python del sistema) ───
echo "--- Creando entorno virtual Python en ~/venv-jenkins..."

python3 -m venv ~/venv-jenkins

# Activar el venv
source ~/venv-jenkins/bin/activate

echo "Python en venv: $(python --version)"
echo "pip en venv   : $(pip --version)"

# ── 4. Instalar dependencias Python dentro del venv ───────────────────────
echo "--- Instalando dependencias Python para tests (dentro del venv)..."

pip install --upgrade pip --quiet

pip install \
    "testcontainers[rabbitmq]" \
    pytest \
    pytest-timeout \
    pika \
    numpy \
    "opencv-python-headless" \
    pytesseract \
    Pillow \
    pdf2image \
    python-dotenv \
    --prefer-binary \
    --quiet

echo ""
echo "--- Verificando instalaciones dentro del venv..."
python -c "import testcontainers; print('testcontainers OK')"
python -c "import pytest;         print('pytest         OK')"
python -c "import pika;           print('pika           OK')"
python -c "import numpy;          print('numpy          OK')"
python -c "import cv2;            print('opencv         OK')"
python -c "import pytesseract;    print('pytesseract    OK')"
python -c "import PIL;            print('Pillow         OK')"
python -c "import pdf2image;      print('pdf2image      OK')"

deactivate

# ── 5. Script de activación automática del venv para Jenkins ──────────────
echo "--- Creando script wrapper para pytest..."

# Jenkins ejecutará este script en lugar de llamar pytest directamente
cat > ~/run-pytest-vm2.sh << 'WRAPPER'
#!/bin/bash
# Activa el venv y ejecuta pytest con los argumentos pasados
export PATH="$HOME/.local/bin:$PATH"
source ~/venv-jenkins/bin/activate
python -m pytest "$@"
WRAPPER

chmod +x ~/run-pytest-vm2.sh
echo "Script wrapper creado: ~/run-pytest-vm2.sh"

# ── 6. Directorio de trabajo del agente Jenkins ───────────────────────────
echo "--- Creando directorio de trabajo del agente..."
mkdir -p ~/jenkins-agent
echo "Directorio: $(realpath ~/jenkins-agent)"

# ── 7. Autorizar clave SSH de Jenkins ─────────────────────────────────────
echo "--- Autorizando clave SSH de Jenkins..."
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Evitar duplicados
if ! grep -qF "$CLAVE_PUBLICA" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "$CLAVE_PUBLICA" >> ~/.ssh/authorized_keys
    echo "Clave agregada correctamente"
else
    echo "Clave ya existía, no se duplicó"
fi

chmod 600 ~/.ssh/authorized_keys

# ── 8. Acceso a Docker ────────────────────────────────────────────────────
echo "--- Configurando acceso a Docker..."
sudo usermod -aG docker $USER
sudo systemctl enable docker
sudo systemctl start docker
echo "Usuario $USER agregado al grupo docker"

# ── 9. Verificación final ─────────────────────────────────────────────────
echo ""
echo "=== VERIFICACIÓN FINAL ==="
java -version 2>&1 | head -1
python3 --version
tesseract --version 2>&1 | head -1
docker --version
echo ""
echo "pytest disponible en venv:"
source ~/venv-jenkins/bin/activate && pytest --version && deactivate

echo ""
echo "=== VM2 lista como agente Jenkins ==="
echo ""
echo "Datos para registrar el agente en Jenkins (panel web VM1):"
echo "  IP de VM2              : $(hostname -I | awk '{print $1}')"
echo "  Usuario SSH            : $USER"
echo "  Directorio raíz        : $(realpath ~/jenkins-agent)"
echo "  Label del agente       : vm2-agent"
echo "  Venv para tests        : ~/venv-jenkins"
echo "  Wrapper pytest         : ~/run-pytest-vm2.sh"
echo ""
echo "IMPORTANTE:"
echo "  Ejecutar 'newgrp docker' o cerrar sesión para aplicar permisos Docker"
echo ""
