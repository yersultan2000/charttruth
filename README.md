# ChartTruth: a corrections desk for charts

**WAICY 2026 · High School AI Showcase**

ChartTruth checks bar, line and pie charts for visual misinformation, then draws an honest version side by side.

**Live demo:** https://yersultan2000.github.io/charttruth/

## How it works
1. **Vision read:** Gemini (`gemini-3.5-flash`) transcribes the chart into strict JSON. It only reads; it never judges.
2. **Human check:** every extracted value is editable, and edits re-run the audit instantly.
3. **Deterministic rule engine:** transparent math decides the verdict:
   - truncated axis and Lie Factor (`visual ratio ÷ data ratio`, flagged above 1.25)
   - inconsistent tick intervals (more than 5% gap difference)
   - pie slices that don't sum to 100%, negative slices
   - inverted axis, dual axis, 3D distortion
   - **context-aware guardrail:** zoomed line axes, which are legitimate in science and finance, are not called misleading
   - **refusal:** below 60% confidence, it says "unable to verify" instead of guessing
4. **Honest render:** zero baseline, even ticks, flat 2D, pies rescaled to 100%.

Four built-in cases work fully offline. There is no backend and no build step: open `index.html`.

## Benchmark
`eval_misviz.py` compares zero-shot Gemini with the ChartTruth hybrid on real-world charts from [UKPLab/misviz](https://huggingface.co/datasets/UKPLab/misviz). It reports precision, recall, F1 and false-positive rate. The rule engine is a line-for-line port of the one in `index.html`.

```bash
pip install datasets google-genai pillow
export HF_TOKEN=...   GEMINI_API_KEY=...
python eval_misviz.py --misleading 30 --clean 15 --out results.json
```
Paste `results.json` into the **Evidence & standards** tab.

## Limits
Single data series only. It doesn't detect cherry-picked ranges, misleading captions or bad source data. "Misleading" describes the design, never the author's intent.
