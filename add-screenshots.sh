#!/usr/bin/env bash
# Copy the before/after contrast screenshots into gutils under stable names.
#
# Usage:
#   ./add-screenshots.sh                      # auto-picks the 2 newest ~/Desktop screenshots
#   ./add-screenshots.sh BEFORE.png AFTER.png # explicit paths
#
# Auto mode assumes the OLDER of the two newest files is the "before" shot.
# It prints what it picked before copying, so check the line before committing.

set -euo pipefail

DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/screenshots"

before=""
after=""

if [ "$#" -eq 2 ]; then
  before="$1"
  after="$2"
elif [ "$#" -eq 0 ]; then
  # Two newest images on the Desktop, oldest-first so before/after line up.
  # Avoids mapfile, which macOS bash 3.2 does not have.
  picks=()
  while IFS= read -r line; do
    [ -n "$line" ] && picks+=("$line")
  done < <(
    find "$HOME/Desktop" -maxdepth 1 \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
      -print0 2>/dev/null \
      | xargs -0 ls -t 2>/dev/null \
      | head -2 \
      | tail -r
  )
  if [ "${#picks[@]}" -ne 2 ]; then
    echo "error: expected 2 recent images in ~/Desktop, found ${#picks[@]}" >&2
    echo "       pass them explicitly: $0 BEFORE.png AFTER.png" >&2
    exit 1
  fi
  before="${picks[0]}"
  after="${picks[1]}"
else
  echo "usage: $0 [BEFORE AFTER]" >&2
  exit 1
fi

for f in "$before" "$after"; do
  if [ ! -f "$f" ]; then
    echo "error: not a file: $f" >&2
    exit 1
  fi
done

echo "before: $before"
echo "after:  $after"

mkdir -p "$DEST"
cp "$before" "$DEST/high-contrast-cb-before.png"
cp "$after" "$DEST/high-contrast-cb-after.png"

echo
echo "copied to $DEST/high-contrast-cb-{before,after}.png"
echo
echo "next: re-embed them in the guide, which does not use external assets"
echo "  python3 embed-images.py"
