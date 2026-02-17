#!/usr/bin/env bash
set -euo pipefail
LEGACY_DIR="${1:-legacy}"
mkdir -p "$LEGACY_DIR"

shopt -s nullglob
moved=false
for f in *.html; do
  mv -f "$f" "$LEGACY_DIR/"
  moved=true
done
if [ "$moved" = true ]; then
  git add "$LEGACY_DIR" || true
fi
echo "Done. Now run: git add .gitattributes .gitignore && git commit -m 'chore(repo): hygiene (ignore builds, move legacy html)'"
