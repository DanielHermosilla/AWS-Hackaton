#!/usr/bin/env bash
# build-webapp.sh — prepara la webapp integrada dentro del contexto de la Lambda.
#
# La webapp "fuente" (ya integrada con el login) vive en la raíz del repo, en
# ../../webapp. El Dockerfile de la Lambda espera encontrarla como ./webapp
# dentro de este directorio (deploy-aws/app/), porque Docker no puede copiar
# archivos de fuera del contexto de build.
#
# Este script copia la webapp aquí ANTES de ejecutar `sam build`.
# Debe ejecutarse desde deploy-aws/app/ (o vía la ruta del script).
#
#   cd deploy-aws/app && ./build-webapp.sh && sam build && sam deploy --guided
#
set -euo pipefail

# Directorio donde está este script (deploy-aws/app/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SRC="../../webapp"
DEST="./webapp"

if [ ! -d "$SRC" ]; then
  echo "ERROR: no se encuentra la webapp fuente en $SRC" >&2
  exit 1
fi

echo "Copiando webapp integrada: $SRC -> $DEST"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"
echo "Listo. Ahora ejecuta: sam build && sam deploy"
