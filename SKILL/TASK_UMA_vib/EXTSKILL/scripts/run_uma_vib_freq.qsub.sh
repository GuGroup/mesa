#!/bin/bash
#$ -V
#$ -S /bin/bash
#$ -cwd
#$ -N UMA_VIB_FREQ

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

mkdir -p results logs vib_cache

python "${TASK_DIR}/EXTSKILL/uma_vib_freq_runner.py" \
  > logs/uma_vib_freq.log \
  2>&1
