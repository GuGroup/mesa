# LaTeX Layout and Typesetting Reference

Use this reference when the task is page layout, float placement, sparse pages, stranded headings, oversized figures, or Supplementary Information layout rather than prose polishing.

## Required Workflow

1. Compile the document.
2. Render affected pages to images or a contact sheet.
3. Read the LaTeX log for float, overfull, underfull, and page-break warnings.
4. Apply the smallest layout fix.
5. Compile and visually inspect the affected pages again.

## Common Fixes

- Loose page with one heading: move the heading with nearby text or adjust page breaks deliberately.
- Oversized figure: regenerate the figure at a better aspect ratio instead of forcing it into the page.
- Multi-panel figure too wide: stack panels or split into related figures.
- Float appears too late: use `placeins`, `[!htbp]`, or a local barrier only when the surrounding narrative supports it.
- Sparse Supplementary Information: rebalance figure sizes, captions, and section breaks.

## Rules

- Do not judge layout from `.tex` alone.
- Avoid global spacing hacks unless the whole document needs them.
- Do not hide warnings by shrinking text below the journal-readable size.
- Preserve figure readability and caption completeness.
