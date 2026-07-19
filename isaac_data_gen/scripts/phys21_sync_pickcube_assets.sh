#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XTRAINER="$ROOT/external/x-trainer"
API_JSON="$ROOT/logs/phys21_asset_api/hf_model_api.json"
MIRROR_BASE="${HF_MIRROR_BASE:-https://hf-mirror.com/dstx123/xtrainer-leisaac/resolve/main}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/phys21_${STAMP}_sync_pickcube_assets"
LOG="$LOG_DIR/sync_assets.log"
DOWNLOAD_LIST="$LOG_DIR/download_list.txt"
ASSET_MANIFEST="$LOG_DIR/asset_manifest.txt"

mkdir -p "$LOG_DIR" "$ROOT/logs/phys21_asset_api"

exec > >(tee -a "$LOG") 2>&1

echo "[phys21] root=$ROOT"
echo "[phys21] xtrainer=$XTRAINER"
echo "[phys21] mirror=$MIRROR_BASE"

if [[ ! -d "$XTRAINER" ]]; then
  echo "[phys21][ERROR] missing external/x-trainer; run PHYS-2.0 first"
  exit 2
fi

if [[ ! -f "$API_JSON" ]]; then
  curl -L --connect-timeout 20 --max-time 120 \
    "https://hf-mirror.com/api/models/dstx123/xtrainer-leisaac" \
    -o "$API_JSON"
fi

python3 - "$API_JSON" "$MIRROR_BASE" "$DOWNLOAD_LIST" <<'PY'
import json
import sys
from pathlib import Path
from urllib.parse import quote

api_json, mirror_base, output = sys.argv[1:4]
data = json.loads(Path(api_json).read_text(encoding="utf-8"))
files = [s["rfilename"] for s in data.get("siblings", [])]
wanted = [
    f for f in files
    if f.startswith("assets/scenes/table_with_cube/")
    and "/.thumbs/" not in f
]
if not wanted:
    raise SystemExit("no table_with_cube assets found in model API")
with open(output, "w", encoding="utf-8") as out:
    out.write(f"# repo_sha {data.get('sha')}\n")
    for rel in sorted(wanted):
        url = mirror_base.rstrip("/") + "/" + quote(rel)
        out.write(f"{url}\t{rel}\n")
PY

echo "[phys21] download list:"
cat "$DOWNLOAD_LIST"

while IFS=$'\t' read -r url rel; do
  [[ -z "${url}" || "${url}" == \#* ]] && continue
  target="$XTRAINER/$rel"
  mkdir -p "$(dirname "$target")"
  if [[ -s "$target" ]]; then
    echo "[phys21] exists $rel"
    continue
  fi
  echo "[phys21] download $rel"
  curl -L --retry 3 --connect-timeout 20 --max-time 300 "$url" -o "$target"
done < "$DOWNLOAD_LIST"

required=(
  assets/robots/x_trainer.usd
  assets/robots/X-Trainer-URDF/urdf/x-trainer_asm-0226.SLDASM/x-trainer_asm-0226.SLDASM.usd
  assets/robots/X-Trainer-URDF/urdf/x-trainer_asm-0226.SLDASM/configuration/x-trainer_asm-0226.SLDASM_base.usd
  assets/robots/X-Trainer-URDF/urdf/x-trainer_asm-0226.SLDASM/configuration/x-trainer_asm-0226.SLDASM_physics.usd
  assets/robots/X-Trainer-URDF/urdf/x-trainer_asm-0226.SLDASM/configuration/x-trainer_asm-0226.SLDASM_sensor.usd
  assets/scenes/table_with_cube/scene.usd
  assets/scenes/table_with_cube/cube/cube.usd
  assets/scenes/table_with_cube/cube/collision/BuildingBlock003_Collider1_m.obj
  assets/scenes/table_with_cube/cube/visuals/BuildingBlock003.obj
  assets/scenes/table_with_cube/Plate/Plate.usd
  assets/scenes/table_with_cube/textures/light_wood_planks_0.png
)

for rel in "${required[@]}"; do
  if [[ ! -s "$XTRAINER/$rel" ]]; then
    echo "[phys21][ERROR] required asset missing or empty: $rel"
    exit 3
  fi
done

{
  echo "repo: dstx123/xtrainer-leisaac"
  echo "api: https://hf-mirror.com/api/models/dstx123/xtrainer-leisaac"
  python3 - "$API_JSON" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
print(f"repo_sha: {data.get('sha')}")
print(f"last_modified: {data.get('lastModified')}")
PY
  echo
  echo "assets:"
  find "$XTRAINER/assets/robots" "$XTRAINER/assets/scenes/table_with_cube" -type f -printf '%P\t%s bytes\n' | sort
  echo
  echo "sha256:"
  find "$XTRAINER/assets/robots" "$XTRAINER/assets/scenes/table_with_cube" -type f -print0 | sort -z | xargs -0 sha256sum
} > "$ASSET_MANIFEST"

touch "$LOG_DIR/PASS_PHYS21_PICKCUBE_ASSETS"
echo "[phys21] PASS assets"
echo "[phys21] manifest=$ASSET_MANIFEST"
