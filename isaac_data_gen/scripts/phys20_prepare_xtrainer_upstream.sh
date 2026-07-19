#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM_COMMIT="${XTRAINER_UPSTREAM_COMMIT:-5862c3ba4997ae0d4c41f69c73981353af3a8346}"
UPSTREAM_ZIP_URL="${XTRAINER_UPSTREAM_ZIP_URL:-https://github.com/embodied-dobot/x-trainer/archive/${UPSTREAM_COMMIT}.zip}"
SRC="${1:-}"
DEST="$ROOT/external/x-trainer"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/phys20_${STAMP}_prepare_xtrainer"
LOG="$LOG_DIR/prepare.log"

mkdir -p "$LOG_DIR" "$ROOT/external"

exec > >(tee -a "$LOG") 2>&1

echo "[phys20] root=$ROOT"
echo "[phys20] source=${SRC:-public archive ${UPSTREAM_ZIP_URL}}"
echo "[phys20] dest=$DEST"

if [[ -z "$SRC" ]]; then
  ARCHIVE="$ROOT/external/x-trainer-${UPSTREAM_COMMIT}.zip"
  EXTRACT_DIR="$ROOT/external/_xtrainer_extract"
  if [[ ! -s "$ARCHIVE" ]]; then
    curl -L --retry 3 --connect-timeout 20 --max-time 300 "$UPSTREAM_ZIP_URL" -o "$ARCHIVE"
  fi
  rm -rf "$EXTRACT_DIR"
  mkdir -p "$EXTRACT_DIR"
  python3 - "$ARCHIVE" "$EXTRACT_DIR" <<'PY'
import sys
import zipfile
archive, target = sys.argv[1:3]
with zipfile.ZipFile(archive) as zf:
    zf.extractall(target)
PY
  SRC="$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
else
  if [[ ! -d "$SRC" ]]; then
    echo "[phys20][ERROR] source directory not found: $SRC"
    exit 2
  fi
fi

for required in \
  README.md \
  source/leisaac/pyproject.toml \
  source/leisaac/leisaac/tasks/pick_cube/__init__.py \
  scripts/environments/teleoperation/teleop_se3_agent.py \
  scripts/convert/isaaclab2lerobot_xtrainer.py \
  assets/robots/x_trainer.usd
do
  if [[ ! -e "$SRC/$required" ]]; then
    echo "[phys20][ERROR] missing required upstream file: $required"
    exit 3
  fi
done

if [[ -e "$DEST" ]]; then
  echo "[phys20] destination already exists; not overwriting"
else
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude '/.git' --exclude '/checkpoints' "$SRC/" "$DEST/"
  else
    mkdir -p "$DEST"
    (cd "$SRC" && tar --exclude='./.git' --exclude='./checkpoints' -cf - .) | (cd "$DEST" && tar -xf -)
  fi
  echo "[phys20] copied upstream source"
fi

{
  echo "source_path: $SRC"
  echo "dest_path: $DEST"
  echo "upstream_commit: $UPSTREAM_COMMIT"
  echo "upstream_zip_url: $UPSTREAM_ZIP_URL"
  if [[ -n "${ARCHIVE-}" && -f "$ARCHIVE" ]]; then
    echo "archive_path: $ARCHIVE"
    echo "archive_sha256: $(sha256sum "$ARCHIVE" | awk '{print $1}')"
  else
    echo "archive_path: user_supplied_source"
  fi
  echo "source_note: fixed public embodied-dobot/x-trainer upstream"
  echo "copied_at: $(date -Iseconds)"
} > "$LOG_DIR/source_manifest.txt"

find "$DEST" -maxdepth 3 -type f | sed "s#^$DEST/##" | sort > "$LOG_DIR/file_manifest_depth3.txt"

touch "$LOG_DIR/PASS_PHYS20_XTRAINER_PREPARE"
echo "[phys20] PASS prepare"
echo "[phys20] log_dir=$LOG_DIR"
