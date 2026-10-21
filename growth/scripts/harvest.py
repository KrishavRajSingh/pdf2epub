import json, subprocess, sys, os, re
from concurrent.futures import ThreadPoolExecutor

ENV = dict(os.environ)
ENV["TWITTER_BROWSER"] = "chrome"
ENV["TWITTER_CHROME_PROFILE"] = "Profile 4"
OUT = os.path.dirname(os.path.abspath(__file__))

def cli(*args, tries=2):
    for _ in range(tries):
        p = subprocess.run(["twitter", *args, "--json"], capture_output=True, text=True, env=ENV)
        try:
            d = json.loads(p.stdout)
            if d.get("ok"):
                return d
        except Exception:
            pass
    return {"ok": False, "data": []}

Q_PAT = re.compile(r"\?|does it|does this|do i|can i|can it|is there|are there|how do i|how much|how to|any way|is there any|what about|will it|would it|anyone know|does anyone|am i allowed|is it possible", re.I)
BAIT = re.compile(r"let'?s connect|connect privately|inbox me|check dm|dm plz|follow back|giveaway|airdrop|crypto|🔥|💎|solid |amazing |great work|keep going|ship it|congrats", re.I)

def harvest(handle, maxposts=100, workers=2):
    up = cli("user-posts", handle, "--max", "150")
    rows = up.get("data", [])
    posts = [t for t in rows if t.get("author", {}).get("screenName", "").lower() == handle.lower() and not t.get("isRetweet")]
    posts = posts[:maxposts]
    withrep = [t for t in posts if t.get("metrics", {}).get("replies", 0) > 0]
    paths = []
    def one(t):
        p = os.path.join(OUT, "replies", f"{handle}__{t['id']}.json")
        if os.path.exists(p):
            return p
        d = cli("tweet", t["id"], "-n", "50")
        if not d.get("ok"):
            return None
        with open(p, "w") as f:
            json.dump({"post": t, "replies": d.get("data", [])[1:]}, f)
        return p
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for p in ex.map(one, withrep):
            if p:
                paths.append(p)
    # retry misses sequentially (rate limits hit hardest in parallel)
    for t in withrep:
        p = os.path.join(OUT, "replies", f"{handle}__{t['id']}.json")
        if os.path.exists(p):
            continue
        one(t)
        if os.path.exists(p):
            paths.append(p)
    with open(os.path.join(OUT, "posts", f"{handle}.json"), "w") as f:
        json.dump(posts, f)
    return {"handle": handle, "original_posts": len(posts), "posts_with_replies": len(withrep), "reply_files": len(paths)}

if __name__ == "__main__":
    os.makedirs(os.path.join(OUT, "replies"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "posts"), exist_ok=True)
    for h in sys.argv[1:]:
        r = harvest(h)
        print(json.dumps(r), flush=True)
