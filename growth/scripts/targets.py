import json, subprocess, os, re, sys

OUT = os.path.dirname(os.path.abspath(__file__))
TARGETS = {
    "1x39d2e": "r/ebooks", "1psh9u5": "r/ebooks", "1vqoth7": "r/ebooks",
    "1wvccvg": "r/kindle", "1sa7guk": "r/kindle", "1tlu322": "r/kindle",
    "1x5a2d4": "r/Calibre", "1vqi568": "r/Calibre", "1uzcek2": "r/Calibre", "1hc2utk": "r/Calibre",
    "1uoxaky": "r/ereader",
}

def rdt(*a):
    p = subprocess.run(["rdt", *a, "--json"], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {}

def flat(cs, parent=None, depth=0):
    for c in cs:
        if not isinstance(c, dict):
            continue
        yield c, parent, depth
        for r in (c.get("replies") or []):
            yield from flat([r], c.get("fullname"), depth + 1)

out = {}
for tid, sub in TARGETS.items():
    d = rdt("read", tid).get("data", {})
    post = d.get("post") or {}
    comments = d.get("comments") or []
    items = []
    for c, parent, depth in flat(comments):
        body = re.sub(r"\s+", " ", c.get("body") or "").strip()
        if not body:
            continue
        items.append({"author": c.get("author"), "id": c.get("id"), "score": c.get("score"),
                      "depth": depth, "body": body[:700],
                      "url": "https://reddit.com" + (c.get("permalink") or "")})
    out[tid] = {"sub": post.get("subreddit") or sub, "title": post.get("title"),
                "score": post.get("score"), "num_comments": post.get("num_comments"),
                "op": post.get("author"), "created": post.get("created_utc"),
                "body": re.sub(r"\s+", " ", post.get("selftext") or "")[:900],
                "url": "https://reddit.com" + (post.get("permalink") or ""),
                "comments": items}
    print(f"{tid} r/{out[tid]['sub']} up={out[tid]['score']} cmts={out[tid]['num_comments']} | {out[tid]['title'][:60]}", flush=True)
json.dump(out, open(os.path.join(OUT, "targets_live.json"), "w"), indent=1)
print("saved", len(out))
