# Project

Use the repository's modeling, calculation, analysis, and writing skills for
computational catalysis work. Read `workflow.md` before starting a study and
load relevant domain guides explicitly. Keep API keys in `DEPENDENCY/.env`.

Use `initialize-mesa` for environment checks, dependency setup, and skill
symlinks. Take calculation settings and execution constraints from the user's
task and the tool inputs.

Save research artifacts in English under `project/<project_name>/` unless the
user specifies another output directory. User-facing discussion can use the
user's language.

# Skill-first operating rules

Inspect the available skills, choose the narrowest applicable one, and read its
`SKILL.md` before using it. Use the skill's scripts and references when
applicable and mention the skill in the response. If no skill applies, say
"No matching skill found; proceeding without a skill."

## Wiki updates (internal use only)

After design decisions, milestones, or measured results, update `GuGroup/mesa-llm-wiki` before ending the session:

1. Run `git pull --rebase` in the wiki repository.
2. Append to `entities/mesa.md`, update its `updated` field, and add an entry to `log.md`.
3. Run `python3 tools/lint.py` with zero errors, then commit and push.

Do not modify `raw/` or copy code or data into the wiki. Reference them by path or repository link.
