# Figure contract before plotting

A publication-quality scientific figure is a visual argument, not an isolated pretty plot. Every figure starts from a claim, an evidence hierarchy, and a review-risk check before code or aesthetics. Before generating or editing code, establish the contract below.

## Missing runtime/package rule

Check Python and the required plotting packages before rendering. If the runtime
or packages are unavailable, stop before rendering and report the exact blocker.
You may provide a Python script and environment installation commands, but must
not claim that a preview or export was generated.

## The five-point contract

1. **Core conclusion**: write the one-sentence claim the figure must defend.
2. **Evidence chain**: map each planned panel to the claim, and drop panels that do not carry a unique piece of evidence.
3. **Archetype**: classify the figure as `quantitative grid`, `schematic-led composite`, `image plate + quant`, or `asymmetric mixed-modality figure`.
4. **Implementation**: use the Python plotting track for drawing, previewing, exporting, and visual QA.
5. **Journal/export contract**: set final dimensions, editable text, source data, statistics, image-integrity notes, and export formats before styling.

The highest-priority rule is: **the chart serves the scientific logic**. Aesthetic polish, template matching, and complex layout are subordinate to making the core conclusion clear, defensible, and reviewable.

For the full method to convert a request into core conclusion, evidence hierarchy, panel map, and review-risk checks, open `references/figure-contract.md`.
