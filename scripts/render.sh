#!/usr/bin/env bash
# Rebuild the full video from source: scenes -> concat -> soundtrack -> final MP4.
#
#   scripts/render.sh                 # cinematic soundtrack (default)
#   scripts/render.sh ambient         # ambient soundtrack
#   JOBS=4 scripts/render.sh          # render scenes in parallel
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STYLE="${1:-cinematic}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 2)}"
BUILD="$ROOT/build"
OUT="$BUILD/telecom-under-siege-$STYLE.mp4"

case "$STYLE" in
  cinematic|ambient) ;;
  *) echo "unknown style '$STYLE' (use cinematic or ambient)" >&2; exit 64 ;;
esac

mkdir -p "$BUILD"
cd "$BUILD"
log() { printf '\033[36m==>\033[0m %s\n' "$*"; }

log "Rendering 10 scenes with $JOBS parallel jobs"
mapfile -t SCENES < <(python3 -c "import sys; sys.path.insert(0, '$ROOT/video'); import make_video as m; print('\n'.join(n for n, _, _ in m.SCENES))")
printf '%s\n' "${SCENES[@]}" | xargs -P "$JOBS" -I{} python3 "$ROOT/video/make_video.py" {}

log "Joining scenes"
: > list.txt
for s in "${SCENES[@]}"; do echo "file 'out/$s.mp4'" >> list.txt; done
ffmpeg -y -loglevel error -f concat -safe 0 -i list.txt -c copy joined.mp4

log "Composing $STYLE soundtrack"
python3 "$ROOT/video/music_$STYLE.py" "music_$STYLE.wav"

log "Muxing audio (loudness-normalized to -14 LUFS)"
ffmpeg -y -loglevel error -i joined.mp4 -i "music_$STYLE.wav" -map 0:v -map 1:a -c:v copy \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11" -c:a aac -b:a 192k -ar 48000 -shortest "$OUT"

log "Done: $OUT ($(du -h "$OUT" | cut -f1))"
