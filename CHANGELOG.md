# Changelog

`METHOD.md` was committed before any data was downloaded (commit `6b62c8f`). Entries below record how the rules were applied where the method did not say. Each is committed before the scoring it affects is run.

## 2026-09-30: how the rules are applied (before the first scoring run)

1. **Intraday is scored only from its issue time.** Energinet describes `ForecastIntraday` as issued at 06:00 Danish time for the same day. Hours from midnight to 06:00 Danish time are before that issue time, so they are not forecasts and are not scored. (In the sample rows seen by the probe, the intraday value for those early hours was identical to `ForecastCurrent`.) The same rule is written into `tools/score.py` as `scored()`, and it also limits the common hours.
2. **"Last full hour before the forecast was issued"** is the hour that ended at or before the issue time. All issue times are whole hours, so for the 1-hour forecast of 10:00–11:00 it is 08:00–09:00.
3. **The 28-day average needs at least 20 of its 28 values.** With fewer, the "like recently" baseline is left empty for that hour, and the hour doesn't count in that baseline's skill or hours won. The forecast's own error still counts.
4. **Solar at night, for common hours.** An hour is left out of the solar common hours when the outcome and all four forecasts are 0.
5. **A missing settlement column counts as 0 if the others for the same type are present.** For example, a size class of solar panels with no value in an early year. If every column for a type is empty, the outcome is missing and the hour is not scored.
