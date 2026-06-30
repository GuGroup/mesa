# Experimental Information Extraction

## Purpose

Extract structured scientific information from raw experimental notes, optional metadata, and researcher hypotheses.

## Position in MESA Pipeline

This skill is TASK1 in the MESA workflow. It receives the initial experimental information and prepares normalized context for literature search, VASP input planning, and later comparison with calculation results.

## Inputs

The input is a JSON-serializable dictionary. Supported fields include:

- `experiment_id`: Optional experiment identifier.
- `raw_text`: Free-text experimental description.
- `materials`: Optional list of material names, formulas, or catalyst labels.
- `measurements`: Optional list of measurement dictionaries.
- `hypotheses`: Optional list of researcher hypotheses as strings or dictionaries.
- `conditions`: Optional dictionary of experimental conditions.
- `targets`: Optional list of target properties or outcomes.

## Outputs

The skill returns the standard MESA output dictionary. The `data` field contains:

- `experiment_id`
- `raw_text_summary`
- `materials`
- `measurements`
- `conditions`
- `hypotheses`
- `targets`
- `keywords`
- `uncertainties`
- `extraction_quality`

## Algorithm

1. Validate that `input_data` is a dictionary.
2. Read raw text and optional structured fields.
3. Normalize material labels from structured input and simple formula-like patterns in text.
4. Normalize measurement dictionaries and extract simple numeric unit expressions from text.
5. Normalize hypotheses into stable records with IDs and evidence fields.
6. Preserve explicit conditions and targets.
7. Record uncertainties for missing or ambiguous fields.
8. Return the standard MESA skill output with provenance.

## Dependencies

Only the Python standard library is required.

## Failure Modes

- Non-dictionary input returns `status: failure`.
- Non-JSON-serializable values are converted to strings where possible.
- Missing raw text is allowed when structured fields are present, but the output records an uncertainty.
- Unexpected exceptions are reported in the `errors` field.

## Example

Input:

```json
{
  "experiment_id": "EXP-001",
  "raw_text": "NiCoO2 showed 0.20 V overpotential for nitrate reduction to ammonia in 1 M KOH.",
  "hypotheses": ["Ni-Co synergy lowers the nitrate activation barrier."]
}
```

Output data includes normalized material labels, extracted measurements, hypotheses, keywords, and uncertainties.

## Validation

Run:

```bash
python SKILL/TASK1_experimental_information_extraction/MYSKILL/experimental_information_extraction.py --input SKILL/TASK1_experimental_information_extraction/examples/input.example.json --output SKILL/TASK1_experimental_information_extraction/examples/output.generated.json --dry-run --verbose
python -m unittest discover -s SKILL/TASK1_experimental_information_extraction/tests
```

## Limitations

This skill is deterministic and intentionally lightweight. It does not perform deep natural language understanding, literature lookup, or external database validation.
