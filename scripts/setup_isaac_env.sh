#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT/isaac_data_gen"

echo "Creating and verifying Isaac/LeIsaac environment."
echo "This step requires conda, network access, NVIDIA GPU driver, and acceptance of NVIDIA Omniverse EULA."
echo "Existing conda env xtrainer_VLA is kept by default. Use RESET_XTRAINER_ENV=1 only when a full rebuild is intended."

bash scripts/create_fresh_conda_env.sh
bash scripts/install_stage2_isaacsim_pip.sh
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/verify_stage2_isaacsim.sh
bash scripts/install_stage3_isaaclab_source.sh
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/verify_stage3_isaaclab.sh
bash scripts/phys22_install_leisaac.sh
ACCEPT_NVIDIA_OMNIVERSE_EULA=YES bash scripts/phys22_verify_leisaac_registry.sh session_leisaac_registry

echo "Isaac/LeIsaac environment setup finished."
