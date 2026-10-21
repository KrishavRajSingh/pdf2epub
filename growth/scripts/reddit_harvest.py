import json, subprocess, os, re, sys
from collections import defaultdict

OUT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(OUT, "reddit")

def rdt(*args):
    p = subprocess.run(["rdt", *args, "--json"], capture_output=True, text=True)
    try:
        return json.loads(p.stdout)
    except Exception:
        return {"ok": False}

Q = re.compile(r"\?|does it|can i|can it|is there|any way|how do i|how much|looking for|anyone know|need a|want a|anyone else|help me|best way|alternative|has anyone|what's the best|how can", re.I)
BAIT = re.compile(r"free (lifetime|premium)|promo code|giveaway|100% off|comment below i will send|discount code|check out my app|my app .* is", re.I)
SELFPOST = re.compile(r"i built|my app|my tool|check out my|launched my|i made|my new app", re.I)

def children_of(d):
    inner = d.get("data", {})
    if isinstance(inner, dict) and isinstance(inner.get("data"), dict):
        inner = inner["data"]
    return inner.get("children", []) if isinstance(inner, dict) else []

def flat_comments(cs, parent=None, depth=0):
    for c in cs:
        if not isinstance(c, dict):
            continue
        yield c, parent, depth
        for r in (c.get("replies") or []):
            yield from flat_comments([r], c.get("fullname"), depth + 1)

def main():
    os.makedirs(RAW, exist_ok=True)
    subs = sys.argv[1:] or ["ebooks", "kindle", "ereader", "Calibre"]
    queries = ["pdf to epub", "pdf epub converter", "convert pdf", "epub from pdf", "pdf to kindle", "scanned pdf epub"]
    posts, seen = [], set()
    for sub in subs:
        for q in queries:
            d = rdt("search", q, "-r", sub, "-n", "25")
            for ch in children_of(d):
                p = ch.get("data") or {}
                pid = p.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                title, body = p.get("title") or "", p.get("selftext") or ""
                if SELFPOST.search(title) or BAIT.search(title):
                    continue
                if not (Q.search(title) or Q.search(body)):
                    continue
                posts.append({"sub": sub, "id": pid, "title": title, "body": body[:400],
                              "score": p.get("ups"), "comments": p.get("num_comments"),
                              "url": "https://reddit.com" + (p.get("permalink") or "")})
    posts.sort(key=lambda r: -(r["comments"] or 0))
    keep = posts[:40]
    out = []
    for r in keep:
        d = rdt("read", r["id"]).get("data", {})
        post = d.get("post") or {}
        comments = d.get("comments") or []
        if not post:
            continue
        with open(os.path.join(RAW, f"{r['id']}.json"), "w") as f:
            json.dump({"post": post, "comments": comments}, f)
        op = (post.get("author") or "").lower()
        op_full = post.get("name")
        # OP asked the main question in the post body; answered if any top-level comment by OP exists
        op_replied = any((c.get("author") or "").lower() == op for c in comments)
        out.append({
            "source": f"r/{r['sub']} post", "asker": "OP@" + op, "question": (r["body"] or r["title"])[:600],
            "answered": op_replied, "post_url": r["url"], "post_title": r["title"],
            "score": r["score"], "comments": r["comments"], "thread": r["id"], "kind": "op",
        })
        for c, parent, depth in flat_comments(comments):
            body = re.sub(r"\s+", " ", c.get("body") or "").strip()
            if not body or len(body) < 12 or not Q.search(body) or BAIT.search(body):
                continue
            if (c.get("author") or "").lower() == op:
                continue
            # answers to this comment?
            kids = [k for k, p, dd in flat_comments(comments) if p == c.get("fullname")]
            answered = bool(kids)
            out.append({
                "source": f"r/{r['sub']} comment", "asker": "@" + (c.get("author") or ""),
                "question": body[:600], "answered": answered, "post_url": r["url"],
                "post_title": r["title"], "score": r["score"], "comments": r["comments"],
                "thread": r["id"], "kind": "comment",
                "comment_url": "https://reddit.com" + (c.get("permalink") or ""),
            })
    with open(os.path.join(OUT, "reddit_questions.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("threads:", len(keep), "questions:", len(out), "unanswered:", sum(1 for r in out if not r["answered"]))
    for r in out:
        if not r["answered"]:
            print(f"[{r['source']}] {r['asker']}: {r['question'][:200]}")

if __name__ == "__main__":
    main()
