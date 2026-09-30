#!/usr/bin/env python3
"""Scores Energinet's wind and solar forecasts as described in METHOD.md (and CHANGELOG.md).

  python3 tools/score.py     reads data/raw/*.csv.gz, writes results/scores.csv, results/summary.md
                             and results/results.json

Standard library only (zoneinfo needs the system time zone database, present on GitHub runners).
Deterministic: same inputs, same bytes out.
"""
import csv, glob, gzip, json, os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DK = ZoneInfo("Europe/Copenhagen")
UTC = timezone.utc
AREAS = ["DK1", "DK2"]
TYPES = [("Offshore Wind", "offshore", "OffshoreWind"), ("Onshore Wind", "onshore", "OnshoreWind"), ("Solar", "solar", "SolarPower")]
HORIZONS = [("ForecastDayAhead", "day-ahead"), ("ForecastIntraday", "intraday"), ("Forecast5Hour", "5 hours"), ("Forecast1Hour", "1 hour")]
BASELINES = [("persistence", "like right now"), ("recent", "like recently (28-day average for the hour)")]
MIN_RECENT = 20  # CHANGELOG.md: the 28-day average needs at least 20 of the 28 values


def ts(s):
    return datetime.strptime(s[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)


def num(s):
    return None if s in ("", None) else float(s)


def read(pattern):
    rows = []
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "raw", pattern))):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def issue_time(col, hour):
    """When the forecast for `hour` (UTC) was issued, per METHOD.md."""
    if col == "ForecastDayAhead":
        d = hour.astimezone(DK).date() - timedelta(days=1)
        return datetime(d.year, d.month, d.day, 18, tzinfo=DK).astimezone(UTC)
    if col == "ForecastIntraday":
        # CHANGELOG.md 2026-09-30 #1: treated as issued at 08:00 Danish time (not 06:00, as described)
        d = hour.astimezone(DK).date()
        return datetime(d.year, d.month, d.day, 8, tzinfo=DK).astimezone(UTC)
    if col == "Forecast5Hour":
        return hour - timedelta(hours=5)
    if col == "Forecast1Hour":
        return hour - timedelta(hours=1)
    raise ValueError(col)


def load():
    out = {}  # (area, type) -> {hour: outcome}
    for r in read("settlement_*.csv.gz"):
        h = ts(r["HourUTC"])
        for tname, short, prefix in TYPES:
            vals = [num(v) for k, v in r.items() if k.startswith(prefix)]
            vals = [v for v in vals if v is not None]
            if vals:
                out.setdefault((r["PriceArea"], tname), {})[h] = sum(vals)
    fc = {}  # (area, type) -> {hour: {col: value}}
    for r in read("forecasts_*.csv.gz"):
        fc.setdefault((r["PriceArea"], r["ForecastType"]), {})[ts(r["HourUTC"])] = {c: num(r[c]) for c, _ in HORIZONS}
    return out, fc


def baselines(outc, col, hour):
    iss = issue_time(col, hour)
    last = iss.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)  # last full hour ended by the issue time
    pers = outc.get(last)
    day0 = datetime(iss.year, iss.month, iss.day, tzinfo=UTC)
    vals = [outc.get(day0 - timedelta(days=k) + timedelta(hours=hour.hour)) for k in range(1, 29)]
    vals = [v for v in vals if v is not None]
    rec = sum(vals) / len(vals) if len(vals) >= MIN_RECENT else None
    return {"persistence": pers, "recent": rec}


def scored(col, hour):
    """CHANGELOG.md 2026-09-30 #1: intraday is scored only for hours starting at 09:00 Danish time or later."""
    if col == "ForecastIntraday":
        return hour >= issue_time(col, hour) + timedelta(hours=1)
    return True


def metrics(points):
    """points: list of (forecast, outcome, {baseline: value})."""
    n = len(points)
    if not n:
        return None
    mae = sum(abs(f - o) for f, o, _ in points) / n
    mean_o = sum(o for _, o, _ in points) / n
    m = {"hours": n, "mae_mw": round(mae, 2), "nmae_pct": round(100 * mae / mean_o, 2) if mean_o else None,
         "bias_mw": round(sum(f - o for f, o, _ in points) / n, 2), "mean_outcome_mw": round(mean_o, 2)}
    for b, _ in BASELINES:
        bp = [(f, o, bb[b]) for f, o, bb in points if bb.get(b) is not None]
        if not bp:
            continue
        mf = sum(abs(f - o) for f, o, _ in bp) / len(bp)
        mb = sum(abs(v - o) for _, o, v in bp) / len(bp)
        m[f"{b}_hours"] = len(bp)
        m[f"{b}_mae_mw"] = round(mb, 2)
        m[f"{b}_skill"] = round(1 - mf / mb, 4) if mb else None
        m[f"{b}_won_pct"] = round(100 * sum(1 for f, o, v in bp if round(abs(f - o), 6) < round(abs(v - o), 6)) / len(bp), 2)
    return m


def main():
    outcomes, forecasts = load()
    rows, missing = [], []
    for area in AREAS:
        for tname, short, _ in TYPES:
            outc, fcs = outcomes.get((area, tname), {}), forecasts.get((area, tname), {})
            hours = sorted(set(outc) & set(fcs))
            per = {c: [] for c, _ in HORIZONS}  # (hour, forecast, outcome, baselines)
            for h in hours:
                o = outc[h]
                for c, _ in HORIZONS:
                    f = fcs[h][c]
                    if f is None or not scored(c, h):
                        continue
                    if short == "solar" and f == 0 and o == 0:
                        continue
                    per[c].append((h, f, o, baselines(outc, c, h)))
            for c, label in HORIZONS:
                n_missing = sum(1 for h in hours if fcs[h][c] is None and scored(c, h))
                missing.append({"area": area, "type": short, "horizon": label, "hours_missing": n_missing})
            # common hours: all four forecasts and the outcome exist (solar: not all zero)
            common = set(h for h, *_ in per[HORIZONS[0][0]])
            for c, _ in HORIZONS[1:]:
                common &= set(h for h, *_ in per[c])
            if short == "solar":
                common = set(h for h in common if outc[h] != 0 or any(fcs[h][c] for c, _ in HORIZONS))
            for c, label in HORIZONS:
                for hourset in ("all", "common"):
                    pts = [p for p in per[c] if hourset == "all" or p[0] in common]
                    splits = [("period", "all", pts)]
                    by_y, by_q = defaultdict(list), defaultdict(list)
                    for p in pts:
                        by_y[str(p[0].year)].append(p)
                        by_q[f"Q{(p[0].month - 1) // 3 + 1}"].append(p)
                    splits += [("year", k, v) for k, v in sorted(by_y.items())] + [("quarter", k, v) for k, v in sorted(by_q.items())]
                    for split, key, sp in splits:
                        m = metrics([(f, o, b) for _, f, o, b in sp])
                        if m:
                            rows.append({"area": area, "type": short, "horizon": label, "hours_set": hourset,
                                         "split": split, "split_key": key, **m})
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    fields = sorted({k for r in rows for k in r}, key=lambda k: (["area", "type", "horizon", "hours_set", "split", "split_key"] + [k]).index(k))
    with open(os.path.join(ROOT, "results", "scores.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    manifest = json.load(open(os.path.join(ROOT, "data", "manifest.json")))
    json.dump({"method": "https://github.com/kvantixtech/energinet-forecasts/blob/main/METHOD.md",
               "source": "Energinet (www.energidataservice.dk), CC BY 4.0", "downloaded_at_utc": manifest["downloaded_at_utc"],
               "period": manifest["period"], "missing": missing,
               "scores": [r for r in rows if r["split"] != "quarter" or r["hours_set"] == "all"]},
              open(os.path.join(ROOT, "results", "results.json"), "w"), indent=1, sort_keys=True)
    write_summary(rows, missing, manifest)
    print(f"{len(rows)} score rows")


def write_summary(rows, missing, manifest):
    p = manifest["period"]
    out = ["# Results", "", "Generated by `tools/score.py`. Do not edit by hand.", "",
           f"Period: {p['first_hour_utc']} to {p['last_hour_utc']} UTC. Data downloaded {manifest['downloaded_at_utc']}. "
           "Source: Energinet (www.energidataservice.dk), CC BY 4.0.", "",
           "Stored forecasts are scored as they are stored today; see METHOD.md, \"What this can't show\".", ""]
    for area in AREAS:
        for _, short, _ in TYPES:
            sub = [r for r in rows if r["area"] == area and r["type"] == short and r["split"] == "period"]
            if not sub:
                continue
            out += [f"## {area} · {short}", "",
                    "| Horizon | Hours | MAE (MW) | Normalised MAE | Bias (MW) | Skill vs \"like right now\" | Won | Skill vs \"like recently\" | Won |",
                    "|---|---|---|---|---|---|---|---|---|"]
            for hs in ("common", "all"):
                for r in [x for x in sub if x["hours_set"] == hs]:
                    sk = lambda b: "–" if r.get(f"{b}_skill") is None else f"{100 * r[f'{b}_skill']:+.1f} %"
                    wn = lambda b: "–" if r.get(f"{b}_won_pct") is None else f"{r[f'{b}_won_pct']:.1f} %"
                    out.append(f"| {r['horizon']} ({hs} hours) | {r['hours']:,} | {r['mae_mw']:.1f} | {r['nmae_pct']:.1f} % | "
                               f"{r['bias_mw']:+.1f} | {sk('persistence')} | {wn('persistence')} | {sk('recent')} | {wn('recent')} |")
            out.append("")
    out += ["Skill: 1 − MAE(forecast) / MAE(baseline). Won: share of hours where the forecast was closer than the baseline. "
            "Common hours: hours where all four forecasts exist, used to compare horizons.", "",
            "## Missing forecast values", "", "| Area | Type | Horizon | Hours missing |", "|---|---|---|---|"]
    out += [f"| {m['area']} | {m['type']} | {m['horizon']} | {m['hours_missing']:,} |" for m in missing]
    open(os.path.join(ROOT, "results", "summary.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
