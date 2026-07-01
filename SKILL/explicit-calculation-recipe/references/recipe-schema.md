# Explicit Calculation Recipe Schema

The generator writes JSON files with `schema_version: 1`.

## `recipe_index.json`

Required fields:

- `schema_version`: integer, currently `1`.
- `strategy_id`: strategy identifier when present in the source artifact.
- `source_strategy_path`: path passed to the generator.
- `computational_json_pointer`: source path to the computational block.
- `translator_policy`: object describing that no feasibility judgment was made.
- `procedure_count`: number of source procedure lines.
- `procedures`: list of procedure records.

Each procedure record contains:

- `procedure_id`: `P###`.
- `folder`: output folder path relative to the output root.
- `source_json_pointer`: JSON pointer to the source procedure line.
- `source_text`: exact source procedure text.
- `calculation_count`: number of generated calculation recipes.
- `calculations`: list of calculation identifiers and folders.

## `procedure.json`

Required fields:

- `schema_version`
- `strategy_id`
- `procedure_id`
- `source_json_pointer`
- `source_text`
- `source_context`
- `calculation_folders`

`source_context` may include copied context from:

- `models`
- `methods`
- `dft_details`
- `computational_tests_to_run`
- `computational_benchmark_comparisons`

These fields are context for later execution and preflight. They are not
feasibility judgments.

## `recipe.json`

Required fields:

- `schema_version`
- `strategy_id`
- `procedure_id`
- `calculation_id`
- `source_procedure_text`
- `source_json_pointer`
- `recipe_role`
- `calculation_title`
- `required_prior_artifacts`
- `required_inputs`
- `operations`
- `method_intent`
- `output_artifacts`
- `notes`

Forbidden fields:

- `status`
- `blocked`
- `unsupported`
- `executable`
- `feasible`
- `requires_repair`
- `reason`
- `why_cannot_be_done`

The explicit-recipe skill is a translator only. A separate preflight skill may
add feasibility statuses later in a different artifact tree.

## Naming

Folder identifiers use deterministic slugs:

- procedures: `P###_<procedure_slug>`
- calculations: `C###_<calculation_slug>`

Slugs are lowercase ASCII, use underscores, and are derived from the source text
or calculation title.
