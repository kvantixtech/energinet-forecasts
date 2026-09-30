# Changelog

`METHOD.md` was committed before any data was downloaded (commit `6b62c8f`). Entries below record how the rules were applied where the method did not say, or where the data showed that a rule could not be applied as written. Each is committed before the scoring it affects is run.

## 2026-09-30: how the rules are applied (before the first scoring run)

1. **Intraday is treated as issued at 08:00 Danish time, not 06:00, and scored from the 09:00 hour.** `METHOD.md` took the issue time, 06:00 Danish time, from Energinet's description of `ForecastIntraday`. The downloaded data shows something else. For wind, the stored intraday value is identical to `ForecastCurrent`, the forecast made at the start of the hour itself:
   - for every hour starting before 08:00 Danish time, summer and winter alike
   - for about half of the hours starting at 08:00
   - for none of the hours from 09:00.

   Before 08:00 the stored value is therefore not a forecast made in advance. So, before any score was computed:
   - intraday is treated as issued at 08:00 Danish time, which is what the baselines use
   - it is scored only for hours starting at 09:00 Danish time or later.

   The check that found this compared the two stored columns hour by hour. It computed no error or score. Solar is left out of the check, because both values are 0 at night.
2. **"Last full hour before the forecast was issued"** is the hour that ended at or before the issue time. All issue times are whole hours, so for the 1-hour forecast of 10:00–11:00 it is 08:00–09:00.
3. **The 28-day average needs at least 20 of its 28 values.** With fewer, the "like recently" baseline is left empty for that hour, and the hour doesn't count in that baseline's skill or hours won. The forecast's own error still counts.
4. **Solar at night, for common hours.** An hour is left out of the solar common hours when the outcome and all four forecasts are 0.
5. **A missing settlement column counts as 0 if the others for the same type are present.** For example, a size class of solar panels with no value in an early year. If every column for a type is empty, the outcome is missing and the hour is not scored.

## 2026-09-30: after the first scoring run

6. **Correction to METHOD.md, "Bias, and what it can and can't mean".** The method says a difference in coverage between forecasts and settled outcomes does not affect the comparisons with the baselines. That is wrong. Both baselines are built from the settled outcomes, so they include everything the settlement includes. If the forecast leaves out plants that the settlement includes, the baselines get an advantage the forecast can't have. The first scoring run shows large negative biases in some series and years, for example DK2 offshore in 2021–2022 and DK1 offshore from 2024. In exactly those years, "like right now" beats the 1-hour forecast. We do not know the cause. Missing plants are one explanation the data is consistent with, but it is not established. So the results are shown by year next to the full period, and the pages say this plainly. The scoring itself is unchanged. Comparisons between horizons are still not affected, because all horizons are scored against the same outcomes.
