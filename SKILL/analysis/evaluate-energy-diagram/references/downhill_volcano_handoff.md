# Unresolved Ranking to Sabatier-Volcano Handoff

## Goal

Use `evaluate-energy-diagram` for deterministic parsing and thermodynamic
screening. Invoke `SKILL/figure/plot-sabatier-volcano` when at least two
catalysts are evaluable but the diagram does not identify one unique
thermodynamic best catalyst.

## Trigger order

1. Normalize all catalysts to the same reaction coordinate.
2. Use equilibrium-potential-transformed steps when valid transformed profiles
   are available for every catalyst.
3. Otherwise use the input reaction-energy profile.
4. Apply `downhill_trigger_scope` to retain comparable profile diagnostics:
   - `all_steps`: every non-duplicate represented transition must be downhill.
   - `electrochemical`: only potential-coupled/electrochemical transitions are tested.
5. Require at least two catalysts, two numerical ranking rows, and evaluable
   transitions for every compared catalyst.
6. Trigger when the reaction-specific thermodynamic ranking is unresolved or
   when multiple top scores are tied within `downhill_tolerance_ev`.
7. Preserve uphill-step/PDS evidence in the payload; an uphill step does not
   suppress the handoff.

## Non-trigger cases

Do not invoke `SKILL/figure/plot-sabatier-volcano` automatically when:

- fewer than two catalysts are present;
- fewer than two numerical ranking rows are available;
- no eligible transition can be identified for a compared catalyst;
- one unique thermodynamic best catalyst is resolved;
- the user sets `enable_unresolved_volcano_handoff` to false.

`enable_downhill_volcano_handoff` remains a deprecated compatibility alias when
the new switch is absent.

## Required downstream interpretation

The downstream skill must:

- read the electrochemical reference first;
- apply the Sabatier principle;
- reject the claim that the steepest or most negative profile is automatically best;
- select or validate a reaction-specific binding descriptor;
- distinguish weak-binding, near-optimal-binding, and strong-binding behavior;
- consider product desorption, surface regeneration, competing reactions,
  kinetic barriers, coverage, solvent, field, and stability;
- state that two catalyst points alone cannot establish a new empirical volcano
  without an external scaling relation or theoretical model.

## Orchestration boundary

The local Python module cannot activate a Codex skill. It emits:

```text
data.skill_handoff.triggered = true
next_action.recommendation = invoke_skill
next_action.target_skill = plot-sabatier-volcano
next_action.target_skill_path = SKILL/figure/plot-sabatier-volcano
```

The host agent first reads `SKILL/figure/plot-sabatier-volcano/SKILL.md`, then
invokes the skill name declared there exactly once with the emitted
`handoff_payload`. `$plot-sabatier-volcano` is the directory-name fallback.
