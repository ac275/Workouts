#!/usr/bin/env python3
"""Cabin Log Garmin bridge, v1.1.
Key behaviour: this script ALWAYS writes garmin.json, even when everything
fails, embedding the error text. The app reads that error and shows you the
root cause via Settings > Diagnose Garmin feed - no more silent failures.
Requires repo secrets GARMIN_EMAIL and GARMIN_PASSWORD.
Metrics are fetched independently: one broken endpoint cannot zero the rest.
"""
import json
import os
import sys
import datetime as dt

OUT = "garmin.json"
DAYS = 30


def write(days, error=None):
    payload = {
        "generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error,
        "days": days,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=1)
    msg = "wrote %d day rows" % len(days)
    if error:
        msg += " | ERROR: " + error
    print(msg)


def main():
    email = os.environ.get("GARMIN_EMAIL")
    pw = os.environ.get("GARMIN_PASSWORD")
    if not email or not pw:
        write([], "GARMIN_EMAIL / GARMIN_PASSWORD secrets are not set on the repo "
                  "(Settings > Secrets and variables > Actions)")
        return

    try:
        from garminconnect import Garmin
    except Exception as e:
        write([], "python package garminconnect failed to import: %s "
                  "(check the pip install step in the workflow)" % e)
        return

    try:
        api = Garmin(email, pw)
        api.login()
    except Exception as e:
        write([], "Garmin login failed: %s. If this mentions MFA, CAPTCHA, "
                  "Cloudflare or 429, Garmin is blocking the GitHub runner - "
                  "re-run the workflow later; if it persists, MFA on the "
                  "account is the usual culprit." % e)
        return

    today = dt.date.today()
    rows = {}
    errs = []

    def row(datestr):
        if datestr not in rows:
            rows[datestr] = {"date": datestr}
        return rows[datestr]

    for i in range(DAYS):
        d = today - dt.timedelta(days=i)
        ds = d.isoformat()

        # resting heart rate
        try:
            hr = api.get_rhr_day(ds)
            v = None
            if isinstance(hr, dict):
                metrics = hr.get("allMetrics", {}).get("metricsMap", {})
                lst = metrics.get("WELLNESS_RESTING_HEART_RATE", [])
                if lst:
                    v = lst[0].get("value")
            if v:
                row(ds)["rhr"] = v
        except Exception as e:
            errs.append("rhr %s: %s" % (ds, e))

        # overnight HRV
        try:
            h = api.get_hrv_data(ds)
            v = None
            if isinstance(h, dict):
                s = h.get("hrvSummary") or {}
                v = s.get("lastNightAvg") or s.get("weeklyAvg")
            if v:
                row(ds)["hrv"] = v
        except Exception as e:
            errs.append("hrv %s: %s" % (ds, e))

        # training readiness
        try:
            trd = api.get_training_readiness(ds)
            v = None
            if isinstance(trd, list) and trd:
                v = trd[0].get("score")
            elif isinstance(trd, dict):
                v = trd.get("score")
            if v is not None:
                row(ds)["tr"] = v
        except Exception as e:
            errs.append("tr %s: %s" % (ds, e))

    # weight: one ranged call
    try:
        start = (today - dt.timedelta(days=DAYS)).isoformat()
        w = api.get_body_composition(start, today.isoformat())
        for entry in (w or {}).get("dateWeightList", []) or []:
            ds = entry.get("calendarDate")
            wt = entry.get("weight")
            if ds and wt:
                row(ds)["weight"] = round(wt / 1000.0, 1)
    except Exception as e:
        errs.append("weight: %s" % e)

    days = sorted(rows.values(), key=lambda r: r["date"])
    error = None
    if not days:
        error = ("login OK but every metric call failed - first error: "
                 + (errs[0] if errs else "unknown"))
    elif errs:
        print("partial errors (%d), publishing what succeeded. First: %s"
              % (len(errs), errs[0]))
    write(days, error)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        write([], "unexpected crash: %s" % e)
    sys.exit(0)  # always exit 0 so the workflow's commit step publishes the report
