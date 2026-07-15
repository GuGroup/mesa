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

After cloning, expose only the initialization skill to Codex. The
`initialize-mesa` skill will synchronize the rest of this repository's skills
during initialization.

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$PWD/SKILL/init/initialize-mesa" \
  "${CODEX_HOME:-$HOME/.codex}/skills/initialize-mesa"
```

Then run `initialize-mesa` from Codex. It will run the repository bootstrap
checks and link the remaining MESA skills into `$CODEX_HOME/skills` or
`~/.codex/skills`. To check the environment directly:

```bash
bash DEPENDENCY/bootstrap.sh
```
