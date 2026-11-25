# ChartTruth: catch misleading charts

**WAICY 2026 · High School AI Showcase** · Live: https://yersultan2000.github.io/charttruth/

ChartTruth reads bar, line and pie charts with AI, checks them with transparent, deterministic math, and redraws them honestly.

## How it works
1. **AI reads:** Gemini or Claude transcribes the chart into strict JSON. It never judges. In **cross-check mode** both models read it, and any disagreement sends the chart to a human.
2. **A person checks:** every value is editable, with undo and redo. Below 60% confidence it refuses to judge.
3. **Rules decide:** lie factor (`looks ÷ really > 1.25`), uneven tick steps (> 5%), pie sums outside 99 to 101%, flipped axis, dual axis and 3D, plus a guardrail for honest zoomed science and finance line charts.
4. **Honest redraw:** zero baseline, even ticks, upright, flat 2D, pies rescaled to 100%, with an honest caption and alt text.

## Features
- Correction wipe (drag or arrow keys) with red-pen marks numbered to each finding
- 8 offline case files, including two honest ones, to show it doesn't flag everything
- "Show the math" for every finding; downloadable correction card; copyable caption, alt text and JSON
- Spot the Lie game (fresh charts each game, marked by the rule engine), Deception lab
- Guided tour, keyboard shortcuts (`?`), dark mode, undo and redo, reduced-motion support

## Evidence
Coverage computed from the official Misviz labels ([UKPLab/acl2026-misviz](https://github.com/UKPLab/acl2026-misviz), test split, 2,077 real charts):
- **44%** of the 1,441 misleading charts contain a misleader ChartTruth fully checks (85% including partial pie-sum checks)
- **78%** of all test charts are bar, line or pie charts

Coverage is not accuracy. Measure accuracy with the benchmark:
```bash
git clone https://github.com/UKPLab/acl2026-misviz
pip install google-genai anthropic pillow
export GEMINI_API_KEY=...  ANTHROPIC_API_KEY=...
python eval_misviz.py --source github --misviz-json acl2026-misviz/data/misviz/misviz.json \
  --provider both --misleading 30 --clean 15 --out results.json
```
Paste `results.json` into the Evidence section.

## Limits
Single data series only. It doesn't detect cherry-picked ranges, misleading captions or bad source data. "Misleading" describes the design, never the author's intent.

Misviz © UKPLab, CC BY-SA 4.0.
