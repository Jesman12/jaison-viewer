#!/bin/bash

# 📌 Configuración
REPO_URL="https://github.com/Jesman12/jaison-viewer"  # Reemplaza con la URL de tu repo
LOCAL_DIR="./"                                        # Directorio del script en la Raspberry Pi
VERSION_FILE="version.txt"                            # Archivo que indica la versión
SCRIPT_NAME="reproductor.py"                          # Script principal

# 📌 Obtener la versión local
if [[ -f "$LOCAL_DIR/$VERSION_FILE" ]]; then
    LOCAL_VERSION=$(cat "$LOCAL_DIR/$VERSION_FILE")
else
    LOCAL_VERSION="0"
fi

# 📌 Obtener la última versión en GitHub
REMOTE_VERSION=$(curl -s "$REPO_URL/raw/main/$VERSION_FILE")

if [[ "$LOCAL_VERSION" != "$REMOTE_VERSION" ]]; then
    echo "Nueva versión disponible ($REMOTE_VERSION), actualizando..."
    
    # 📌 Respaldar la versión actual
    mv "$LOCAL_DIR" "${LOCAL_DIR}_backup_$(date +%Y%m%d%H%M%S)"

    # 📌 Descargar la nueva versión
    git clone "$REPO_URL" "$LOCAL_DIR"

    # 📌 Guardar la nueva versión
    echo "$REMOTE_VERSION" > "$LOCAL_DIR/$VERSION_FILE"
else
    echo "Ya tienes la última versión ($LOCAL_VERSION)"
fi

# 📌 Ejecutar el script principal
echo "Ejecutando $SCRIPT_NAME..."
python3 "$LOCAL_DIR/$SCRIPT_NAME"
