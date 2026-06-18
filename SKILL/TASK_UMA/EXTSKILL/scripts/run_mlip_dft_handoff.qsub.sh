#!/usr/bin/env bash
#PBS -N mesa_mlip_dft_handoff
#PBS -j oe

set -euo pipefail

if [ "$#" -lt 8 ]; then
  echo "Usage: $0 INPUT_POSCAR OUTPUT_POSCAR MODEL TASK DEVICE RELAX_TYPE FMAX STEPS" >&2
  exit 2
fi

INPUT_POSCAR="$1"
OUTPUT_POSCAR="$2"
MODEL="$3"
UMA_TASK="$4"
DEVICE="$5"
RELAX_TYPE="$6"
FMAX="$7"
STEPS="$8"

WORKDIR="${PBS_O_WORKDIR:-$(pwd)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "${WORKDIR}"
mkdir -p optimized results logs

SINGLEPOINT_INPUT="results/uma_singlepoint.input.json"
SINGLEPOINT_OUTPUT="results/uma_singlepoint.mesa_output.json"
RELAXATION_INPUT="results/uma_relaxation.input.json"
RELAXATION_OUTPUT="results/uma_relaxation.mesa_output.json"

cat > "${SINGLEPOINT_INPUT}" <<EOF
{
  "poscar_path": "${INPUT_POSCAR}",
  "mlip_settings": {
    "model": "${MODEL}",
    "task": "${UMA_TASK}",
    "device": "${DEVICE}"
  },
  "results_dir": "results",
  "dry_run": false
}
EOF

cat > "${RELAXATION_INPUT}" <<EOF
{
  "poscar_path": "${INPUT_POSCAR}",
  "output_poscar": "${OUTPUT_POSCAR}",
  "mlip_settings": {
    "model": "${MODEL}",
    "task": "${UMA_TASK}",
    "device": "${DEVICE}"
  },
  "relaxation_settings": {
    "relax_type": "${RELAX_TYPE}",
    "fmax": ${FMAX},
    "steps": ${STEPS}
  },
  "results_dir": "results",
  "logs_dir": "logs",
  "dry_run": false
}
EOF

"${PYTHON_BIN}" "${TASK_DIR}/EXTSKILL/uma_singlepoint_runner.py" \
  --input "${SINGLEPOINT_INPUT}" \
  --output "${SINGLEPOINT_OUTPUT}" \
  --workdir "${WORKDIR}" \
  --verbose > logs/uma_singlepoint.stdout.log 2> logs/uma_singlepoint.stderr.log

"${PYTHON_BIN}" "${TASK_DIR}/EXTSKILL/uma_relaxation_runner.py" \
  --input "${RELAXATION_INPUT}" \
  --output "${RELAXATION_OUTPUT}" \
  --workdir "${WORKDIR}" \
  --verbose > logs/uma_relaxation.stdout.log 2> logs/uma_relaxation.stderr.log
