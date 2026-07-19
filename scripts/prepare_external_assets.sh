#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Preparing official X-Trainer-LeIsaac source and PickCube assets..."
cd "$ROOT/isaac_data_gen"

bash scripts/phys20_prepare_xtrainer_upstream.sh
bash scripts/phys21_sync_pickcube_assets.sh

echo "External assets are ready under: $ROOT/isaac_data_gen/external"
