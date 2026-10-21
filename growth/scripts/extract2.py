import json, os, re, glob, csv
from collections import Counter, defaultdict

OUT = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(OUT, "replies")

BRAND = {
    "leslie_rh7": ("Hyperknow", "hyperknow"), "yi1inz": ("Hyperknow", "hyperknow"),
    "hyperknow_ai": ("Hyperknow", "hyperknow"),
    "ahmadKaamel": ("Sinai.ai", "sinai"), "Sinaidotai": ("Sinai.ai", "sinai"),
    "yoonseok_yang": ("Pensive", "pensive"), "trypensive": ("Pensive", "pensive"),
    "alapshah1": ("Littlebird", "littlebird"), "LittlebirdAI": ("Littlebird", "littlebird"),
    "george_matelich": ("Rely", "rely"), "mgalcor": ("Plotsy", "plotsy"),
    "Plotsy_inc": ("Plotsy", "plotsy"), "SpokenPress": ("Spoken", "spoken"),
}

Q = re.compile(r"\?|\bdoes\b|\bdo i\b|\bcan i\b|\bcan it\b|\bcan we\b|\bis there\b|\bare there\b|\bhow do i\b|\bhow do you\b|\bhow much\b|\bhow to\b|\bany way\b|\bwhat about\b|\bwill it\b|\bwould it\b|\banyone know\b|\bdoes anyone\b|\bis it possible\b|\bwhy is\b|\bwhy does\b|\bwhen is\b|\bwhich\b", re.I)
BAIT = re.compile(r"let'?s connect|connect privately|inbox me|check dm|dm plz|follow back|giveaway|airdrop|\bNFT\b|\btoken\b|crypto|🔥|💎|\bsolid\b|\bamazing\b|great work|keep going|ship it|congrats|comment .{0,25}and|interested in|collaborat|partner with|\bDM me\b|check page|follow me", re.I)
THANKS = re.compile(r"^(?:@?\w+\s*)?(?:thanks|thank you|great|nice|awesome|love this|this is (great|amazing|cool)|following you|followed)", re.I)

THEMES = [
    ("pricing", r"\b(price|pricing|cost|costs|how much|subscription|pay per|payment|billing|invoice|expensive|cheap|free tier|refund)\b"),
    ("plans/limits", r"\b(limit|limits|quota|quota|cap|caps|max pages|page limit|size limit|file size|too (big|large)|how many|credits|minutes|daily)\b"),
    ("file types/format", r"\b(pdf|epub|mobi|docx?|pptx?|powerpoint|csv|xlsx?|markdown|txt|image|scan|ocr|file type|formats?)\b"),
    ("conversion/import", r"\b(convert|conversion|convert it|import|importing|export|exporting|upload|uploading|download|downloadable|sync|export to)\b"),
    ("feature gap", r"\b(does it (do|support|have|handle)|can it (do|support|handle)|feature request|would be great if|wish it (could|did|had)|support for|when will|roadmap|offline|mobile app|ios|android|desktop)\b"),
    ("quality/reliability", r"\b(accuracy|accurate|quality|error|errors|fail|fails|failure|wrong|bug|crash|hallucinat|garbage|garbled|jumbled|words? (in|out of) order)\b"),
    ("account/access", r"\b(login|log in|sign ?up|sign ?in|account|accounts|password|email|invite|team|seats?|workspace|admin)\b"),
    ("reliability of answer", r"\b(is it (accurate|reliable|good)|can i trust|does it actually|really work|any good)\b"),
    ("alternatives/compare", r"\b(alternative|instead of|better than|compared to|vs\.?|versus|which (one|tool|app) (is|should)|what do you use|any other)\b"),
    ("content/curation", r"\b(books?|titles?|library|catalog|collection|authors?|writing|story|stories|novel)\b"),
]

def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def theme_of(t):
    for name, pat in THEMES:
        if re.search(pat, t, re.I):
            return name
    return "other"

def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(FOLDER, "*.json"))):
        blob = json.load(open(path))
        post = blob["post"]
        replies = blob.get("replies") or []
        handle = os.path.basename(path).split("__")[0]
        founder = post.get("author", {}).get("screenName", handle)
        company, brand = BRAND.get(founder, (founder, founder.lower()))
        founderset = {r.get("author", {}).get("screenName", "").lower() for r in replies}
        founder_replied = founder.lower() in founderset
        directed = defaultdict(list)
        for r in replies:
            txt = norm(r.get("text"))
            m = re.match(r"^@([A-Za-z0-9_]+)", txt)
            if m:
                directed[m.group(1).lower()].append((r.get("author", {}).get("screenName", ""), txt))
        for r in replies:
            ra = r.get("author", {}).get("screenName", "")
            if ra.lower() == founder.lower():
                continue
            txt = norm(r.get("text"))
            if len(txt) < 15 or not Q.search(txt) or BAIT.search(txt) or THANKS.match(txt):
                continue
            mentions_brand = brand.lower() in txt.lower()
            has_product_term = any(re.search(p, txt, re.I) for _, p in THEMES)
            if not (mentions_brand or has_product_term):
                continue
            af = any(a.lower() == founder.lower() for a, _ in directed.get(ra.lower(), []))
            ao = [(a, t) for a, t in directed.get(ra.lower(), []) if a.lower() != founder.lower()]
            rows.append({
                "startup": company,
                "founder": "@" + founder,
                "post_url": f"https://x.com/{founder}/status/{post['id']}",
                "post_date": post.get("createdAtISO", "")[:10],
                "post_text": norm(post.get("text"))[:200],
                "asker": "@" + ra,
                "question": txt[:500],
                "theme": theme_of(txt),
                "answered_by_founder": af,
                "founder_replied_in_thread": founder_replied,
                "answered_by_other": bool(ao),
                "other_answer": ao[0][1][:200] if ao else "",
                "reply_url": f"https://x.com/{ra}/status/{r['id']}",
                "likes": r.get("metrics", {}).get("likes", 0),
            })
    seen, out = set(), []
    for r in rows:
        k = (r["startup"], r["question"][:70].lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    fields = ["startup", "founder", "post_url", "post_date", "asker", "question", "theme",
              "answered_by_founder", "founder_replied_in_thread", "answered_by_other",
              "other_answer", "reply_url", "likes", "post_text"]
    with open(os.path.join(OUT, "questions.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print("total:", len(out))
    print(Counter(r["startup"] for r in out))
    print("themes:", Counter(r["theme"] for r in out).most_common())
    print("answered_by_founder:", sum(1 for r in out if r["answered_by_founder"]))
    print("unanswered:", sum(1 for r in out if not r["answered_by_founder"]))

if __name__ == "__main__":
    main()
