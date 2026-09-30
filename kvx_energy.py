#!/usr/bin/env python3
"""kvx_energy.py: Kvantix energy forecast collector (part B of energinet-forecasts, see METHOD-CO2.md).

Saves Energinet's CO2 forecast every hour, the wind and solar forecasts every evening, and the CO2
actuals every night. Every download is saved compressed and locked in a SHA-256 hash chain BEFORE it
is read, exactly like the weather test. Standard library only; touches nothing else on the server.

    kvx_energy.py probe              fetch once from each dataset and show what was read (no saving)
    kvx_energy.py collect            CO2 forecast, now to +48 h                    (timer: hourly at :07)
    kvx_energy.py dayahead           wind/solar forecasts, now to +48 h            (timer: daily 17:30 UTC)
    kvx_energy.py observe            CO2 actuals + stored wind/solar, last 3 days  (timer: daily 03:37 UTC)
    kvx_energy.py verify             recompute the hash chain and every raw file's SHA-256
    kvx_energy.py status [--json]    counts, last downloads, chain state

Source: Energinet (www.energidataservice.dk), CC BY 4.0. No API key; no personal data.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.0"
UTC = timezone.utc
API = "https://api.energidataservice.dk/dataset/"
CONFIG_PATH = os.environ.get("KVX_ENERGY_CONFIG", "/etc/kvx-energy/config.json")
DEFAULT_CONFIG = {
    "data_dir": "/var/lib/kvx-energy",
    "user_agent": "kvantix-energy/1.0 (https://kvantix.tech; validation@kvantix.tech)",
}
AREAS = ("DK1", "DK2")
FIXTURES = None  # set by --fixtures (offline tests): folder with saved responses named <dataset>.json

# What each command downloads: (kind, dataset, start, end). "now" is Energi Data Service's dynamic time.
JOBS = {
    "collect": [("forecast", "CO2EmisProg", "now-P0DT1H", "now+P2D")],
    "dayahead": [("forecast", "Forecasts_Hour", "now", "now+P2D")],
    "observe": [("observation", "CO2Emis", "now-P3D", "now"), ("stored", "Forecasts_Hour", "now-P3D", "now")],
}


# ------------------------------------------------------------ util

def now_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    return cfg


def url_for(dataset: str, start: str, end: str) -> str:
    q = {"start": start, "end": end, "filter": json.dumps({"PriceArea": list(AREAS)}, separators=(",", ":")), "limit": 0}
    return API + dataset + "?" + urllib.parse.urlencode(q)


def http_get(url: str, cfg: dict, dataset: str, waits=(20, 60, 120)) -> tuple[int, bytes]:
    """GET with an identifying User-Agent. On 429/5xx wait (Retry-After if given) and retry."""
    if FIXTURES is not None:
        path = os.path.join(FIXTURES, dataset + ".json")
        if os.path.exists(path):
            data = open(path, "rb").read()
            if data.startswith(b"HTTP "):
                return int(data[5:8]), data
            return 200, data
        return 404, b""
    req = urllib.request.Request(url, headers={"User-Agent": cfg["user_agent"], "Accept": "application/json"})
    status, body = 0, b""
    for attempt in range(len(waits) + 1):
        retry_after = None
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            status, body = e.code, (e.read() if hasattr(e, "read") else b"")
            ra = e.headers.get("Retry-After") if e.headers else None
            retry_after = int(ra) if ra and ra.strip().isdigit() else None
            if e.code not in (429, 500, 502, 503, 504):
                return status, body
        except (urllib.error.URLError, TimeoutError, OSError):
            status, body = 0, b""
        if attempt < len(waits):
            time.sleep(min(300, retry_after if retry_after is not None else waits[attempt]))
    return status, body


# ------------------------------------------------------------ database + hash chain (same as the weather test)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,              -- forecast / observation / stored
  source TEXT NOT NULL,            -- dataset name
  location TEXT NOT NULL,          -- 'DK1+DK2'
  fetched_at TEXT NOT NULL,
  http_status INTEGER,
  url TEXT,
  payload_sha256 TEXT,
  raw_path TEXT,
  n_rows INTEGER DEFAULT 0,
  error TEXT,
  parse_error TEXT,
  prev_hash TEXT NOT NULL,
  chain_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS co2_forecast (
  run_id INTEGER NOT NULL, area TEXT NOT NULL, t TEXT NOT NULL, value REAL NOT NULL,
  PRIMARY KEY (run_id, area, t)
);
CREATE TABLE IF NOT EXISTS co2_actual (
  area TEXT NOT NULL, t TEXT NOT NULL, value REAL NOT NULL, run_id INTEGER NOT NULL,
  PRIMARY KEY (area, t)
);
CREATE TABLE IF NOT EXISTS co2_revisions (area TEXT, t TEXT, old_value REAL, new_value REAL, run_id INTEGER, seen_at TEXT);
CREATE TABLE IF NOT EXISTS wind_forecast (
  run_id INTEGER NOT NULL, kind TEXT NOT NULL, area TEXT NOT NULL, type TEXT NOT NULL, hour TEXT NOT NULL,
  dayahead REAL, intraday REAL, h5 REAL, h1 REAL, current REAL,
  PRIMARY KEY (run_id, area, type, hour)
);
"""
GENESIS = "0" * 64
CHAIN_FIELDS = ("kind", "source", "location", "fetched_at", "http_status", "url", "payload_sha256", "n_rows", "error")


def db_connect(cfg) -> sqlite3.Connection:
    os.makedirs(cfg["data_dir"], exist_ok=True)
    con = sqlite3.connect(os.path.join(cfg["data_dir"], "energy.sqlite3"))
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def chain_hash(prev: str, fields: dict) -> str:
    rec = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev + "|" + rec).encode()).hexdigest()


def add_run(con, cfg, *, kind, source, fetched_at, status, url, payload: bytes, error=None) -> int:
    """Saves the raw response compressed and adds it to the hash chain BEFORE anything is read from it."""
    sha = hashlib.sha256(payload).hexdigest() if payload else None
    raw_path = None
    if payload:
        rel = os.path.join("raw", fetched_at[:10], f"{fetched_at.replace(':', '')}_{kind}_{source}_{sha[:12]}.json.gz")
        full = os.path.join(cfg["data_dir"], rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if not os.path.exists(full):
            with gzip.open(full, "wb") as fh:
                fh.write(payload)
        raw_path = rel
    prev = con.execute("SELECT chain_hash FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    prev = prev[0] if prev else GENESIS
    fields = {"kind": kind, "source": source, "location": "DK1+DK2", "fetched_at": fetched_at, "http_status": status,
              "url": url, "payload_sha256": sha, "n_rows": 0, "error": error}
    h = chain_hash(prev, fields)
    cur = con.execute(
        "INSERT INTO runs (kind, source, location, fetched_at, http_status, url, payload_sha256, raw_path, n_rows, error,"
        " prev_hash, chain_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (kind, source, "DK1+DK2", fetched_at, status, url, sha, raw_path, 0, error, prev, h))
    with open(os.path.join(cfg["data_dir"], "chain.log"), "a", encoding="utf-8") as fh:
        fh.write(f"{cur.lastrowid}\t{fetched_at}\t{kind}\t{source}\t{sha or '-'}\t{h}\n")
    return cur.lastrowid


def verify_chain(con, cfg) -> tuple[bool, list[str]]:
    problems, prev = [], GENESIS
    for r in con.execute(f"SELECT id, prev_hash, chain_hash, raw_path, {', '.join(CHAIN_FIELDS)} FROM runs ORDER BY id"):
        rid, p, h, raw_path = r[0], r[1], r[2], r[3]
        fields = dict(zip(CHAIN_FIELDS, r[4:]))
        fields["n_rows"] = 0
        if p != prev:
            problems.append(f"run {rid}: prev_hash does not match")
        if chain_hash(p, fields) != h:
            problems.append(f"run {rid}: chain_hash does not match")
        if raw_path:
            try:
                with gzip.open(os.path.join(cfg["data_dir"], raw_path), "rb") as fh:
                    if hashlib.sha256(fh.read()).hexdigest() != fields["payload_sha256"]:
                        problems.append(f"run {rid}: raw file changed ({raw_path})")
            except OSError:
                problems.append(f"run {rid}: raw file missing ({raw_path})")
        prev = h
    return (not problems), problems


# ------------------------------------------------------------ parsing (pure: bytes -> rows)

def records(payload: bytes) -> list[dict]:
    j = json.loads(payload)
    if not isinstance(j, dict) or not isinstance(j.get("records"), list):
        raise ValueError("no 'records' list in the response")
    return j["records"]


def utc_key(s: str) -> str:
    return s[:16] + ":00Z" if len(s) >= 16 else s


def store(con, run_id, kind, dataset, payload, fetched_at) -> int:
    recs = records(payload)
    n = 0
    if dataset == "CO2EmisProg":
        for r in recs:
            if r.get("PriceArea") in AREAS and r.get("CO2Emission") is not None:
                con.execute("INSERT OR IGNORE INTO co2_forecast VALUES (?,?,?,?)",
                            (run_id, r["PriceArea"], utc_key(r["Minutes5UTC"]), float(r["CO2Emission"])))
                n += 1
    elif dataset == "CO2Emis":
        for r in recs:
            if r.get("PriceArea") not in AREAS or r.get("CO2Emission") is None:
                continue
            area, t, v = r["PriceArea"], utc_key(r["Minutes5UTC"]), float(r["CO2Emission"])
            old = con.execute("SELECT value FROM co2_actual WHERE area=? AND t=?", (area, t)).fetchone()
            if old is None:
                con.execute("INSERT INTO co2_actual VALUES (?,?,?,?)", (area, t, v, run_id))
            elif abs(old[0] - v) > 1e-9:  # first value is kept; the correction is logged
                con.execute("INSERT INTO co2_revisions VALUES (?,?,?,?,?,?)", (area, t, old[0], v, run_id, fetched_at))
            n += 1
    elif dataset == "Forecasts_Hour":
        f = lambda x: None if x is None else float(x)
        for r in recs:
            if r.get("PriceArea") not in AREAS:
                continue
            con.execute("INSERT OR IGNORE INTO wind_forecast VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (run_id, kind, r["PriceArea"], r["ForecastType"], utc_key(r["HourUTC"]), f(r.get("ForecastDayAhead")),
                         f(r.get("ForecastIntraday")), f(r.get("Forecast5Hour")), f(r.get("Forecast1Hour")), f(r.get("ForecastCurrent"))))
            n += 1
    return n


# ------------------------------------------------------------ commands

def run_job(con, cfg, job, quiet=False) -> int:
    failures = 0
    for kind, dataset, start, end in JOBS[job]:
        url = url_for(dataset, start, end)
        fetched_at = iso(now_utc())
        status, payload = http_get(url, cfg, dataset)
        ok = status == 200 and payload
        with con:
            rid = add_run(con, cfg, kind=kind, source=dataset, fetched_at=fetched_at, status=status, url=url,
                          payload=payload if ok else b"", error=None if ok else f"HTTP {status}")
        if not ok:
            failures += 1
            if not quiet:
                print(f"{dataset:15} FAILED http {status} (kept in the chain as a gap, run {rid})")
            continue
        try:
            with con:
                n = store(con, rid, kind, dataset, payload, fetched_at)
                con.execute("UPDATE runs SET n_rows=? WHERE id=?", (n, rid))
        except (ValueError, KeyError, TypeError) as e:
            with con:
                con.execute("UPDATE runs SET parse_error=? WHERE id=?", (str(e)[:300], rid))
            failures += 1
            n = 0
        if not quiet:
            print(f"{dataset:15} http {status}  {len(payload):>8} bytes  {n:>5} rows  run {rid}")
    return 1 if failures else 0


def status(con, cfg, as_json=False) -> int:
    ok, problems = verify_chain(con, cfg)
    last = con.execute("SELECT id, fetched_at, chain_hash FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    by_source = {s: {"runs": n, "failed": f, "last": t} for s, n, f, t in con.execute(
        "SELECT source || ':' || kind, COUNT(*), SUM(error IS NOT NULL OR parse_error IS NOT NULL), MAX(fetched_at) FROM runs GROUP BY 1")}
    out = {"version": VERSION, "chain_ok": ok, "runs": con.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
           "last_run_id": last[0] if last else None, "last_fetched_at": last[1] if last else None,
           "chain_head": last[2] if last else GENESIS, "by_source": by_source,
           "co2_forecast_values": con.execute("SELECT COUNT(*) FROM co2_forecast").fetchone()[0],
           "co2_actual_values": con.execute("SELECT COUNT(*) FROM co2_actual").fetchone()[0],
           "co2_revisions": con.execute("SELECT COUNT(*) FROM co2_revisions").fetchone()[0],
           "problems": problems[:20]}
    if as_json:
        print(json.dumps(out, indent=1))
    else:
        print(f"kvx_energy {VERSION} · runs {out['runs']} · chain {'intact' if ok else 'BROKEN'} · last {out['last_fetched_at']}")
        for s, v in sorted(by_source.items()):
            print(f"  {s:32} {v['runs']:>5} runs  {v['failed'] or 0:>3} failed  last {v['last']}")
        print(f"  CO2 forecast values {out['co2_forecast_values']}, actual values {out['co2_actual_values']}, "
              f"revisions {out['co2_revisions']}")
        for p in problems[:20]:
            print("  PROBLEM:", p)
    return 0 if ok else 1


def probe(cfg) -> int:
    rc = 0
    for job in ("collect", "dayahead", "observe"):
        for kind, dataset, start, end in JOBS[job]:
            status_, payload = http_get(url_for(dataset, start, end), cfg, dataset)
            try:
                recs = records(payload) if status_ == 200 else []
                sample = recs[0] if recs else None
                print(f"{job:9} {dataset:15} http {status_}  {len(recs):>5} rows  first: {json.dumps(sample)[:160]}")
            except ValueError as e:
                print(f"{job:9} {dataset:15} http {status_}  could not read: {e}")
                rc = 1
            if status_ != 200:
                rc = 1
    return rc


def main(argv=None) -> int:
    global FIXTURES
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixtures", help="offline test: read saved responses from this folder")
    ap.add_argument("--data-dir", help="override data_dir (tests)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("probe", "collect", "dayahead", "observe", "verify"):
        sub.add_parser(c)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    FIXTURES = a.fixtures
    cfg = load_config()
    if a.data_dir:
        cfg["data_dir"] = a.data_dir
    if a.cmd == "probe":
        return probe(cfg)
    con = db_connect(cfg)
    if a.cmd in JOBS:
        return run_job(con, cfg, a.cmd)
    if a.cmd == "verify":
        ok, problems = verify_chain(con, cfg)
        print("chain intact" if ok else "CHAIN BROKEN:\n  " + "\n  ".join(problems))
        return 0 if ok else 1
    if a.cmd == "status":
        return status(con, cfg, a.json)
    return 2


if __name__ == "__main__":
    sys.exit(main())
