"""/stats: real buy clicks (with a visitor id) and Polar-verified paid orders.

11-25: "checkouts" was read as 120 buy clicks. It counts /thanks landings (our tests, refreshes),
and 160 of 205 checkout_click lines were bot bursts with no visitor id. Run: python3 test_stats_clicks.py
"""
import json, os, tempfile

os.environ["LOG_DIR"] = tempfile.mkdtemp()  # keep the real conversions.log clean
from pathlib import Path
from starlette.responses import Response
import app as a


def main():
    d = Path(os.environ["LOG_DIR"])
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/149.0"
    a.LOG = d / "conversions.log"
    a.LOG.write_text("\n".join(json.dumps(r) for r in [
        {"t": "2026-11-25T00:00:00+00:00", "ev": "checkout_click", "v": "", "ua": ua, "offer": "onebook"},
        {"t": "2026-11-25T00:00:00+00:00", "ev": "checkout_click", "v": "", "ua": ua, "offer": "shelf"},
        {"t": "2026-11-25T00:00:01+00:00", "ev": "checkout_click", "v": "reader1", "ua": ua, "offer": "short"},
        {"t": "2026-11-25T00:00:02+00:00", "ev": "checkout_click", "v": "crawler1", "ua": "Googlebot/2.1", "offer": "short"},
    ]) + "\n")
    a.PAID = d / "paid-checkouts.txt"
    a.PAID.write_text("id-1 prod-a\nid-2 prod-b\nid-1 prod-a\n")
    st = a.stats(Response())
    assert st["clicks_real"] == 1, st["clicks_real"]
    assert st["paid_orders"] == 2, st["paid_orders"]
    a.PAID.unlink()
    assert a.stats(Response())["paid_orders"] == 0
    print("ok: /stats counts real clicks and paid orders")


if __name__ == "__main__":
    main()
