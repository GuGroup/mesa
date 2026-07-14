#!/bin/bash
#$ -V
#$ -S /bin/bash
#$ -N {{ job_name }}
#$ -q 64core.q
#$ -pe mpi_64 64
#$ -j Y
#$ -o $JOB_NAME.o$JOB_ID
#$ -cwd

###### don't touch below #####
echo "Got $NSLOTS slots."
cat $TMPDIR/machines
export OMP_NUM_THREADS=1
##############################
cd $SGE_O_WORKDIR

module load vasp/6.3.2-vtst-vaspsol-beef-intel

mpirun -machinefile $TMPDIR/machines -n $NSLOTS vasp_std
exit_code=$?

date -Is > .vasp_submit_finished
printf '%s\n' "$exit_code" > .vasp_submit_exit_code

exit "$exit_code"
