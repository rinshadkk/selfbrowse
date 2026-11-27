#!/usr/bin/env bash
# Turns the Python backend into a standalone folder (build/backend/selfbrowse-backend) that the packaged app runs.
# Optional packages are left out: the packaged app cannot pip install them. Presidio is a download (scripts/freeze-presidio.sh);
# Patchright stealth is not offered.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=backend/.venv/bin
[ -x "$PY/pyinstaller" ] || { echo "Run: $PY/pip install pyinstaller"; exit 1; }
rm -rf build/backend build/pyi
"$PY/pyinstaller" --noconfirm --clean --onedir --name selfbrowse-backend \
  --distpath build/backend --workpath build/pyi --specpath build --paths backend \
  --collect-all playwright --collect-submodules uvicorn --collect-submodules selfbrowse \
  --hidden-import live --hidden-import record --hidden-import flow_clean --hidden-import addons --hidden-import blocklists --hidden-import certifi \
  --add-data "$PWD/backend/addon_manifest.json:." \
  --add-data "$PWD/../docs/flows.md:." \
  --exclude-module patchright --exclude-module spacy --exclude-module thinc --exclude-module blis \
  --exclude-module numpy --exclude-module presidio_analyzer --exclude-module presidio_anonymizer \
  backend/server.py
# Patchright ships a PyInstaller hook that pulls itself back in (about 140 MB), so remove it after the fact.
rm -rf build/backend/selfbrowse-backend/_internal/patchright build/backend/selfbrowse-backend/_internal/patchright-*.dist-info
echo "Frozen backend: $(du -sh build/backend/selfbrowse-backend | cut -f1)"
