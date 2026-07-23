<p align="center">
  <img src="assets/mesa-hero.png" alt="MESA computational chemistry agent overview" width="78%">
</p>

<h1 align="center">MESA: End-to-End Autonomous DFT Agent</h1>

<p align="center">
  A Codex-native research agent for computational chemistry, designed to carry
  an investigation from literature understanding and hypothesis generation to
  DFT calculations, evidence validation, and manuscript-ready scientific writing.
</p>

---

MESA is an end-to-end agent for catalyst discovery and mechanistic analysis.
It connects literature understanding, atomistic modeling, calculation planning,
result analysis, figure generation, and paper drafting into one agent-driven loop.

In practice, MESA is meant to move from a research question to a
publication-ready quality computational chemistry manuscript, with every claim
grounded in explicit calculations and reviewable evidence.

Our direction is simple: build an agent that can do research better than a PhD
student. That is what we are working toward.

## Fresh Clone Setup

Clone the repository, then expose only the initialization skill to Codex:

```bash
git clone https://github.com/GuGroup/mesa.git
cd mesa
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$PWD/SKILL/init/initialize-mesa" \
  "${CODEX_HOME:-$HOME/.codex}/skills/initialize-mesa"
```

Then open Codex in this checkout and run `initialize-mesa`. The skill runs the
repository setup checks and links the remaining MESA skills. After that, run
`initialize-project` to create `project/<project_name>/project_profile.md`, then
run `start-research`.
