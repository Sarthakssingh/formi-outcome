#!/usr/bin/env bash
# Runs on plain Python 3.10+ (deps in requirements.txt). No Docker needed.
# State is kept in controller.db, so a restart after a crash resumes where it stopped.
set -euo pipefail
cd "$(dirname "$0")"
SIM_URL="${1:?usage: ./run.sh <SIM_URL>}"
export SIMULATOR_URL="$SIM_URL"
export CONTROLLER_DB="${CONTROLLER_DB:-controller.db}"
exec python -m controller.main