# Methods Section Writer Output Schema

`methods_section_text.json` contains:

- `schema_version`
- `strategy_id`
- `source_digest`
- `sections`
- `missing_details`
- `validation`

Schema version 3 uses ordered content blocks. Each section contains:

- `section_id`
- `title`
- `text`
- `content_blocks`

`text` is a compatibility field derived from paragraph blocks only. It is not
the authoritative rendering order.

`content_blocks` is the authoritative manuscript order. Each block is one of:

```json
{"type": "paragraph", "text": "Academic Methods prose."}
```

or:

```json
{
  "type": "equation",
  "label": "Thermochemical free-energy correction",
  "latex": "\\Delta G = \\Delta E + \\Delta E_{\\mathrm{ZPE}} - T\\Delta S",
  "explanation": "Reaction free energies were corrected from electronic energy differences using zero-point-energy and entropy contributions."
}
```

Equation blocks should be used for mathematical equations, chemical equations,
electrochemical identities, and reaction-state sequences. Do not repeat the same
expression inside paragraph text.

Allowed section ids:

- `model_construction`
- `geometry_optimization`
- `vibrational_free_energy_corrections`
- `electrochemical_free_energy_formalism`

`missing_details` should be a list of concise factual details that could improve
the Methods section in a future run. It must not be used to add unsupported
claims to the current text.
