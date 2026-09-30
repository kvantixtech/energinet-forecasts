"""Offline test of kvx_energy.py with saved responses. Run: python3 tests/test_collector.py"""
import gzip, json, os, shutil, sqlite3, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")
PY = [sys.executable, os.path.join(ROOT, "kvx_energy.py")]


def run(d, *args, fixtures=FX):
    env = dict(os.environ, KVX_ENERGY_CONFIG=os.path.join(d, "none.json"))
    return subprocess.run(PY + ["--fixtures", fixtures, "--data-dir", d, *args], capture_output=True, text=True, env=env)


d = tempfile.mkdtemp()
try:
    for c in ("collect", "dayahead", "observe"):
        r = run(d, c)
        assert r.returncode == 0, (c, r.stdout, r.stderr)
    con = sqlite3.connect(os.path.join(d, "energy.sqlite3"))
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM co2_forecast").fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM co2_actual").fetchone()[0] == 4
    assert con.execute("SELECT COUNT(*) FROM wind_forecast WHERE kind='forecast'").fetchone()[0] == 6
    assert run(d, "verify").returncode == 0

    # A corrected actual: the first value is kept and the correction logged
    fx2 = tempfile.mkdtemp()
    shutil.copytree(FX, fx2, dirs_exist_ok=True)
    j = json.load(open(os.path.join(fx2, "CO2Emis.json")))
    j["records"][0]["CO2Emission"] += 5
    json.dump(j, open(os.path.join(fx2, "CO2Emis.json"), "w"))
    assert run(d, "observe", fixtures=fx2).returncode == 0
    first = j["records"][0]["CO2Emission"] - 5
    t = j["records"][0]["Minutes5UTC"][:16] + ":00Z"
    assert con.execute("SELECT value FROM co2_actual WHERE area=? AND t=?", (j["records"][0]["PriceArea"], t)).fetchone()[0] == first
    assert con.execute("SELECT COUNT(*) FROM co2_revisions").fetchone()[0] == 1

    # A failed download stays in the chain as a gap
    fx3 = tempfile.mkdtemp()
    open(os.path.join(fx3, "CO2EmisProg.json"), "wb").write(b"HTTP 429\nbusy")
    r = run(d, "collect", fixtures=fx3)
    assert r.returncode == 1 and "FAILED" in r.stdout
    assert con.execute("SELECT error FROM runs ORDER BY id DESC LIMIT 1").fetchone()[0] == "HTTP 429"
    assert run(d, "verify").returncode == 0

    # Changing a saved raw file breaks verification
    raw = con.execute("SELECT raw_path FROM runs WHERE raw_path IS NOT NULL LIMIT 1").fetchone()[0]
    with gzip.open(os.path.join(d, raw), "wb") as fh:
        fh.write(b'{"records": []}')
    r = run(d, "verify")
    assert r.returncode == 1 and "raw file changed" in r.stdout

    # The anchor tool reads the same chain
    out = os.path.join(d, "head.json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "anchor.py"), "snapshot", "--db", os.path.join(d, "energy.sqlite3"),
                        "--code", os.path.join(ROOT, "kvx_energy.py"), "--out", out], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    snap = json.load(open(out))
    assert snap["runs"] == 7 and snap["chain_ok"] == "true", snap   # the chain itself is intact; the raw file check is verify's job
    print("collector: chain, gaps, revisions, tamper detection and anchor snapshot all check out")
finally:
    shutil.rmtree(d, ignore_errors=True)
