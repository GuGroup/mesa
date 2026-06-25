---
name: extract-data-from-pdf
description: Extract DFT-relevant experimentally reported materials information from PDF files by sending the PDF through a fixed OpenAI Responses API prompt that explicitly checks body text, tables, figures, captions, plots, axes, legends, annotations, microscopy images, spectra, and graphical data. Use when Codex needs to inspect a local materials-research PDF, extract experimental material identity, structure, synthesis conditions, measured properties, characterization evidence, figure-only values, or run a smoke test against a sample PDF such as ExperimentalData.pdf.
---

# Extract Data From PDF

## Overview

Use this skill to extract only explicitly reported experimental materials information that can reduce uncertainty when setting up a DFT calculation. Always use the bundled script for the asking process; do not replace its fixed prompt with a free-form summary or question.

## Workflow

1. Confirm the target file is a PDF and is under 50 MB.
2. Run `scripts/ask_pdf.py` with the PDF path. The script contains the extraction prompt and explicitly requires checking figures, captions, plots, axes, legends, annotations, tables, and body text.
3. Use `--task-note` only for non-conflicting context, such as a known target material name. Do not use it to request hypotheses, summaries, computational settings, or interpretations.
4. Treat model output as extracted evidence, not ground truth. If the result drives code or a report, preserve enough context to audit it.

## Script

Run:

```bash
python3 /path/to/extract-data-from-pdf/scripts/ask_pdf.py /path/to/file.pdf
```

Useful options:

- `--model`: override the model. Defaults to `OPENAI_MODEL`, then `gpt-5.5`.
- `--task-note`: append non-conflicting context to the fixed extraction prompt.
- `--save-response`: write the full API response JSON for debugging.
- `--dry-run`: validate inputs and show the request summary without calling the API.

The script reads `OPENAI_API_KEY` from the environment and uses only the Python standard library. It asks for a concise structured text report with sections for material identity, crystal/structural information, experimental conditions, measured properties, characterization results, figure-extracted data, and missing information.

## Fixed Prompt Boundary

Do not summarize the PDF unless the summary is directly represented by the fixed extraction output. The prompt explicitly forbids hypotheses, mechanisms, inferred missing information, DFT-setting recommendations, computational-method suggestions, speculative structures, property predictions, scientific discussion, and interpretations beyond what is explicitly reported.

The script prompt explicitly tells the model to inspect figure panels and extract visible figure data, including axis labels, units, tick values, legend labels, annotations, peak positions, binding energies, Raman shifts, diffraction angles, current density, voltage, efficiency, yield, selectivity, time, temperature, pressure, composition values, microscopy observations, elemental maps, spectra, and plot/caption-only values.

For smoke testing with `ExperimentalData.pdf`:

```bash
python3 extract-data-from-pdf/scripts/ask_pdf.py ExperimentalData.pdf --dry-run
```

Remove `--dry-run` when `OPENAI_API_KEY` is set and an actual API smoke test is intended.

## API Notes

Read `references/openai-file-inputs.md` when changing the API request format, model constraints, or file handling behavior.
