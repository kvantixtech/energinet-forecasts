"""Checks of the time rules in METHOD.md. Run: python3 tests/test_score.py"""
import os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import score as S

U = timezone.utc
h = lambda s: datetime.strptime(s, "%Y-%m-%d %H").replace(tzinfo=U)

# Day-ahead: 18:00 Danish time the day before = 16:00 UTC in summer, 17:00 UTC in winter
assert S.issue_time("ForecastDayAhead", h("2026-07-02 10")) == h("2026-07-01 16")
assert S.issue_time("ForecastDayAhead", h("2026-01-02 10")) == h("2026-01-01 17")
# 22:00 UTC on 1 July is already 2 July in Denmark, so it belongs to the forecast issued on 1 July
assert S.issue_time("ForecastDayAhead", h("2026-07-01 22")) == h("2026-07-01 16")
# Intraday: 06:00 Danish time the same day; hours before it are not scored
assert S.issue_time("ForecastIntraday", h("2026-07-02 10")) == h("2026-07-02 04")
assert not S.scored("ForecastIntraday", h("2026-07-02 03")) and S.scored("ForecastIntraday", h("2026-07-02 04"))
assert S.scored("ForecastDayAhead", h("2026-07-02 00"))
# 5 hours / 1 hour before
assert S.issue_time("Forecast5Hour", h("2026-07-02 10")) == h("2026-07-02 05")
assert S.issue_time("Forecast1Hour", h("2026-07-02 10")) == h("2026-07-02 09")
# Baselines use only hours that ended by the issue time
outc = {h("2026-07-02 08"): 100.0, h("2026-07-02 09"): 999.0}
for k in range(1, 29):
    outc[h("2026-07-02 10") - timedelta(days=k)] = 50.0
b = S.baselines(outc, "Forecast1Hour", h("2026-07-02 10"))
assert b["persistence"] == 100.0, b          # 08:00-09:00 ended at the issue time 09:00; 09:00-10:00 had not
assert b["recent"] == 50.0, b                # 28 days before the issue day, same UTC hour
del outc[h("2026-07-01 10")]
for k in range(2, 10):
    del outc[h("2026-07-02 10") - timedelta(days=k)]
assert S.baselines(outc, "Forecast1Hour", h("2026-07-02 10"))["recent"] is None   # 19 of 28 < 20
# Metrics
m = S.metrics([(10.0, 12.0, {"persistence": 14.0, "recent": 11.0}), (20.0, 18.0, {"persistence": 18.0, "recent": 25.0})])
assert m["mae_mw"] == 2.0 and m["bias_mw"] == 0.0 and m["persistence_mae_mw"] == 1.0 and m["persistence_skill"] == -1.0
assert m["recent_won_pct"] == 50.0 and m["persistence_won_pct"] == 0.0   # a tie is not a win
print("all time rules and metrics check out")
