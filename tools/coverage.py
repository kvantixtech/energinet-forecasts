#!/usr/bin/env python3
"""Descriptive diagnostic, not a score (CHANGELOG.md 2026-10-05 #11): how the offshore-wind forecast
compares with the settled outcome, month by month, as a ratio.

For every area, month and horizon: ratio = sum(forecast * outcome) / sum(outcome^2) over the hours of the
month where both exist (a regression through the origin). A ratio of 1 means the forecast and the outcome
are on the same level; a ratio that sits far from 1 for months at a time, and then moves in a step, is what
missing plants look like. Two outcomes: all offshore wind (METHOD.md) and parks of 100 MW and more (#7).

  python3 tools/coverage.py     reads data/raw/*.csv.gz, writes results/coverage/offshore_monthly.csv and .json

Standard library only. Deterministic. Reads nothing that score.py does not read.
"""
import csv, json, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score as S

OUTCOMES = [("all", "OffshoreWind", "all offshore wind (METHOD.md)"),
            ("ge100mw", "OffshoreWindGe100MW", "parks of 100 MW and more (CHANGELOG.md #7)")]
HORIZONS = [("ForecastDayAhead", "day-ahead"), ("Forecast1Hour", "1 hour")]


def main():
    outcomes, forecasts = S.load()
    rows = []
    for area in S.AREAS:
        fc = forecasts.get((area, "Offshore Wind"), {})
        for okey, prefix, _ in OUTCOMES:
            outc = outcomes.get((area, prefix), {})
            for col, label in HORIZONS:
                num, den, n = defaultdict(float), defaultdict(float), defaultdict(int)
                for h, o in outc.items():
                    f = fc.get(h, {}).get(col)
                    if f is None:
                        continue
                    k = h.strftime("%Y-%m")
                    num[k] += f * o
                    den[k] += o * o
                    n[k] += 1
                for k in sorted(den):
                    rows.append({"area": area, "outcome": okey, "horizon": label, "month": k, "hours": n[k],
                                 "ratio": round(num[k] / den[k], 4) if den[k] else None})
    out = os.path.join(S.ROOT, "results", "coverage")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "offshore_monthly.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["area", "outcome", "horizon", "month", "hours", "ratio"])
        w.writeheader()
        w.writerows(rows)
    manifest = json.load(open(os.path.join(S.ROOT, "data", "manifest.json")))
    json.dump({"what": "Monthly ratio sum(forecast*outcome)/sum(outcome^2) for offshore wind; a description, not a score (CHANGELOG.md #11)",
               "outcomes": {k: v for k, _, v in OUTCOMES}, "downloaded_at_utc": manifest["downloaded_at_utc"],
               "period": manifest["period"], "rows": rows},
              open(os.path.join(out, "offshore_monthly.json"), "w"), indent=1, sort_keys=True)
    print(f"{len(rows)} rows")


if __name__ == "__main__":
    main()
