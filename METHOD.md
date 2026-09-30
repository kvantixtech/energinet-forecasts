# Method: how good is Denmark's wind and solar forecast?

Fixed before the data was downloaded. To learn the column names, a probe had earlier read the dataset descriptions and a few sample rows (one day for DK1, and the newest and oldest rows); no score was computed. The forecasts and outcomes are already history, so this can't prove we didn't know them. What it does prove is that the rules were not tuned afterwards. Every later change is listed in `CHANGELOG.md` with the reason, and it is committed before the scoring it affects.

## Question

Energinet, the Danish transmission system operator, publishes forecasts of wind and solar power production for each price area several times before each hour. How close were they to what was actually produced, how much do they improve as the hour approaches, and do they beat simple rules that use only what was known when the forecast was issued?

## Data

Source: Energi Data Service (Energinet), licensed CC BY 4.0. Source: Energinet (www.energidataservice.dk). Kvantix is not affiliated with Energinet, and Energinet does not endorse this evaluation.

**Forecasts:** dataset `Forecasts_Hour`, one row per hour (UTC), price area and forecast type. Four columns are scored, each a separate forecast horizon:

| Column | Issued (as described by Energinet) | Short name |
|---|---|---|
| `ForecastDayAhead` | 18:00 Danish time the day before | day-ahead |
| `ForecastIntraday` | 06:00 Danish time the same day | intraday |
| `Forecast5Hour` | 5 hours before the hour | 5 hours |
| `Forecast1Hour` | 1 hour before the hour | 1 hour |

`ForecastCurrent` is not scored: it is made during or at the start of the hour itself.

**Series:** 2 price areas (DK1, DK2) × 3 types (offshore wind, onshore wind, solar) = 6 series.

**Outcomes:** dataset `ProductionConsumptionSettlement` (settled production, MWh per hour, which equals average MW over the hour):

- offshore wind: the sum of all columns whose names start with `OffshoreWind`
- onshore wind: the sum of all columns whose names start with `OnshoreWind`
- solar: the sum of all columns whose names start with `SolarPower`

The column list is recorded when the data is downloaded.

**Period:** hours from 2019-11-01 00:00 UTC up to the end of the last calendar month that ended at least three months before the download. Energinet corrects settled data for up to three months, and the gap keeps the outcomes stable. The download date and the resulting end of the period are recorded.

All times are UTC, so daylight saving time never creates a missing or duplicated hour.

## Baselines: what anyone could have guessed at the time

Both baselines use only outcomes from hours that had ended before the forecast was issued. The issue times in the table above are used for that; for day-ahead and intraday, 18:00 and 06:00 Danish time are converted to UTC for each date.

1. **Persistence ("like right now"):** the production in the last full hour before the forecast was issued, repeated.
2. **Recent average for that hour ("like recently"):** the average production at the same UTC hour of day over the 28 complete UTC days before the day of issue.

We use settled outcomes for the baselines, which are more accurate than the real-time measurements available at the time. That favours the baselines, not the forecast.

## Scoring

For each series, horizon and baseline:

- **MAE:** mean absolute error in MW.
- **Normalised MAE:** MAE divided by the mean actual production over the same hours, in per cent.
- **Bias:** mean of (forecast − outcome), in MW.
- **Skill:** 1 − MAE(forecast) / MAE(baseline). A positive value means the forecast was better than the baseline.
- **Hours won:** the share of hours in which the forecast was closer than the baseline. Ties are not counted as won.

Two sets of hours are used:

- **All available hours** for each horizon: every hour where that forecast and the outcome exist.
- **Common hours** for comparing horizons: hours where all four forecasts and the outcome exist. The claim "the forecast improves as the hour approaches" is judged on common hours only.

**Solar at night:** hours where both the forecast and the outcome are 0 are left out of the solar scores. Otherwise the night hours would make every solar forecast look almost perfect.

**Splits,** shown alongside the full period: calendar year, and quarter of the year.

A missing forecast value is never filled in. The number of hours with a missing forecast is reported for each series and horizon.

## Bias, and what it can and can't mean

The forecasts and the settled outcomes may not cover exactly the same plants. For example, the settlement includes solar panels whose production is used on site. A constant difference in coverage shows up as bias. So we report bias but don't read a small bias as a forecasting error. Comparisons between horizons and against the baselines are not affected, because every horizon is scored against the same outcomes.

## What this can't show

We score the forecasts as they are stored in `Forecasts_Hour` today. We can't prove that stored values were never revised after they were issued. A collector that saves the day-ahead forecasts on the day they are published, hash-chained, is part of this project. Once it has run for a while, it will show whether later stored values match. Until then, this limitation is stated next to every result.

This evaluates published numbers against published numbers. It is not a judgement of Energinet's forecasting staff or systems, which serve purposes (balancing, trading) that a mean error doesn't capture.
