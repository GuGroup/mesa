# Example prompts

## Slab relaxation with dry run

Prepare a VASP slab relaxation job from an input folder containing `POSCAR`. Use `structure.path: POSCAR`, use the slab defaults, keep metal smearing unless the structure clearly requires otherwise, run `vasp-job prepare` first, summarize the generated inputs, and submit only if they look valid.

```text
Input folder path here.
```

## Static calculation for an existing structure

Prepare a VASP static calculation from an existing input folder containing `POSCAR`. Use `structure.path: POSCAR`, use the static defaults, choose appropriate `ismear`, `sigma`, `ispin`, and `magmom` values from the structure context, dry-run the generated inputs, then submit the job.

```text
Input folder path here.
```

## Check a submitted job

Check the status of VASP job `<job_uid>`, show the stored metadata, and tell me whether it is still queued, running, finished, failed, or unknown.
