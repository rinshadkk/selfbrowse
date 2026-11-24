#!/usr/bin/env bash
# Builds the Presidio add-on: Presidio + spaCy + the en_core_web_sm model frozen into one program, zipped for a
# GitHub release. The app downloads this file when someone presses Install next to Presidio.
# Needs a Python with presidio-analyzer, en_core_web_sm and pyinstaller (set PY=... to pick one).
# Prints the checksum and size to paste into backend/addon_manifest.json.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-backend/.venv/bin/python}
"$PY" -c "import presidio_analyzer, en_core_web_sm, PyInstaller" 2>/dev/null \
  || { echo "Needs presidio-analyzer, en_core_web_sm and pyinstaller in $PY"; exit 1; }
ZIP=build/presidio-addon-macos-arm64.zip
rm -rf build/addon build/pyi-addon "$ZIP"
"$PY" -m PyInstaller --noconfirm --clean --onedir --name presidio-sidecar \
  --distpath build/addon --workpath build/pyi-addon --specpath build \
  --collect-all presidio_analyzer --collect-all spacy --collect-all en_core_web_sm \
  --collect-data phonenumbers --collect-data tldextract \
  --exclude-module matplotlib --exclude-module tkinter --exclude-module pytest \
  backend/presidio_sidecar.py
( cd build/addon && zip -qry "../presidio-addon-macos-arm64.zip" presidio-sidecar )
echo "Add-on: $(du -sh build/addon/presidio-sidecar | cut -f1) unpacked, $(du -sh "$ZIP" | cut -f1) zipped"
echo "sha256: $(shasum -a 256 "$ZIP" | cut -d' ' -f1)"
echo "size:   $(stat -f%z "$ZIP" 2>/dev/null || stat -c%s "$ZIP")"
