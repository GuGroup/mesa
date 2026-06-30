# General MESA Skill Workflow

TEST VERSION.

You can start from # Strage Generation.4.Strategy generation.  (Skip #1~3)
The result from 1 to 3 is saved on /home/mesa/mesa/project/mos_0629_2/strategy_generation/
Please save files on mos_0629_2.

This workflow is a loop, not a linear checklist. The intended sequence is:

```text
strategy generation
-> select one strategy
-> modeling and calculation for that strategy
-> manuscript/result artifact for the completed strategy
-> update-strategies-from-manuscript decision
-> stop/finalize, repair, or select the next revised strategy
```

Do not move directly from one completed calculation strategy into the next
calculation strategy. After each selected strategy is modeled and analyzed, a
manuscript-like result artifact must be written and fed into
`update-strategies-from-manuscript`.

# Strategy Generation

Strategy generation should follow this continuous skill flow.

1. Experimental data extraction
  - Extract information by using skill in `TASK_EXTRACT_DATA_FROM_PDF`.
  - For present test, the experimental data is located at `/home/mesa/mesa/project/mos_0629/strategy_generation/experimental_data/Mos_exp_data.pdf`.

2. Paper search
  - Search paper with `search-papers-with-mcp` skill.
  - User must specify the target task and material domain.
  - User needs to download recommended papers manually.
  - Stop the first run here. User needs time to download.

3. Paper extraction
  - Extract information from paper by using `decompose-chemistry-paper-pdf` or `extract-general-insight-pdf`.
  - Paper under `strategy` folder should be extracted with `decompose-chemistry-paper-pdf`.
  - Paper under non-`strategy` folder should be extracted with `extract-general-insight-pdf`.

4. Strategy generation
  - Use `generate-strategies` skill (`generate_strategies` workflow stage).
  - Generate multiple computational chemistry strategies based on results of steps 1, 2, and 3.
  - Use information from experimental data extraction only as benchmark constraints or measured targets to explain computationally.
  - Do not generate experimental strategy plans; generate DFT/computational proof strategies from paper extraction.
  - Save the strategy artifact and identify strategy IDs, expected evidence, success criteria, and known limits.
  - Treat `prioritization.recommended_order` as the default strategy execution queue.

# Per-Strategy Execution Loop

Repeat this loop for one selected strategy at a time.

1. Select one strategy
  - Use the `select-next-strategy` skill before any modeling or calculation.
  - Choose exactly one strategy from the current strategy artifact.
  - Follow `prioritization.recommended_order` from the original generated strategy artifact, or `updated_prioritization.recommended_order` from the latest `update-strategies-from-manuscript` artifact.
  - Select the first strategy in the current recommended order unless it has already been completed, retired, blocked, or explicitly superseded.
  - Save the skill output as a strategy-selection artifact under the project folder.
  - Record why it is selected now.
  - If selecting a strategy out of recommended order, record the reason and the evidence that justifies the override before doing any modeling.
  - Record what claim it can prove and what claim it cannot prove.
  - Do not treat a partial descriptor strategy as sufficient for a broader mechanism unless the strategy itself says so.

2. Modeling and calculation
  - Build the required structures based on the selected strategy.
  - Use the narrowest relevant skills for slab building, adsorbate placement, gas references, UMA calculation, and result analysis.
  - For this test project, prepare VASP-compatible input files if needed, but do not submit VASP jobs.
  - If the user requests local GPU UMA execution, do not submit UMA through qsub; run UMA locally on the GPU node.
  - Save all structures, run inputs, run outputs, scripts, metadata, and analysis tables under the project folder.
  - If the executed modeling is narrower than the selected strategy, state that explicitly in the result artifact.

3. Evidence readiness
  - Use `calculation-result-analyzer` before manuscript intake.
  - Use `TASK_CONSTRUCT_ENERGY_DIAGRAM` if free-energy data must be constructed from reaction metadata/calculation registry.
  - Separate accepted, exploratory, failed, and excluded artifacts.
  - Continue only with accepted result artifacts, trusted structures, tables, and figure inputs.

4. Manuscript/result artifact
  - Use the Manuscript workflow below after evidence readiness.
  - Write a bounded manuscript-like artifact for the completed strategy.
  - The manuscript must distinguish:
    - what the completed strategy establishes;
    - what remains unresolved;
    - whether unresolved items are blocking or nonblocking for the original target task.

5. Strategy update decision
  - Use `update-strategies-from-manuscript` after the completed strategy is written as a manuscript or result artifact.
  - IMPORTANT: If the manuscript is enough for submission, stop the loop immediately.
  - Compare the manuscript result against the original generated strategy sequence.
  - Decide whether to:
    - stop/finalize;
    - maintain the original next strategy;
    - revise the next strategy;
    - reprioritize existing strategies;
    - repair/repeat the completed strategy;
    - add a new computational direction.
  - Keep updated strategies computational chemistry focused and preserve references from the original strategy plan and manuscript output.
  - Treat `updated_prioritization.recommended_order` as the next execution queue.
  - Only after this decision may the workflow proceed to the next strategy.

# Atomistic Modeling and UMA Calculation

Model required structures based on the selected strategy. Maintain the
skill-first rule and choose the narrowest task-specific skill. Do not run
modeling or calculation for a later strategy until the current strategy has
passed through manuscript/result writing and update-strategy decision.

# Manuscript

Manuscript workflow starts only after computational/result artifacts exist.
Write manuscript after one strategy is finished. This should be prior to updating strategy.
Manuscript skills do not run VASP, UMA, DFT, qsub, literature search, citation
verification, or reference export.

1. Evidence readiness
  - Use `calculation-result-analyzer`.
  - Use `TASK_CONSTRUCT_ENERGY_DIAGRAM` if free-energy data must be constructed from reaction metadata/calculation registry.
  - Continue only with accepted result artifacts, trusted structures, tables, and figure inputs.

2. Paper workspace intake
  - Use `mesa-manuscript-loop`.
  - Create/verify canonical `paper/`.
  - Stop if the manuscript topic does not match `paper/` evidence.

3. Claim logic
  - Use `mesa-manuscript-loop`.
  - Create/update `paper/logic/claim-matrix.yaml`.
  - Decide allowed claims before any prose.

4. Plot and figure plan
  - Use `mesa-manuscript-loop`.
  - Build the figure plan from accepted calculation results and claim logic.
  - Create/update `paper/logic/figure-map.yaml`.
  - Map each planned figure to claim IDs.

5. Plot and figure production
  - Use below skills:
    - `energy-diagram-plotter`
    - `sabatier-volcano-plotter`
    - `adsorbate-structure-grid`
  - Use `nature-figure` only for a new/custom manuscript figure design or multi-panel figure that is not covered by the existing plotter/grid skills.
  - Return generated figures and QA to `figure-map.yaml`.

6. Nature review of logic/figures
  - Use `nature-reviewer` through MESA reviewer roles:
    - `chem-claim-reviewer`
    - `chem-method-reviewer`
    - `chem-significance-reviewer`
    - `chem-figure-reviewer`
  - Output structured reviewer issues only.

7. Logic/figure revision loop
  - Use `mesa-manuscript-loop`.
  - Revise claim matrix, figure map, and story spine.
  - Repeat steps 3-4 until no open `BLOCKER` remains.

8. Manuscript architecture
  - Use `nature-writing` through `chem-manuscript-architect`.
  - Generate story spine, figure order, outline, and section contracts.
  - Do not write final prose yet.

9. Prose lock
  - Use `mesa-manuscript-loop` validators.
  - Validate claim matrix, figure map, reviewer issues, section contracts, and notation.

10. Section drafting
  - Use `nature-writing` through `chem-section-writer`.
  - Draft evidence-first, then frame:
    - Results / Results and Discussion
    - Methods / Computational Methods
    - Discussion
    - Conclusion
    - Introduction
    - Abstract and title
    - References
    - SI
  - A manuscript for one completed strategy may be a bounded result artifact rather than a full final paper.
  - Do not promote a strategy-specific claim into the original target claim unless the claim matrix supports it.

11. Prose polishing
  - Use `nature-polishing`.
  - Polish locked prose only.

12. Nature review of manuscript prose
  - Use `nature-reviewer`.
  - Review generated Markdown manuscript or locked sections.
  - Convert findings to MESA reviewer issues.

13. Manuscript revision loop
  - Use `mesa-manuscript-loop` + `chem-revision-editor`.
  - Patch accepted issues only.
  - Repeat steps 12-13 until manuscript-level blockers are resolved.

14. Final Markdown manuscript
  - Use `mesa-manuscript-loop`.
  - Finalize canonical Markdown/YAML/BibTeX/figure files under `paper/`.

15. Final typeset/export
  - Use `mesa-manuscript-typeset`.
  - Run check-only export first.
  - Then export DOCX/styled DOCX.
  - Export success is assembly/cross-reference verification, not scientific approval.

X. Manuscript-to-strategy feedback
  - Use `update-strategies-from-manuscript`.
  - Feed final claims, caveats, blockers, and excluded claims back into the next strategy.
  - This step is mandatory before the next modeling/calculation strategy begins.
  - The next modeling/calculation strategy must follow the latest `updated_prioritization.recommended_order`, except for explicitly logged blockers or overrides.

# Decision Rules

- If the completed manuscript resolves the original target task and has no blocking computational gaps, stop or finalize.
- If the manuscript resolves only a subclaim, continue the loop with a revised next strategy.
- If the completed calculations do not match the selected strategy scope, repair or repeat the completed strategy before moving on.
- If the completed strategy reveals a more important gap than the original next strategy, revise or reprioritize the strategy sequence.
- If a strategy artifact contains `prioritization.recommended_order` or `updated_prioritization.recommended_order`, follow that order as the default queue. Do not skip ahead without a recorded blocker, retirement, supersession, or explicit user instruction.
- If the target task is alkaline HER, `Delta G_H` evidence alone is descriptor-level support, not a complete alkaline mechanism, unless the target was explicitly narrowed to H adsorption only.
