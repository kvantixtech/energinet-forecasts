# How good is Denmark's wind and solar forecast?

Energinet publishes forecasts of wind and solar power for each Danish price area: the day before, the same morning, 5 hours before and 1 hour before. This repository checks those forecasts against the settled production, and against simple rules that use only what was known at the time.

**Status: first scoring run, 30 September 2026. Not yet interpreted on the website.** The rules are in [`METHOD.md`](METHOD.md), committed before any data was fetched. How they were applied is in [`CHANGELOG.md`](CHANGELOG.md). Full tables: [`results/summary.md`](results/summary.md), by year and quarter in [`results/scores.csv`](results/scores.csv).

**Read the bias column before the skill columns.** In some years, the published forecast sat far below the settled production (DK2 offshore 2021–2022, DK1 offshore from 2024). In those years the baselines, which are built from settled production, have an advantage. See changelog entry 6.

Part of the Kvantix [Data Playground](https://kvantix.tech/playground/). Same method as the [weather forecast test](https://github.com/kvantixtech/weather-forecast-test) and [expert-forecasts](https://github.com/kvantixtech/expert-forecasts): lock it, measure it against data nobody controls, compare it with a lazy guess.

## Part B: does the green hour hold?

Energinet's CO₂ forecast is overwritten as it is updated, so it can only be scored if someone saves it at the time. From October 2026 the collector [`kvx_energy.py`](kvx_energy.py) saves it every hour. It also saves the wind and solar forecasts every evening, which checks part A's one blind spot: whether stored forecasts are ever changed afterwards. Every download is hash-chained, and the chain head is published daily in [`anchors/`](anchors/). The rules are in [`METHOD-CO2.md`](METHOD-CO2.md), fixed before the first snapshot. The collector's SHA-256 is in [`METHOD.lock`](METHOD.lock). Live status of the collector: [kvantix.tech/playground/energy](https://kvantix.tech/playground/energy/).

## Data and licence

Source: Energinet (www.energidataservice.dk), CC BY 4.0. Kvantix is not affiliated with Energinet, and Energinet does not endorse this evaluation.

Code: MIT. Compiled tables: CC BY 4.0, credit "Kvantix energinet-forecasts".
