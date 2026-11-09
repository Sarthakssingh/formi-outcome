#!/usr/bin/env bash
# Replace this with your controller. Contract: ./run.sh <SIM_URL> runs until the scenario finishes.
set -euo pipefail
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"

export SIMULATOR_URL="$SIM_URL"
export PYTHONUTF8=1
export PYTHONUNBUFFERED=1

exec python -m controller.main
