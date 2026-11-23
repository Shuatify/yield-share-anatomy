#!/usr/bin/env python3
"""Temporary one-shot research-only Yahoo Chart API diagnostics."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import requests

url = "https://query1.finance.yahoo.com/v8/finance/chart/YTSL.NE"
p1 = int(datetime(2026, 6, 18, tzinfo=timezone.utc).timestamp())
p2 = int(datetime(2026, 11, 5, tzinfo=timezone.utc).timestamp())
q = {"period1":p1,"period2":p2,"interval":"1d","events":"history"}
res = requests.get(url, params=q, timeout=25, headers={"User-Agent":"Mozilla/5.0"})
print("Yahoo chart URL:",res.url)
print("Yahoo status:",res.status_code)
res.raise_for_status()
doc = res.json()["chart"]
result=(doc.get("result") or [])[0]
meta=result.get("meta") or {}
print("Yahoo meta:",json.dumps({k:meta.get(k) for k in ("currency","symbol","exchangeName","exchangeTimezoneName","instrumentType")},ensure_ascii=False))
tz = ZoneInfo(meta.get("exchangeTimezoneName","America/Toronto"))
bars=result["indicators"]["quote"][0]
target_dates={"2026-06-22","2026-06-23","2026-06-24","2026-10-30","2026-11-02","2026-11-03"}
found=set()
for i,t in enumerate(result.get("timestamp") or []):
    date=datetime.fromtimestamp(t,tz=tz).date().isoformat()
    if date not in target_dates:continue
    found.add(date)
    print(json.dumps({"date":date,"open":bars["open"][i],"high":bars["high"][i],
      "low":bars["low"][i],"close":bars["close"][i],"volume":bars["volume"][i]}))
print("Dates missing from Yahoo query:", sorted(target_dates-found))
