"""Country code on funnel lines: paywall hits, pitches, buy clicks and nobuy taps carry `cc`, never the IP.

Run: python3 test_country.py
"""
import json, os, tempfile

os.environ["LOG_DIR"] = tempfile.mkdtemp()  # keep the real conversions.log clean
from fastapi.testclient import TestClient
import app as a


def fake_request(headers):
    from starlette.requests import Request
    return Request({"type": "http", "method": "POST", "path": "/convert", "query_string": b"",
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()], "client": ("10.0.0.1", 1)})


class FakeGeo:
    def get(self, ip):
        return {"203.0.113.9": {"country": {"iso_code": "IN"}},
                "198.51.100.7": {"country": {"iso_code": "US"}}}.get(ip)


def main():
    human = {"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"}
    c = TestClient(a.app)
    # no database file: logging still works, cc is empty
    a._GEO = None
    r = c.post("/e", content=b'{"n":"view","v":"abcdefgh12"}', headers={**human, "x-forwarded-for": "203.0.113.9"})
    assert r.status_code == 204
    last = json.loads(a.LOG.read_text().splitlines()[-1])
    assert last["cc"] == "" and "203.0.113.9" not in a.LOG.read_text(), last

    a._GEO = FakeGeo()
    c.post("/e", content=b'{"n":"nobuy","v":"abcdefgh12","why":"price"}', headers={**human, "x-forwarded-for": "203.0.113.9, 10.0.0.1"})
    c.post("/e", content=b'{"n":"pitch","v":"abcdefgh13"}', headers={**human, "x-forwarded-for": "198.51.100.7"})
    c.post("/e", content=b'{"n":"nav_cta","v":"abcdefgh13"}', headers={**human, "x-forwarded-for": "198.51.100.7"})
    c.get("/go/onebook", headers={**human, "x-forwarded-for": "198.51.100.7"}, follow_redirects=False)
    a.log(False, 400, 100, 0, "too many pages", "r-test|", request=fake_request({**human, "x-forwarded-for": "203.0.113.9"}))
    text = a.LOG.read_text()
    assert "203.0.113.9" not in text and "198.51.100.7" not in text, "IP must never be logged"
    lines = [json.loads(l) for l in text.splitlines()]
    assert any(l.get("ev") == "nav_cta" for l in lines), "nav_cta beacon must be kept (was dropped before 11-25)"
    by = c.get("/stats").json()["by_cc"]
    assert by["nobuy:price"] == {"IN": 1}, by
    assert by["pitch"] == {"US": 1}, by
    assert by["cap"] == {"IN": 1}, by
    assert by.get("checkout_click", {}).get("US") == 1 or not a.ONETIME_URL, by
    priv = c.get("/privacy").text
    assert "DB-IP" in priv and "Cloudflare Web Analytics" in priv and "no third party analytics" not in priv
    print("ok country")


if __name__ == "__main__":
    main()
