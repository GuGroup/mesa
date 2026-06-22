#!/usr/bin/env bash

set -euo pipefail

WORKDIR="${PBS_O_WORKDIR:-${SGE_O_WORKDIR:-$(pwd)}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${WORKDIR}"
mkdir -p relaxed results logs

CONFIG_PATH="results/resolved_uma_config.json"
OUTPUT_PATH="results/uma_relax_traj.mesa_output.json"
LOG_PATH="logs/uma_relax_traj.log"

if [ ! -s "${CONFIG_PATH}" ]; then
  echo "Missing required controller config: ${CONFIG_PATH}" > "${LOG_PATH}"
  exit 2
fi

"${PYTHON_BIN}" "${TASK_DIR}/EXTSKILL/uma_relax_traj_runner.py" \
  --config "${CONFIG_PATH}" \
  --output "${OUTPUT_PATH}" \
  --workdir "${WORKDIR}" \
  --verbose > "${LOG_PATH}" 2>&1
