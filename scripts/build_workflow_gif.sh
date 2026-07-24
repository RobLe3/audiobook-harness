#!/usr/bin/env bash
# Build the README's local ASCII workflow GIF. Requires ImageMagick and a local
# monospace font; it never downloads media or models.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/docs/assets/audiobook-harness-workflow.gif"
FRAMES="$ROOT/docs/assets/workflow-frames"
BUILD="$ROOT/docs/assets/.workflow-gif-build"
FONT="${AUDIOBOOK_HARNESS_MONO_FONT:-}"
if [[ -z "$FONT" ]]; then
  for candidate in /System/Library/Fonts/Menlo.ttc /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf; do
    [[ -f "$candidate" ]] && FONT="$candidate" && break
  done
fi
[[ -n "$FONT" && -f "$FONT" ]] || { echo "Set AUDIOBOOK_HARNESS_MONO_FONT to a local monospaced font." >&2; exit 1; }
command -v magick >/dev/null || { echo "ImageMagick (magick) is required" >&2; exit 1; }
rm -rf "$BUILD"; mkdir -p "$BUILD"
index=0
for frame in "$FRAMES"/*.txt; do
  printf -v png '%s/%02d.png' "$BUILD" "$index"
  magick -size 960x540 "xc:#07111F" \
    -fill '#101827' -draw 'roundrectangle 20,24 940,516 18,18' \
    -fill '#D6E2EE' -font "$FONT" -pointsize 23 -interline-spacing 10 \
    -gravity northwest -annotate +48+58 "@$frame" \
    -strip "$png"
  index=$((index + 1))
done
magick -delay 180 -loop 0 "$BUILD"/*.png -layers Optimize "$OUT"
rm -rf "$BUILD"
printf 'Created %s\n' "$OUT"
