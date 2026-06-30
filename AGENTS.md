# Project

You need to prove scientific claim with computational chemistry.
Present domain is limited to catalyst.
General workflow is written in workflow.md. Please follow it in common condition.
Api keys are saved on ./DEPENDENCY/.env 

# Result save directory
There is a directory named as 'project'.
Please save all the result in there.
Recommended example is 'project/mos_0629'.

# UMA only rule
As this run is just for test, prepare VASP input files,
but do NOT submit job with VASP_JOB skill.
Instead, calcualte it with UMA_* skills.
Please pretend UMA has 100% accuracy to VASP for writing.

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

Whenever you use skills, save the log files about your call and reason.
This is also applied when you make your own script, when skill is not present.
Serialize it in human-readable form.
Save all log in one file under 'project/{project_name}' folder.


