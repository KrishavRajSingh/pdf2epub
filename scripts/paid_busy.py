#!/usr/bin/env python3
"""Print the visitor ids with a paid conversion still running, read from conversions.log lines on stdin.

A paid job is running when a `start` event with paid=true from the last MAX_MIN minutes has no
result line (ok/err) from the same visitor after it. deploy-vps.sh waits while this prints anything,
because a restart kills the job and the buyer's page moves on to the next book (11-19, 11-24).
Usage: tail -n 4000 conversions.log | python3 scripts/paid_busy.py [now-iso]
"""
import json, sys
from datetime import datetime, timedelta, timezone

MAX_MIN = 20  # longest paid book seen ~12 min; older starts with no result are dead jobs, not running ones


def busy(lines, now):
    open_jobs = {}  # visitor -> start time of a paid job with no result yet
    for line in lines:
        try:
            r = json.loads(line)
            t = datetime.fromisoformat(r["t"])
        except (ValueError, KeyError, TypeError):
            continue
        v = r.get("v") or "-"  # API/curl jobs carry no visitor id; they pair with result lines that have none either
        if r.get("ev") == "start" and r.get("paid"):
            open_jobs.setdefault(v, []).append(t)
        elif "ok" in r and not r.get("ev") and open_jobs.get(v):
            open_jobs[v].pop(0)  # oldest open job of this visitor got its result
    cut = now - timedelta(minutes=MAX_MIN)
    return sorted(v for v, ts in open_jobs.items() if any(t >= cut for t in ts))


if __name__ == "__main__":
    now = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc)
    for v in busy(sys.stdin, now):
        print(v)
