#!/usr/bin/env python3
"""One-off diagnostic to inspect Yahoo YTSL.NE early daily bars. No source mutations."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import requests

url = "https://query1.finance.yahoo.com/v8/finance/chart/YTSL.NE"
p1 = int(datetime(2022, 12, 19, tzinfo=timezone.utc).timestamp())
p2 = int(datetime(2023, 1, 7, tzinfo=timezone.utc).timestamp())
session = requests.Session()
try:
    response = session.get(url, params={"period1":p1,"period2":p2,"interval":"1d","events":"history"},
                           timeout=22, headers={"User-Agent":"Mozilla/5.0"})
    print("Yahoo URL:", response.url)
    print("Yahoo HTTP:", response.status_code)
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart") or {}).get("result") or []
    if not result: raise ValueError("Empty chart result: " + str((payload.get("chart") or {}).get("error")))
    x=result[0]
    tz=ZoneInfo(x["meta"].get("exchangeTimezoneName","America/Toronto"))
    q=x["indicators"]["quote"][0]
    adj=(x["indicators"].get("adjclose") or [{}])[0].get("adjclose",[])
    for i, timestamp in enumerate(x.get("timestamp",[])):
        date=datetime.fromtimestamp(timestamp,tz).date().isoformat()
        print(json.dumps({"date":date,"open":q["open"][i],"high":q["high"][i],"low":q["low"][i],
             "close":q["close"][i],"adj_close": adj[i] if len(adj)>i else None,
             "volume":q["volume"][i]}))
except Exception as exc:
    print("Yahoo probe failed:",type(exc).__name__,str(exc))
    if "response" in locals() and not response.ok: print(response.text[:700])
