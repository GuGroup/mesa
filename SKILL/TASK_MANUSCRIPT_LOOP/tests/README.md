# Manuscript Loop Tests

The regression suite covers the CLI/data surface for workspace initialization,
MESA-output ingestion, validators, reviewer-issue merging, preservation rules,
and malformed fixture failures.

Run from the repository root:

```bash
python3 -m unittest discover -s mesa/SKILL/TASK_MANUSCRIPT_LOOP/tests -v
```
