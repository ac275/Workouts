#!/usr/bin/env python3
"""Cabin Log Garmin fetch v2 — always writes garmin.json, never dies silently.
Auth order: GARTH_TOKEN secret (survives Garmin MFA) then GARMIN_EMAIL/PASSWORD.
Output: {"generated": iso8601, "error": str|null, "auth": "token|password", "days": [...]}
"""
import base64, datetime as dt, json, os, sys, traceback

OUT = "garmin.json"
DAYS = 30

def write(payload):
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    print("wrote", OUT, "| error:", payload.get("error"), "| days:", len(payload.get("days", [])))

result = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "error": None, "auth": None, "days": []}
try:
    from garminconnect import Garmin
    g = None
    tok = os.environ.get("GARTH_TOKEN", "").strip()
    if tok:
        try:
            import garth
            garth.client.loads(base64.b64decode(tok).decode())
            g = Garmin()
            g.garth = garth.client
            g.display_name = garth.client.username
            result["auth"] = "token"
        except Exception as e:
            result["auth"] = f"token failed ({e.__class__.__name__}: {e}); trying password"
            g = None
    if g is None:
        email, pw = os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD")
        if not email or not pw:
            raise RuntimeError("no GARTH_TOKEN and GARMIN_EMAIL/GARMIN_PASSWORD secrets missing")
        g = Garmin(email, pw)
        g.login()
        result["auth"] = (result["auth"] or "") + "password"
    today = dt.date.today()
    days = []
    for i in range(DAYS - 1, -1, -1):
        d = today - dt.timedelta(days=i)
        iso = d.isoformat()
        row = {"date": iso}
        try:
            s = g.get_stats(iso) or {}
            if s.get("restingHeartRate") is not None: row["rhr"] = s["restingHeartRate"]
        except Exception as e: row.setdefault("_err", []).append(f"stats:{e.__class__.__name__}")
        try:
            h = g.get_hrv_data(iso) or {}
            v = (h.get("hrvSummary") or {}).get("lastNightAvg")
            if v is not None: row["hrv"] = v
        except Exception as e: row.setdefault("_err", []).append(f"hrv:{e.__class__.__name__}")
        try:
            t = g.get_training_readiness(iso)
            if isinstance(t, list) and t: t = t[0]
            v = (t or {}).get("score")
            if v is not None: row["tr"] = v
        except Exception as e: row.setdefault("_err", []).append(f"tr:{e.__class__.__name__}")
        try:
            w = g.get_body_composition(iso) or {}
            arr = (w.get("dateWeightList") or [])
            if arr and arr[0].get("weight"): row["weight"] = round(arr[0]["weight"] / 1000.0, 1)
        except Exception as e: row.setdefault("_err", []).append(f"wt:{e.__class__.__name__}")
        days.append(row)
    result["days"] = days
except Exception:
    result["error"] = traceback.format_exc(limit=2).strip().splitlines()[-1]
write(result)
sys.exit(0)
