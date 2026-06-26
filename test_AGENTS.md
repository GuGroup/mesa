# Project

You need to prove scientific claim with computational chemistry.
Present domain is limited to catalyst.
General workflow is written in ./WORKFLOW/workflow.md. Please follow it in common condition.

# Skill-first operating rules

You are operating inside a skills repository.

Before doing any user task:
1. Inspect the available skills index or skill folders.
2. Select the most relevant skill.
3. Read that skill's SKILL.md completely.
4. Follow the skill's workflow exactly.

Do not solve tasks ad hoc unless:
- no relevant skill exists, or
- the selected skill explicitly cannot apply.

When a relevant skill exists:
- use its scripts, templates, examples, and checklists;
- cite which skill was used in your response;
- do not bypass the skill with general reasoning.

If multiple skills apply:
- choose the narrowest task-specific skill first;
- compose skills only when necessary.

If no skill applies:
- say: "No matching skill found; proceeding without a skill."


# Skill-call logging

Whenever you use skills, save the log files about which skills you call and reason why you called.
Serialize it in human-readable form.

Save it on ./RESULT/0625/skill_log/log.json

