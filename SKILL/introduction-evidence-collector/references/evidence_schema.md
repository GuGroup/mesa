# Introduction Evidence Collector Schema

`introduction_evidence.json` is the full audit artifact. It contains:

- `schema_version`
- `project`
- `strategy_id`
- `source_files`
- `source_papers`
- `evidence_by_role`
- `project_positioning`
- `citation_seed`
- `validation`

`introduction_writer_digest.json` is the compact writer input:

```json
{
  "schema_version": 1,
  "strategy_id": "S1",
  "section_goal": "Write a literature-led Introduction...",
  "narrative_order": [
    "field_motivation",
    "catalyst_platform",
    "design_rationale",
    "mechanistic_gap",
    "prior_related_evidence",
    "present_work_framing"
  ],
  "writing_profile": {
    "name": "optional project profile",
    "introduction_roles": [
      {
        "role": "catalyst_platform",
        "keywords": ["material", "surface", "active site"],
        "limit": 5
      }
    ]
  },
  "evidence_points": [
    {
      "role": "mechanistic_gap",
      "claim": "Compact evidence statement.",
      "citation_keys": ["ExampleKey"],
      "source_ids": ["P005"],
      "source_titles": ["Example source title"],
      "evidence_text": "Short extracted support text."
    }
  ],
  "project_positioning": {
    "selected_strategy_id": "S1",
    "selected_strategy_title": "...",
    "present_work_question": "...",
    "present_work_gap": "...",
    "present_work_scope": ["..."]
  },
  "writing_guardrails": [
    "Do not mention strategy/procedure/workflow language.",
    "Do not mention figures or Results values.",
    "Use citations later; do not include citation placeholders in writer output."
  ]
}
```

Default generic evidence roles:

- `field_motivation`: broad catalytic motivation and performance challenge.
- `catalyst_platform`: catalyst/material family and structural context.
- `design_rationale`: modification, composition, defect, or site-tuning logic.
- `mechanistic_gap`: reaction mechanism, intermediates, descriptors, or
  condition-specific ambiguity.
- `prior_related_evidence`: prior experimental or computational evidence
  related to the target catalyst system.
- `computational_design_logic`: descriptor, DFT, free-energy, active motif
  design logic used to motivate the present computation.
- `present_work_framing`: selected-strategy-derived objective only.

Project-specific names and keywords should be supplied through
`manuscript_writing_profile.json`.
