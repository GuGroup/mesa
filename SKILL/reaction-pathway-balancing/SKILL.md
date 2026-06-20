---
name: reaction-pathway-balancing
description: Convert reaction pathway strings into balanced reaction metadata for electrochemical CHON systems. Use when Codex needs to parse, validate, or balance electrochemical reaction pathways for downstream VASP structure generation, calculation orchestration, or energy diagram construction.
---

# Reaction Pathway Balancing Skill

Purpose

Convert a reaction pathway string into balanced reaction metadata for electrochemical CHON systems.

This skill prepares metadata for downstream VASP structure generation, calculation orchestration, and energy diagram construction.

⸻

Entry Point

Always use:

from tools.main import run

Do not manually call low-level parsing, balancing, or serialization functions unless debugging.

⸻

Input

Required

reaction_pathway

Reaction pathway string.

Example:

HNO3(g)>*NO3>*NO2>*NO>*NOH>*N>*NH>*NH2>NH3(g)

system

Currently supported:

ElectroChem

Accepted aliases:

ElectroChem
ElectroChemical
ElectroChemistry

⸻

Usage

from tools.main import run
metadata = run(
    reaction_pathway="HNO3(g)>*NO3>*NO2>*NO",
    system="ElectroChem"
)

⸻

State Syntax

Gas Species

Gas species must explicitly include (g).

Examples:

HNO3(g)
NH3(g)
H2(g)
H2O(g)
CO(g)

Adsorbed Species

Adsorbed species must begin with *.

Examples:

*NO3
*NO2
*NO
*NOH
*N
*NH
*NH2

Multiple Species in a State

States may contain multiple species joined by +.

Examples:

FAL(g)+2H2(g)
*FAL+4*H

⸻

ElectroChem Policy

The current implementation supports electrochemical balancing only.

Elemental CHON differences are balanced using gas reservoir species:

CO(g)
H2O(g)
NH3(g)
H2(g)

Do not manually balance reaction pathways. Always call tools.main.run().

⸻

Slab Normalization

Each balanced state includes slab_count.

slab_count is assigned at the pathway level so that all states have the same total number of adsorbed species after balancing.

Conceptually:

slab_count(state) = max_ads_count_in_pathway - ads_count(state)

where ads_count(state) is computed from the final balanced state.

Example:

HNO3(g)>*NO3

returns:

HNO3(g): slab_count = 1.0
*NO3:    slab_count = 0.0

This means the energy expression for the first state requires one clean slab contribution.

⸻

Output

The returned object is a metadata dictionary.

Example:

{
  "task_type": "reaction_pathway_balance",
  "status": "finished",
  "reaction_pathway": "HNO3(g)>*NO3>*NO2",
  "policy": "ElectroChemPolicy",
  "states": [...]
}

⸻

State Schema

Each state contains:

{
  "label": "*NO2",
  "raw_state": [
    {
      "species": "NO2",
      "phase": "ADS",
      "coefficient": 1.0
    }
  ],
  "balanced_state": [
    {
      "species": "NO2",
      "phase": "ADS",
      "coefficient": 1.0
    },
    {
      "species": "H2O",
      "phase": "GAS",
      "coefficient": 1.0
    },
    {
      "species": "H2",
      "phase": "GAS",
      "coefficient": -0.5
    }
  ],
  "slab_count": 0.0
}

⸻

Validation Rules

1. Gas species must include (g).
2. Adsorbed species must begin with *.
3. Empty states are not allowed.
4. Reaction pathways must contain at least two states.
5. Unknown systems raise an exception.
6. Missing phases are not inferred.
7. Metadata must be generated through the public run() entry point.

⸻

Supported Scope

Current implementation:

Electrochemical CHON systems

Not currently supported:

Thermal catalytic balancing
Charged species
Electrochemical potential corrections
Non-CHON chemistries
Explicit adsorption-site labels such as top, bridge, hollow

⸻

Developer Notes

Use tools.main.run() as the public API.

Internal modules are implementation details:

species.py
split.py
parser.py
formula.py
policy.py
balancer.py
wrapper.py
serializer.py
main.py
