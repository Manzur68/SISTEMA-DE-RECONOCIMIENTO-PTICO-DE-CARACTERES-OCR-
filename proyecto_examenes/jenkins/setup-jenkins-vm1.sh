#!/bin/bash
# jenkins/setup-jenkins-vm1.sh
# Instala dependencias dentro del contenedor Jenkins en VM1.
# Ejecutar UNA SOLA VEZ después de levantar Jenkins.
#
# Uso: bash ~/proyecto_examenes/jenkins/setup-jenkins-vm1.sh

set -e
echo "=== Instalando dependencias en el contenedor Jenkins (VM1) ==="

sudo docker exec jenkins bash -c "
    apt-get update -qq

    # Docker CLI — para ejecutar docker compose desde el pipeline
    apt-get install -y --no-install-recommends \
        docker.io \
        openssh-client \
        curl \
        python3 \
        python3-pip \
        tesseract-ocr \
        tesseract-ocr-spa \
        poppler-utils

    # Verificar
    docker --version
    python3 --version
    tesseract --version

    echo 'Dependencias instaladas correctamente en VM1'
"

echo ""
echo "=== Generando clave SSH para conectar con VM2 ==="
sudo docker exec jenkins bash -c "
    mkdir -p /root/.ssh
    if [ ! -f /root/.ssh/id_rsa ]; then
        ssh-keygen -t rsa -b 4096 -f /root/.ssh/id_rsa -N ''
        echo 'Clave SSH generada'
    else
        echo 'Clave SSH ya existe'
    fi
    echo ''
    echo '=== CLAVE PÚBLICA (copiar esta clave a VM2) ==='
    cat /root/.ssh/id_rsa.pub
    echo '================================================'
"

echo ""
echo "=== Panel web de Jenkins ==="
IP=$(hostname -I | awk '{print $1}')
echo "URL     : http://${IP}:8080"
echo ""
echo "Contraseña inicial:"
sudo docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
echo ""
