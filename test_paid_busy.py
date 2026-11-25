"""deploy guard: a paid job with no result yet blocks the deploy, finished or stale ones don't.

Run: python3 test_paid_busy.py
"""
import importlib.util, json
from pathlib import Path

spec = importlib.util.spec_from_file_location("pb", Path(__file__).parent / "scripts" / "paid_busy.py")
pb = importlib.util.module_from_spec(spec); spec.loader.exec_module(pb)
from datetime import datetime


def L(t, **f):
    return json.dumps({"t": f"2026-11-24T02:{t}:00+00:00", **f})


def main():
    now = datetime.fromisoformat("2026-11-24T02:50:00+00:00")
    lines = [
        L("10", ev="start", v="done1", paid=True), L("12", ok=True, v="done1", err=""),  # finished
        L("44", ev="start", v="buyer", paid=True),                                        # running: the 11-24 case
        L("45", ev="start", v="free1", paid=False),                                       # free jobs never block
        L("01", ev="start", v="old", paid=True),                                          # 49 min old, dead job
        L("40", ev="start", v="two", paid=True), L("41", ok=False, v="two", err="crash x"),
        L("42", ev="start", v="two", paid=True),                                          # second book of a batch, running
        L("46", ev="checkout_click", v="buyer"),                                          # ev lines are not results
        L("47", ev="start", v="", paid=True),                                             # API job, no visitor id
        L("48", ev="start", v="", paid=True), L("48", ok=True, v="", err=""),                                          # ev lines are not results
    ]
    got = pb.busy(lines, now)
    assert got == ["-", "buyer", "two"], got
    # the batch page retries a book once when a restart cut it (502 / job lost / network), instead of skipping it
    import os, tempfile
    os.environ.setdefault("LOG_DIR", tempfile.mkdtemp())
    from fastapi.testclient import TestClient
    import app as a
    land = TestClient(a.app).get("/?k=x").text
    assert "why:'batch-retry'" in land and "[502,503].includes(st)" in land, "batch retry missing"
    print("ok paid_busy")


if __name__ == "__main__":
    main()
