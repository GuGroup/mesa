# MLIP Structure Guard

## Purpose

Validate that an incoming POSCAR is safe to pass into the MLIP workflow without modifying the structure file.

## Position in MESA Pipeline

This protocol runs at the beginning of `TASK_MLIP_DFT_HANDOFF`, before UMA single-point or relaxation execution.

## Inputs

The protocol consumes a resolved POSCAR path and optional runtime context. The file should be readable text in VASP POSCAR format.

## Outputs

The protocol returns structured validation metadata with `status`, `safe_to_continue`, `checks`, `warnings`, `errors`, and parsed structure metadata such as atom count, element labels, cell volume, and minimum pair distance when available.

## Algorithm

1. Check that the POSCAR path exists and is a regular file.
2. Confirm the file is readable and non-empty.
3. Parse scale, lattice, element labels, atom counts, coordinate mode, and coordinates with the built-in parser.
4. Confirm positive atom count and positive cell volume.
5. Check valid element labels when the POSCAR provides them.
6. Check for obviously impossible interatomic distances.
7. If ASE is installed, parse the POSCAR with ASE and record ASE-derived atom count and volume.

## Dependencies

The built-in validation uses only the Python standard library. ASE is optional and used only as an additional parser check.

## Failure Modes

The guard fails for missing files, unreadable files, empty files, invalid lattice data, non-positive volume, invalid element symbols, zero or negative atom counts, missing coordinates, ASE parser failure when ASE is installed, or impossible interatomic distances.

## Example

```json
{
  "status": "pass",
  "safe_to_continue": true,
  "metadata": {
    "atom_count": 2,
    "elements": ["Si"],
    "cell_volume_A3": 160.103
  }
}
```

## Validation

Use the controller dry-run test with a minimal POSCAR. A valid structure should continue to qsub planning, while a missing or malformed POSCAR should return `status: failure`.

## Limitations

The built-in distance sanity check does not perform full periodic nearest-neighbor analysis. ASE should be installed in production environments for stronger parsing coverage.
