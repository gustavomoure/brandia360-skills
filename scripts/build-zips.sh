#!/usr/bin/env bash
# Genera un .zip por skill en dist/ (formato para subir a claude.ai:
# cada zip contiene la carpeta <skill>/ con su SKILL.md en la raíz de esa carpeta).
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$RAIZ/dist"

command -v zip >/dev/null 2>&1 || { echo "Falta 'zip'. Instálalo (apt install zip / brew install zip)." >&2; exit 1; }

rm -rf "$DIST"
mkdir -p "$DIST"
cd "$RAIZ/skills"

n=0
for dir in */; do
  skill="${dir%/}"
  [ -f "$skill/SKILL.md" ] || { echo "Aviso: $skill no tiene SKILL.md, se omite" >&2; continue; }
  zip -qr "$DIST/$skill.zip" "$skill" -x '*/__pycache__/*' '*.pyc' '*/.DS_Store'
  echo "✔ dist/$skill.zip ($(du -h "$DIST/$skill.zip" | cut -f1))"
  n=$((n + 1))
done

echo "Listo: $n zip(s) en dist/"
