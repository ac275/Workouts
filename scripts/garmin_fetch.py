"""Fetch weight, resting HR and overnight HRV from Garmin Connect.

Runs in GitHub Actions. Uses the community `garminconnect` library
(unofficial - it can break when Garmin changes things; rerun or update then).
Writes garmin.json at the repo root: [{date, weight, rhr, hrv}, ...] (last 30 days).
"""
import datetime as dt
import json
import os
import sys

from garminconnect import Garmin

EMAIL = os.environ["GARMIN_EMAIL"]
PASSWORD = os.environ["GARMIN_PASSWORD"]
DAYS = 30

def main() -> None:
    api = Garmin(EMAIL, PASSWORD)
    api.login()

    today = dt.date.today()
    rows = {}
    for i in range(DAYS):
        d = today - dt.timedelta(days=i)
        iso = d.isoformat()
        rows[iso] = {"date": iso}

        try:  # resting HR
            hr = api.get_heart_rates(iso)
            v = hr.get("restingHeartRate")
            if v:
                rows[iso]["rhr"] = int(v)
        except Exception as e:
            print("rhr", iso, e, file=sys.stderr)

        try:  # overnight HRV (Garmin 'hrv status' - lastNightAvg, ms)
            hrv = api.get_hrv_data(iso)
            v = (hrv or {}).get("hrvSummary", {}).get("lastNightAvg")
            if v:
                rows[iso]["hrv"] = int(v)
        except Exception as e:
            print("hrv", iso, e, file=sys.stderr)

        try:  # Garmin Training Readiness (0-100)
            tr = api.get_training_readiness(iso)
            if isinstance(tr, list) and tr:
                v = tr[0].get("score")
                if v is not None:
                    rows[iso]["tr"] = int(v)
        except Exception as e:
            print("tr", iso, e, file=sys.stderr)

    try:  # weight (smart scale / manual entries), spread onto their dates
        start = (today - dt.timedelta(days=DAYS)).isoformat()
        wc = api.get_body_composition(start, today.isoformat())
        for entry in (wc or {}).get("dateWeightList", []):
            iso = entry.get("calendarDate")
            grams = entry.get("weight")
            if iso in rows and grams:
                rows[iso]["weight"] = round(grams / 1000.0, 1)
    except Exception as e:
        print("weight", e, file=sys.stderr)

    out = [r for r in rows.values() if len(r) > 1]
    out.sort(key=lambda r: r["date"])
    with open("garmin.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote garmin.json with {len(out)} days")

if __name__ == "__main__":
    main()
