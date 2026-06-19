# No External Tools

## Purpose

Document that TASK2 does not require external tools for its current reaction CSV evaluation workflow.

## Position in MESA Pipeline

This wrapper sits alongside the TASK2 internal skill and provides a stable EXTSKILL placeholder for future external parsers or databases.

## Inputs

Any JSON-serializable dictionary.

## Outputs

A standard MESA skill output dictionary indicating that no external call was required.

## Algorithm

1. Accept input data.
2. Record that no external calls were made.
3. Return `status: skipped`.

## Dependencies

Python standard library only.

## Failure Modes

No expected failure modes beyond non-dictionary input.

## Example

Input:

```json
{"reason": "standard-library evaluation only"}
```

Output:

```json
{"status": "skipped", "task_id": "TASK2"}
```

## Validation

Call `run({})` and confirm that `provenance.external_calls` is empty.

## Limitations

This wrapper does not call or validate any external program.
