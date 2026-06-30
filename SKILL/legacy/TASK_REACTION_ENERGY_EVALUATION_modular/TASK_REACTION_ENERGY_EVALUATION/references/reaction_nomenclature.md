# Reaction Nomenclature Rules

## Curated common electrocatalysis names

| Abbreviation | Canonical name | Main evaluator |
|---|---|---|
| HER | hydrogen evolution reaction | `evaluators/her.py` |
| OER | oxygen evolution reaction | `evaluators/oer.py` |
| ORR | oxygen reduction reaction | `evaluators/schema_reduction.py` |
| NO3RR | nitrate reduction reaction | `evaluators/schema_reduction.py` |
| NO2RR | nitrite reduction reaction | `evaluators/schema_reduction.py` |
| NRR | nitrogen reduction reaction | `evaluators/schema_reduction.py` |
| CO2RR | carbon dioxide reduction reaction | `evaluators/schema_reduction.py` |

## Fallback naming rule

For less common reactions that look like reduction paths, the skill uses:

```text
<species common name or formula> reduction reaction
<formula>RR
```

Examples:

```text
NO3- -> nitrate reduction reaction, NO3RR
NO2- -> nitrite reduction reaction, NO2RR
CO2  -> carbon dioxide reduction reaction, CO2RR
```

If a species is not in the internal common-name map, the formula is preserved rather than converted into a guessed systematic name.

## Why this is conservative

The skill is intended for catalyst-performance screening, not chemical nomenclature standardization. It therefore prioritizes stable electrocatalysis usage and avoids hallucinating names for uncommon species.
