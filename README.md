# How good is Denmark's wind and solar forecast?

Energinet publishes forecasts of wind and solar power for each Danish price area: the day before, the same morning, 5 hours before and 1 hour before. This repository checks those forecasts against the settled production, and against simple rules that use only what was known at the time.

**Status: method fixed, data not yet downloaded.** The rules are in [`METHOD.md`](METHOD.md), committed before any data was fetched.

Part of the Kvantix [Data Playground](https://kvantix.tech/playground/). Same method as the [weather forecast test](https://github.com/kvantixtech/weather-forecast-test) and [expert-forecasts](https://github.com/kvantixtech/expert-forecasts): lock it, measure it against data nobody controls, compare it with a lazy guess.

## Data and licence

Source: Energinet (www.energidataservice.dk), CC BY 4.0. Kvantix is not affiliated with Energinet, and Energinet does not endorse this evaluation.

Code: MIT. Compiled tables: CC BY 4.0, credit "Kvantix energinet-forecasts".
