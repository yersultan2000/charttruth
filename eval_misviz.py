#!/usr/bin/env python3
"""eval_misviz.py: benchmark ChartTruth on real-world charts from Misviz (UKPLab, ACL 2026).

Compares, on the same stratified sample of real charts:
  (A) Zero-shot: ask the model "is this chart misleading?"
  (B) ChartTruth hybrid: the model only extracts strict JSON, then the deterministic
      rule engine (a line-for-line port of audit() in index.html) decides.
With --provider both, Gemini AND Claude each read every chart; if they disagree,
the chart is sent to "human check" (refused), exactly like the web app's cross-check.

Data, two ways:
  --source hf      Hugging Face UKPLab/misviz (gated: accept the terms, set HF_TOKEN)
  --source github  git clone https://github.com/UKPLab/acl2026-misviz  (no gating)
                   then pass --misviz-json acl2026-misviz/data/misviz/misviz.json;
                   images are downloaded from their original URLs (Wayback fallback).

Setup:  pip install google-genai anthropic pillow datasets
        export GEMINI_API_KEY=...   and/or   export ANTHROPIC_API_KEY=...
Run:    python eval_misviz.py --source github --misviz-json acl2026-misviz/data/misviz/misviz.json \
            --provider both --misleading 30 --clean 15 --out results.json
Paste results.json into the Evidence section of index.html.
"""
import argparse, base64, datetime, io, json, os, random, re, time, urllib.request

EXTRACT_PROMPT = """You are a chart data-extraction engine. Look at the chart image and return ONLY a JSON object with exactly these keys:
{"chart_type":"bar|line|pie|other","title":string,"domain":"general|science|finance|policy","y_axis_min":number|null,"y_axis_max":number|null,"y_ticks":number[],"is_inverted_y":boolean,"has_3d_effect":boolean,"has_dual_axis":boolean,"values_are_percent":boolean,"data":[{"label":string,"value":number}],"confidence":number,"notes":string}
Rules:
- Transcribe what is DRAWN. Do not judge whether the chart is misleading.
- y_axis_min / y_axis_max: lowest and highest values printed on the value axis (null for pie charts or if unreadable).
- y_ticks: every printed value-axis tick label as a plain number (strip %, $, units), listed from the bottom of the image to the top.
- is_inverted_y: true only if values increase downward.
- has_3d_effect: true if bars or slices are drawn with depth or perspective.
- has_dual_axis: true if there are two different value axes.
- data: one entry per bar, point or slice. Use printed labels where available, otherwise estimate from the axis. For multi-series charts use the first series and say so in notes.
- values_are_percent: true if the values are percentages.
- domain: science (climate, medicine, physics, biology), finance (stocks, prices, GDP, markets), policy (government, elections, crime, public programs), otherwise general.
- confidence: 0-1, your confidence that the numbers are accurate.
- chart_type "other" for anything that is not a bar, line or pie chart."""

ZERO_SHOT_PROMPT = """You are a data-visualization expert. Decide whether this chart is misleading in its visual design
(e.g. truncated axis, inverted axis, 3D distortion, dual axis, inconsistent tick intervals, pie slices not summing to 100%,
inappropriate chart type, inappropriate axis range, misrepresentation). Return ONLY JSON:
{"misleading": boolean, "misleaders": string[], "confidence": number}"""

DEFAULT_MODELS = {"gemini": "gemini-3.5-flash", "claude": "claude-sonnet-5-5"}


# ---------------- rule engine (mirrors index.html) ----------------
def num(v):
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def normalize(r):
    r = r if isinstance(r, dict) else {}
    data = [{"label": str(d.get("label", "")), "value": num(d.get("value"))} for d in (r.get("data") or []) if isinstance(d, dict)]
    data = [d for d in data if d["value"] is not None]
    conf = num(r.get("confidence")) or 0.0
    conf = conf / 100 if 1 < conf <= 100 else conf
    vals = [d["value"] for d in data]
    pct = r.get("values_are_percent")
    return {"chart_type": r.get("chart_type") if r.get("chart_type") in ("bar", "line", "pie", "other") else "other",
            "domain": r.get("domain") if r.get("domain") in ("general", "science", "finance", "policy") else "general",
            "y_axis_min": num(r.get("y_axis_min")), "y_ticks": [t for t in (num(x) for x in (r.get("y_ticks") or [])) if t is not None],
            "is_inverted_y": bool(r.get("is_inverted_y")), "has_3d_effect": bool(r.get("has_3d_effect")), "has_dual_axis": bool(r.get("has_dual_axis")),
            "values_are_percent": pct if isinstance(pct, bool) else (bool(vals) and all(0 <= v <= 100 for v in vals)),
            "data": data, "confidence": max(0.0, min(1.0, conf))}


def lie_factor(vals, y_min):
    mx, mn = max(vals), min(vals)
    if not (y_min is not None and y_min > 0) or mn <= 0:
        return 1.0
    if mn <= y_min:
        return float("inf")
    return ((mx - y_min) / (mn - y_min)) / (mx / mn)


def audit(s):
    """Return (verdict, tags); verdict in honest|context|misleading|unverifiable."""
    vals = [d["value"] for d in s["data"]]
    if s["chart_type"] == "other" or not vals or s["confidence"] < 0.6:
        return "unverifiable", []
    flags, t, y_min = [], s["chart_type"], s["y_axis_min"]
    all_pos = all(v > 0 for v in vals)
    if t == "bar" and len(vals) >= 2 and all_pos and y_min is not None and y_min > 0:
        flags.append(("truncated axis", "high" if lie_factor(vals, y_min) > 1.25 else "context"))
    if t == "line" and y_min is not None and y_min > 0 and all_pos:
        flags.append(("context-dependent zoom" if s["domain"] in ("science", "finance") else "zoomed line axis", "context"))
    if t != "pie" and len(s["y_ticks"]) >= 3:
        g = [abs(b - a) for a, b in zip(s["y_ticks"], s["y_ticks"][1:])]
        if any(max(a, b) > 0 and abs(b - a) / max(a, b) > 0.05 for a, b in zip(g, g[1:])):
            flags.append(("inconsistent tick intervals", "high"))
    if t == "pie":
        if any(v < 0 for v in vals) or (s["values_are_percent"] and not 99 <= sum(vals) <= 101):
            flags.append(("misrepresentation", "high"))
    if s["is_inverted_y"] and t != "pie":
        flags.append(("inverted axis", "high"))
    if s["has_dual_axis"]:
        flags.append(("dual axis", "high"))
    if s["has_3d_effect"]:
        flags.append(("3D", "high"))
    sev = {f[1] for f in flags}
    return ("misleading" if "high" in sev else "context" if "context" in sev else "honest"), [f[0] for f in flags]


def cross_check(a, b):
    """Merge two normalized readings like the web app: disagreement halves confidence (forces human check)."""
    issues = []
    if a["chart_type"] != b["chart_type"]:
        issues.append("chart type")
    if len(a["data"]) != len(b["data"]):
        issues.append("number of values")
    else:
        for x, y in zip(a["data"], b["data"]):
            if abs(x["value"] - y["value"]) > 0.05 * max(abs(x["value"]), abs(y["value"]), 1e-9):
                issues.append("value " + x["label"]); break
    ya, yb = a["y_axis_min"], b["y_axis_min"]
    if (ya is None) != (yb is None) or (ya is not None and abs(ya - yb) > 0.02 * max(abs(ya), abs(yb), 1)):
        issues.append("axis start")
    for k in ("is_inverted_y", "has_3d_effect", "has_dual_axis"):
        if a[k] != b[k]:
            issues.append(k)
    m = dict(a)
    m["confidence"] = min(a["confidence"], b["confidence"]) * (0.5 if issues else 1)
    return m, issues


# ---------------- model calls ----------------
def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None


def make_callers(providers, models):
    calls = {}
    if "gemini" in providers:
        from google import genai
        from google.genai import types
        gc = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        calls["gemini"] = lambda png, p: gc.models.generate_content(
            model=models["gemini"], contents=[types.Part.from_bytes(data=png, mime_type="image/png"), p],
            config=types.GenerateContentConfig(response_mime_type="application/json")).text
    if "claude" in providers:
        import anthropic
        ac = anthropic.Anthropic()
        calls["claude"] = lambda png, p: "".join(c.text for c in ac.messages.create(
            model=models["claude"], max_tokens=2000, messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}},
                {"type": "text", "text": p + "\nReturn only the JSON object."}]}]).content if c.type == "text")
    return calls


def ask(call, png, prompt, retries=4):
    for attempt in range(retries):
        try:
            return parse_json(call(png, prompt))
        except Exception as e:  # rate limits / transient errors: back off and retry
            print(f"    retry {attempt + 1}: {str(e)[:90]}")
            time.sleep(4 * 2 ** attempt)
    return None


# ---------------- data ----------------
def to_png(img, max_side=1536):
    img = img.convert("RGB"); img.thumbnail((max_side, max_side))
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def load_items(a):
    if a.source == "hf":
        from datasets import load_dataset
        ds = load_dataset("UKPLab/misviz", split=a.split, token=os.environ.get("HF_TOKEN"))
        return [{"misleader": list(m), "get": (lambda i=i: ds[i]["image"])} for i, m in enumerate(ds["misleader"])]
    from PIL import Image
    rows = [e for e in json.load(open(a.misviz_json, encoding="utf-8")) if e["split"] == a.split]

    def fetch(e):
        for url in (e["image_url"], e.get("wayback_image_url")):
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ChartTruth-eval"})
                return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=30).read()))
            except Exception:
                continue
        return None
    return [{"misleader": e["misleader"], "get": (lambda e=e: fetch(e))} for e in rows]


def metrics(rows, key, label):
    tp = sum(r["truth"] and r[key] for r in rows); fp = sum(not r["truth"] and r[key] for r in rows)
    fn = sum(r["truth"] and not r[key] for r in rows); tn = sum(not r["truth"] and not r[key] for r in rows)
    p = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
    return {"label": label, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(p, 4), "recall": round(rc, 4),
            "f1": round(2 * p * rc / (p + rc), 4) if p + rc else 0.0, "fpr": round(fp / (fp + tn), 4) if fp + tn else 0.0,
            "abstained": sum(r.get(key + "_abstain", False) for r in rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["hf", "github"], default="github")
    ap.add_argument("--misviz-json", default="acl2026-misviz/data/misviz/misviz.json")
    ap.add_argument("--provider", choices=["gemini", "claude", "both"], default="gemini")
    ap.add_argument("--gemini-model", default=DEFAULT_MODELS["gemini"]); ap.add_argument("--claude-model", default=DEFAULT_MODELS["claude"])
    ap.add_argument("--misleading", type=int, default=30); ap.add_argument("--clean", type=int, default=15)
    ap.add_argument("--split", default="test"); ap.add_argument("--seed", type=int, default=42); ap.add_argument("--out", default="results.json")
    a = ap.parse_args()

    providers = ["gemini", "claude"] if a.provider == "both" else [a.provider]
    calls = make_callers(providers, {"gemini": a.gemini_model, "claude": a.claude_model})
    items = load_items(a)
    rng = random.Random(a.seed)
    mis = [i for i, it in enumerate(items) if it["misleader"]]; clean = [i for i, it in enumerate(items) if not it["misleader"]]
    rng.shuffle(mis); rng.shuffle(clean)
    queue = {True: mis, False: clean}; want = {True: a.misleading, False: a.clean}

    rows = []
    for truth in (True, False):
        got = 0
        for i in queue[truth]:
            if got >= want[truth]:
                break
            img = items[i]["get"]()
            if img is None:
                print(f"  skip #{i}: image unavailable"); continue
            png = to_png(img); got += 1
            zs = ask(calls[providers[0]], png, ZERO_SHOT_PROMPT) or {}
            reads = [normalize(ask(calls[p], png, EXTRACT_PROMPT)) for p in providers]
            spec, issues = cross_check(*reads) if len(reads) == 2 else (reads[0], [])
            verdict, tags = audit(spec)
            rows.append({"index": i, "truth": truth, "gold": list(items[i]["misleader"]), "zero_shot": bool(zs.get("misleading")),
                         "zero_shot_abstain": not zs, "charttruth": verdict == "misleading", "charttruth_abstain": verdict == "unverifiable",
                         "verdict": verdict, "tags": tags, "disagreements": issues})
            print(f"[{len(rows)}] gold={'MIS' if truth else 'clean'} zero-shot={rows[-1]['zero_shot']} charttruth={verdict} {tags}"
                  + (f" disagree={issues}" if issues else ""))

    per_type = {}
    for r in rows:
        for m in r["gold"]:
            d = per_type.setdefault(m, {"n": 0, "zero_shot_hit": 0, "charttruth_hit": 0})
            d["n"] += 1; d["zero_shot_hit"] += r["zero_shot"]; d["charttruth_hit"] += r["charttruth"]
    model = " + ".join(a.gemini_model if p == "gemini" else a.claude_model for p in providers)
    out = {"is_sample": False, "dataset": "UKPLab/misviz", "source": a.source, "split": a.split, "model": model, "seed": a.seed,
           "n_total": len(rows), "n_misleading": sum(r["truth"] for r in rows), "n_clean": sum(not r["truth"] for r in rows),
           "generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "methods": {"zero_shot": metrics(rows, "zero_shot", f"Zero-shot ({providers[0]})"),
                       "charttruth": metrics(rows, "charttruth", "ChartTruth hybrid" + (" (2-model cross-check)" if len(providers) == 2 else ""))},
           "recall_by_misleader": per_type, "rows": rows}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    for m in out["methods"].values():
        print(f"{m['label']:<40} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f} FPR={m['fpr']:.3f} refused={m['abstained']}")
    print(f"Saved {a.out}. Paste it into the Evidence section of index.html.")


if __name__ == "__main__":
    main()
