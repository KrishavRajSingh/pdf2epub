"""Post to Reddit without the CLI (rdt cannot create posts).

Uses the reddit session cookie that is already in Chrome. Run it with the rdt venv python so
browser_cookie3 is available:

  /Users/chirkoot/.local/pipx/venvs/rdt-cli/bin/python scripts/reddit_post.py \
      --sub ereader --title "..." --body-file post.txt --flair "Tool"

usage: reddit_post.py --sub X --title T (--body B | --body-file F) [--flair NAME] [--dry-run]
"""
import argparse, json, sys, urllib.parse
from pathlib import Path

import browser_cookie3

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"


def cookies():
    jar = browser_cookie3.chrome(domain_name="reddit.com")
    return {c.name: c.value for c in jar}


def api(path, jar, method="GET", data=None):
    import urllib.request
    url = "https://www.reddit.com" + path
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in jar.items()))
    tok = jar.get("token_v2")
    if tok:
        req.add_header("X-CSRF-Token", tok)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def flair_id(sub, name, jar):
    try:
        rows = api(f"/r/{sub}/api/link_flair_v2.json", jar)
    except Exception:
        rows = api(f"/r/{sub}/api/flairlist.json", jar)
    for row in rows:
        if row.get("text", "").strip().lower() == name.strip().lower():
            return row.get("id") or row.get("flair_id")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sub", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--body")
    ap.add_argument("--body-file")
    ap.add_argument("--flair")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    text = a.body if a.body is not None else Path(a.body_file).read_text()
    jar = cookies()
    fid = flair_id(a.sub, a.flair, jar) if a.flair else None
    if a.flair and not fid:
        print(f"flair {a.flair!r} not found, posting without it", file=sys.stderr)
    data = {"api_type": "json", "sr": a.sub, "kind": "self", "title": a.title, "text": text}
    if fid:
        data["flair_id"] = fid
    if a.dry_run:
        print(json.dumps({"sub": a.sub, "title": a.title, "flair_id": fid, "chars": len(text)}))
        return
    res = api("/api/submit", jar, method="POST", data=data)
    if res.get("errors"):
        print("ERRORS:", res["errors"], file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"id": res.get("id"), "url": "https://reddit.com" + res.get("url", ""),
                      "flair_id": fid}))


if __name__ == "__main__":
    main()
