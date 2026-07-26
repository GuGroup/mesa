# Source HER Skill analysis and design decisions

## What was retained

The supplied alkaline-HER Skill uses a strong pattern for deterministic
scientific bookkeeping:

1. a narrow `SKILL.md` scope and explicit claim boundary;
2. two accepted input shapes: MESA `free_energy_records` and a standalone JSON;
3. a standard-library Python helper that writes JSON/CSV artifacts;
4. required endpoint-state validation;
5. evidence acceptance states and caveats;
6. a separate input-schema reference and `agents/openai.yaml` metadata.

Both new Skills retain those patterns.

## What was changed

| Source behavior | OER/NO3RR redesign |
| --- | --- |
| `pH` and `potential_rhe` are recorded but do not change the HER equations. | RHE/SHE potential and pH terms are evaluated in the CHE equations and tested. |
| Endpoint records use only a completed `free_energy_ev`. | A record may use either `free_energy_ev` or `electronic_energy_ev + corrections_ev`; providing both is rejected. |
| The HER ranking is an intentionally bounded custom score. | OER uses four-step `U_L` and thermodynamic overpotential; NO3RR uses reduction-step limiting potential plus separate chemical-step diagnostics. |
| Evidence state is reported but does not remove a motif from ranking. | Failed/excluded evidence and failed closure remain visible but are not ranking-eligible. |
| No thermodynamic-cycle closure test. | OER must close to the selected water-splitting cycle; NO3RR must close to an eight-electron nitrate-to-NH3 reaction. |
| One optional H2O command-line correction. | External and record-level phase/molecular corrections are checked for double counting. |

## Why two Skills rather than one

OER and NO3RR require different state graphs, reference cycles, limiting-potential
sign conventions, and scientific claim boundaries. Keeping them separate makes
triggering more reliable and prevents OER-specific constants or NO3RR-specific
HNO3 terms from leaking into the wrong reaction.
