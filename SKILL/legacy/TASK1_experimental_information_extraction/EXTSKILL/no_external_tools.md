# No External Tools

## Purpose

Document and expose a no-op external wrapper for TASK1.

## Position in MESA Pipeline

This wrapper belongs to TASK1 and confirms that experimental information extraction can run without external services.

## Inputs

Any JSON-serializable dictionary.

## Outputs

The standard MESA skill output dictionary with `status: skipped` and a message explaining that no external call was needed.

## Algorithm

1. Accept the input dictionary and optional context.
2. Return a skipped result.
3. Record no external calls in provenance.

## Dependencies

Only the Python standard library is required.

## Failure Modes

This wrapper should not fail for normal JSON-serializable inputs. Unexpected exceptions are returned in the standard `errors` field.

## Example

Input:

```json
{"raw_text": "NiCoO2 catalyst experiment"}
```

Output:

```json
{"status": "skipped", "task_id": "TASK1", "skill": "no_external_tools"}
```

## Validation

Run the module directly or call `run({})` from Python.

## Limitations

This wrapper does not call any external service or enrich the input data.

