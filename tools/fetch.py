#!/usr/bin/env python3
"""Downloads the forecasts and settled outcomes described in METHOD.md from Energi Data Service.

  data/raw/forecasts_YYYY.csv.gz    Forecasts_Hour: HourUTC, PriceArea, ForecastType, the four scored
                                    forecast columns, ForecastCurrent and TimestampUTC
  data/raw/settlement_YYYY.csv.gz   ProductionConsumptionSettlement: HourUTC, PriceArea and every column
                                    whose name starts with OffshoreWind, OnshoreWind or SolarPower
  data/manifest.json                download time, period, URLs, row counts, column lists, SHA-256

Files are written deterministically (sorted rows, gzip without timestamps), so a re-download of
unchanged data gives identical bytes. Source: Energinet (www.energidataservice.dk), CC BY 4.0.
Standard library only. Runs in GitHub Actions (see .github/workflows/fetch.yml).
"""
import calendar, csv, gzip, hashlib, io, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://api.energidataservice.dk/dataset/"
UA = "kvantixtech/energinet-forecasts (+https://github.com/kvantixtech/energinet-forecasts; validation@kvantix.tech)"
START = date(2019, 11, 1)
F_COLS = ["HourUTC", "PriceArea", "ForecastType", "ForecastDayAhead", "ForecastIntraday", "Forecast5Hour",
          "Forecast1Hour", "ForecastCurrent", "TimestampUTC"]
S_PREFIX = ("OffshoreWind", "OnshoreWind", "SolarPower")


def month_end(y, m):
    return date(y, m, calendar.monthrange(y, m)[1])


def plus_months(d, k):
    y, m = divmod(d.month - 1 + k, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def period_end(today):
    """Last day of the last calendar month that ended at least three months before `today`."""
    y, m = divmod(today.month - 1 - 3, 12)
    last = month_end(today.year + y, m + 1)
    while plus_months(last, 3) > today:
        prev = date(last.year, last.month, 1) - timedelta(days=1)
        last = prev
    return last


def get(dataset, start, end, calls):
    q = urllib.parse.urlencode({"start": start, "end": end, "limit": 0})
    url = API + dataset + "?" + q
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=180) as r:
                body = r.read()
            calls.append(url)
            time.sleep(3)
            return json.loads(body)["records"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(20)
    raise RuntimeError("giving up on " + url)


def months(a, b):
    d = date(a.year, a.month, 1)
    while d <= b:
        n = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        yield d, min(n, b + timedelta(days=1))
        d = n


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)
    return str(v)


def write_gz(path, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    raw = buf.getvalue().encode("utf-8")
    with open(path, "wb") as fh:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0, compresslevel=9) as gz:
            gz.write(raw)
    return hashlib.sha256(open(path, "rb").read()).hexdigest(), len(rows)


def main():
    now = datetime.now(timezone.utc)
    end = period_end(now.date())
    lo, hi = START.isoformat() + "T00:00", (end + timedelta(days=1)).isoformat() + "T00:00"
    calls, fore, sett, s_cols = [], {}, {}, set()
    for a, b in months(START, end):
        # one day of margin on each side, whatever time zone the API applies to start/end; rows are
        # keyed by their UTC hour, so overlaps are de-duplicated and only the period is kept
        s, e = (a - timedelta(days=1)).isoformat() + "T00:00", (b + timedelta(days=1)).isoformat() + "T00:00"
        for r in get("Forecasts_Hour", s, e, calls):
            if lo <= r["HourUTC"][:16] < hi:
                fore[(r["HourUTC"], r["PriceArea"], r["ForecastType"])] = [fmt(r.get(c)) for c in F_COLS]
        for r in get("ProductionConsumptionSettlement", s, e, calls):
            if lo <= r["HourUTC"][:16] < hi:
                cols = sorted(k for k in r if k.startswith(S_PREFIX))
                s_cols.update(cols)
                sett[(r["HourUTC"], r["PriceArea"])] = r
        print(f"{a:%Y-%m}: {len(fore)} forecast rows, {len(sett)} settlement rows so far", flush=True)
    s_cols = sorted(s_cols)
    os.makedirs(os.path.join(ROOT, "data", "raw"), exist_ok=True)
    files = {}
    for y in range(START.year, end.year + 1):
        fr = [v for k, v in sorted(fore.items()) if k[0].startswith(str(y))]
        sr = [[r["HourUTC"], r["PriceArea"]] + [fmt(r.get(c)) for c in s_cols]
              for k, r in sorted(sett.items()) if k[0].startswith(str(y))]
        for name, header, rows in ((f"forecasts_{y}.csv.gz", F_COLS, fr),
                                   (f"settlement_{y}.csv.gz", ["HourUTC", "PriceArea"] + s_cols, sr)):
            sha, n = write_gz(os.path.join(ROOT, "data", "raw", name), header, rows)
            files[name] = {"rows": n, "sha256": sha}
    manifest = {
        "downloaded_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": {"first_hour_utc": lo, "last_hour_utc": end.isoformat() + "T23:00",
                   "rule": "METHOD.md: up to the end of the last calendar month that ended at least three months before the download"},
        "source": "Energinet (www.energidataservice.dk), CC BY 4.0",
        "datasets": {"forecasts": API + "Forecasts_Hour", "outcomes": API + "ProductionConsumptionSettlement"},
        "query": "month by month with one day of margin on each side, limit=0; rows keyed by HourUTC, de-duplicated, and rows outside the period dropped",
        "settlement_columns": s_cols,
        "api_calls": len(calls),
        "files": files,
    }
    json.dump(manifest, open(os.path.join(ROOT, "data", "manifest.json"), "w"), indent=1)
    print(json.dumps({k: manifest[k] for k in ("downloaded_at_utc", "period", "settlement_columns", "api_calls")}, indent=1))
    for k, v in files.items():
        print(f"{k:28} {v['rows']:>8} rows  {v['sha256'][:16]}…")


if __name__ == "__main__":
    sys.exit(main())
