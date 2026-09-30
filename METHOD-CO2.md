# Method, part B: does the green hour hold?

Fixed before the collector saved its first forecast. Changes are listed in `CHANGELOG.md`, with the reason, before the scoring they affect.

## Why part B exists

Energinet's CO₂ forecast (`CO2EmisProg`, g/kWh per 5 minutes for DK1 and DK2) is overwritten as it is updated, and old versions are not kept. A probe on 29 September 2026 fetched the next 12 hours twice, 20 minutes apart, and 71 of 140 future values had changed. So nobody can score yesterday's CO₂ forecast afterwards unless it was saved at the time. Many people use this forecast, directly or through apps, to choose when to charge a car or run a dishwasher.

Part B also checks part A: it saves the wind and solar day-ahead forecasts on the day they are published. That shows whether the values stored in `Forecasts_Hour` are ever changed afterwards.

## What is saved

The collector runs on Kvantix' server. It uses the Python standard library only and works like the [weather test](https://github.com/kvantixtech/weather-forecast-test): every download is saved compressed and locked in a SHA-256 hash chain before it is read, a failed download stays in the chain as a gap, and the head of the chain is published in this repository once a day (`anchors/chain-heads.csv`).

| What | Dataset | When (UTC) |
|---|---|---|
| CO₂ forecast, now to 48 hours ahead, DK1 and DK2 | `CO2EmisProg` | every hour at :07 |
| Wind and solar forecasts, now to 48 hours ahead, including day-ahead for tomorrow | `Forecasts_Hour` | every day at 17:30, which is after the 18:00 Danish time release in both summer and winter |
| CO₂ actuals, last 3 days | `CO2Emis` | every day at 03:37 |
| Wind and solar forecasts as stored, last 3 days (for the revision check) | `Forecasts_Hour` | every day at 03:37 |

Source: Energinet (www.energidataservice.dk), CC BY 4.0. Kvantix is not affiliated with Energinet, and Energinet does not endorse this evaluation.

## Scoring the CO₂ forecast

**Hours:** forecasts and outcomes are averaged over whole UTC hours, from the twelve 5-minute values. An hour with fewer than 12 values in either the forecast or the outcome is not scored.

**Outcome:** `CO2Emis`, the first value we saw. Later changes are logged, not used.

**Lead time:** hour start minus the snapshot time. For each hour and lead time of 1, 3, 6, 12 and 24 hours, we use the latest snapshot saved at least that long before the hour started.

**Baselines,** using only hours that had ended before the snapshot:

1. **Like right now:** the actual value in the last full hour before the snapshot.
2. **Like yesterday:** the actual value at the same UTC hour on the latest day on which that hour had ended before the snapshot.

**Measures:** mean absolute error in g/kWh, bias, skill against each baseline (1 − MAE forecast / MAE baseline), and the share of hours won.

## The green-hours test

This is the question a household actually asks.

1. For each Danish calendar day, take the snapshot saved at 17:30 UTC the day before.
2. Find the **greenest 3-hour window** in the forecast: the three consecutive whole hours with the lowest forecast average.
3. Measure what actually happened in that window, and compare it with:
   - the actual greenest 3-hour window that day
   - the day's actual average
   - the baseline: the window that was actually greenest yesterday, at the same clock hours.

**Measures:**
- g/kWh saved compared with the day's average
- g/kWh above the best possible window
- the share of days on which the forecast window beat the baseline window.

## The revision check (part A's limitation)

For every hour, the day-ahead values saved at 17:30 UTC are compared with the values stored in `Forecasts_Hour` 1–3 days later. A difference of more than 0.01 MW is counted as a revision. The count is published even if it is zero.

## When results are published

Results are published no earlier than 30 days after the first snapshot, marked "Preliminary" until 90 days. The rules above don't change while the collection runs.
