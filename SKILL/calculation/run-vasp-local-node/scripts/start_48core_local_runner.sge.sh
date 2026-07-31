#!/bin/bash
#$ -V
#$ -S /bin/bash
#$ -N mesa_vasp_local
#$ -q all.q
#$ -pe mpi_48 48
#$ -j Y
#$ -o $JOB_NAME.o$JOB_ID
#$ -cwd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${MESA_VASP_LOCAL_RUNNER:-${SCRIPT_DIR}/vasp_local_node_runner.py}"
QUEUE_DIR="${MESA_VASP_LOCAL_QUEUE_DIR:-${PWD}}"
EXECUTABLE="${MESA_VASP_EXECUTABLE:-std}"
MIN_CORES="${MESA_VASP_MIN_CORES:-40}"
MAX_CORES="${MESA_VASP_MAX_CORES:-40}"
MODULE_NAME="${MESA_VASP_MODULE:-vasp/6.3.2-vtst-vaspsol-beef-intel}"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

if command -v module >/dev/null 2>&1 && [[ -n "${MODULE_NAME}" && "${MODULE_NAME}" != "none" ]]; then
  module load "${MODULE_NAME}"
fi

echo "Starting MESA VASP local node runner at $(date -Is)"
echo "Host: $(hostname)"
echo "Queue directory: ${QUEUE_DIR}"
echo "NSLOTS: ${NSLOTS:-unset}"
echo "VASP MPI ranks: ${MAX_CORES}"
echo "VASP executable family: ${EXECUTABLE}"
if [[ -n "${TMPDIR:-}" && -f "${TMPDIR}/machines" ]]; then
  echo "Machinefile: ${TMPDIR}/machines"
  cat "${TMPDIR}/machines"
fi

python3 "${RUNNER}" watch "${QUEUE_DIR}" \
  --min-cores "${MIN_CORES}" \
  --max-cores "${MAX_CORES}" \
  --executable "${EXECUTABLE}" \
  ${MESA_VASP_LOCAL_EXTRA_ARGS:-}
