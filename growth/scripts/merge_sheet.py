import json, os, re, csv, glob
from collections import Counter, defaultdict

OUT = os.path.dirname(os.path.abspath(__file__))
DEST = "/Users/chirkoot/free/pdf2epub/growth"

CLUSTERS = [
    ("converter-quality", r"\b(mangl|mess(es|ed)?|mess up|garbage|junk|broken|breaks? (up|the)|repeat(ed)? page numbers?|paragraphs? (are )?wrong|wrong (order|formatting)|garbled|words? (in|out of) order|mid-sentence line breaks?|OCR junk|poor quality|bad quality|not reflow|reflow)\b"),
    ("kindle-delivery", r"(send to kindle|side.?load|kobo|boox|pocket ?book|kindle|ereader|e-?reader|email (it |my )?(pdf|epub|book)|usb|copy (it |the )?(file|book) over|load (it |the )?(onto|on)|put (it|the file) on|get (it|the book|my book) (on|to)|calibre)"),
    ("scans-ocr", r"\b(scan(ned|ning)?|image.only|photo of (a )?(page|book)|ocr|no text|camera|photograph|camera.?scan|real paper|out of print book)\b"),
    ("price", r"(\bprice|\bpricing|\bcosts?\b|how much|\bfree\b|subscription|pay per|per book|expensive|afford|premium|trial|paywall|credit)"),
    ("features-chapters", r"\b(chapter|table of contents|toc|navigat|bookmark|highlight|annotat|note(s| taking)? in the margin|syn(c|cing)|dictionary|font size|dictionary lookup)\b"),
    ("formats-compat", r"\b(epub ?3?|mobi|azw3?|fb2|pdf format|other formats?|drm|kindle format|file type|what formats)\b"),
    ("limits-size", r"\b(file size|too (big|large)|mb|gb|page limit|max pages|500 pages|how (big|many pages)|limit(ations)?|quota|whole textbook|entire book)\b"),
    ("mobile-speed", r"\b(on my (phone|tablet|ipad)|phone app|ios|android|mobile|app for|slow|how long|takes forever|minutes|hours?)\b"),
    ("editing-fixes", r"\b(fix(ed|ing)?|edit(ing)? (the )?(epub|file|output)|correct(ing)?|clean up|touch ?up|proofread|typos?|manually)\b"),
    ("privacy", r"\b(privacy|private|upload (my|it) to|store(d|ing)? my|delete my|leak|secure|offline|local)\b"),
    ("alternatives", r"\b(alternative|better tool|is there (a|any) (better|other)|which (tool|app|converter|one) should|instead of|best (tool|app|converter))\b"),
]

def customer_type(t):
    if re.search(r"\b(teacher|instructor|professor|\bTA\b|grading|grade |rubric|assignment|submission|student.s (essay|assignment|homework)|syllabus|college|university|exam|study|studying|course)", t, re.I):
        return "student / instructor"
    if re.search(r"\b(author|manuscript|self.?publish|publish(ing|er)?|kdp|audiobook|narrat|royalt|my book|my novel)", t, re.I):
        return "indie author"
    if re.search(r"\b(kindle|kobo|boox|pocket ?book|ereader|e-?reader|apple books|re-?markable|kindle app|my tablet|my phone)", t, re.I):
        return "e-reader / phone reader"
    if re.search(r"\b(blind|visually impair|large print|dyslex|disab|accessib|screen reader)", t, re.I):
        return "accessibility reader"
    if re.search(r"\b(invoice|contract|legal|financial|real estate|compliance|audit|workplace|company|team)", t, re.I):
        return "document professional"
    return "PDF owner"

def cluster(t):
    for name, pat in CLUSTERS:
        if re.search(pat, t, re.I):
            return name
    return "other"

RELEVANT = re.compile(r"\b(pdf|epub|kindle|kobo|boox|ereader|e-?reader|ebook|e-?book|book|books|textbook|syl(labus)?|slide|notes?|chapter|scan|ocr|convert|conversion|read|reading|reader|author|novel|story|stories|audiobook|narrat|price|pricing|cost|free|subscription|plan|upload|download|side.?load|calibre|highlight|annotat|font|table of contents|toc|drm|mobi|azw|ai|gpt|model|student|teacher|grade|rubric|assignment|essay|document|invoice|folder|file)\b", re.I)
NOISE = re.compile(r"\b(airdrop|giveaway|follow back|let'?s connect|inbox me|check dm|dm me)\b", re.I)

HARDWARE = re.compile(r"\b(battery|screen|display|backlight|fingerprint|case|shipping|firmware|refresh rate|backlit|leather|goodreads|review count|weight of|bezel|palm|wallpaper|fonts on the device|dead pixel)\b", re.I)

def clean(t):
    return re.sub(r"\s+", " ", (t or "")).strip()

rows = []

# 1) Reddit: OP posts + unanswered comments
for r in json.load(open(os.path.join(OUT, "reddit_questions.json"))):
    q = clean(r["question"])
    if len(q) < 20 or not RELEVANT.search(q) or HARDWARE.search(q):
        continue
    rows.append({
        "source": r["source"], "platform": "Reddit", "startup": "", "person": r["asker"],
        "question": q[:600], "cluster": cluster(q), "customer_type": customer_type(q),
        "answered": r["answered"], "status": "answered" if r["answered"] else "UNANSWERED",
        "url": (f"https://reddit.com/r/{r['source'].split()[0][2:]}/comments/{r.get('thread')}/_/{r.get('comment_id')}" if r.get("comment_id") else r["post_url"]),
        "thread": r.get("post_title", "")[:120],
        "upvotes": r.get("score"), "comments": r.get("comments"),
    })

# 2) X: customer-side tweets (search harvest)
for o in json.load(open(os.path.join(OUT, "x_customer_questions.json"))):
    q = clean(o["text"])
    if len(q) < 20:
        continue
    if not RELEVANT.search(q) or NOISE.search(q):
        continue
    rows.append({
        "source": "X search", "platform": "X", "startup": "", "person": "@" + o["author"],
        "question": q[:600], "cluster": cluster(q), "customer_type": customer_type(q), "answered": "", "status": "open",
        "url": o["url"], "thread": o["query"], "upvotes": o["likes"], "comments": "",
    })

FOUNDER2COMPANY = {
    "leslie_rh7": "Hyperknow", "yi1inz": "Hyperknow", "hyperknow_ai": "Hyperknow",
    "ahmadKaamel": "Sinai.ai", "Sinaidotai": "Sinai.ai",
    "yoonseok_yang": "Pensive", "trypensive": "Pensive",
    "alapshah1": "Littlebird", "LittlebirdAI": "Littlebird",
    "SpokenPress": "Spoken",
}

# 3) X: replies under the 5 founders' own posts
for path in sorted(glob.glob(os.path.join(OUT, "replies", "*.json"))):
    blob = json.load(open(path))
    post = blob["post"]
    replies = blob.get("replies") or []
    founder = post.get("author", {}).get("screenName", "")
    company = FOUNDER2COMPANY.get(founder, "")
    directed = defaultdict(list)
    for r in replies:
        m = re.match(r"^@([A-Za-z0-9_]+)", clean(r.get("text")))
        if m:
            directed[m.group(1).lower()].append(r.get("author", {}).get("screenName", ""))
    for r in replies:
        ra = r.get("author", {}).get("screenName", "")
        if ra.lower() == founder.lower():
            continue
        q = clean(r.get("text"))
        if len(q) < 15:
            continue
        ans_by_founder = any(a.lower() == founder.lower() for a in directed.get(ra.lower(), []))
        ans_by_other = [a for a in directed.get(ra.lower(), []) if a.lower() != founder.lower()]
        if not RELEVANT.search(q) or NOISE.search(q):
            continue
        rows.append({
            "source": f"X reply under @{founder}", "platform": "X", "startup": company,
            "person": "@" + ra, "question": q[:600], "cluster": cluster(q),
            "answered": ans_by_founder,
            "status": "answered by founder" if ans_by_founder else ("answered by other" if ans_by_other else "UNANSWERED"),
            "url": f"https://x.com/{ra}/status/{r['id']}",
            "thread": clean(post.get("text"))[:120], "upvotes": r.get("metrics", {}).get("likes", 0), "comments": "",
        })


FOUNDER2COMPANY = {
    "leslie_rh7": "Hyperknow", "yi1inz": "Hyperknow", "hyperknow_ai": "Hyperknow",
    "ahmadKaamel": "Sinai.ai", "Sinaidotai": "Sinai.ai",
    "yoonseok_yang": "Pensive", "trypensive": "Pensive",
    "alapshah1": "Littlebird", "LittlebirdAI": "Littlebird",
    "SpokenPress": "Spoken",
}

fields = ["source", "platform", "startup", "person", "customer_type", "problem", "question", "cluster", "status", "url", "thread", "upvotes", "comments"]
os.makedirs(DEST, exist_ok=True)
with open(os.path.join(DEST, "question-sheet.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in rows:
        r["problem"] = r["cluster"]
        w.writerow({k: r.get(k, "") for k in fields})

print("total rows:", len(rows))
print(Counter(r["platform"] for r in rows))
print(Counter(r["status"] for r in rows))
print("clusters:", Counter(r["cluster"] for r in rows).most_common())
print("\nUNANSWERED by cluster:")
for c, n in Counter(r["cluster"] for r in rows if r["status"] in ("UNANSWERED", "open")).most_common():
    print(f"  {c}: {n}")
