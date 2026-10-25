"""Tell Bing (and the other IndexNow engines) that every page in the sitemap changed.

Run after a deploy that changed page text: python3 scripts/indexnow.py
Google does not take part in IndexNow; Search Console covers it.
"""
import json, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app as pdf2epub

HOST = "epub.ftak.net"
key = pdf2epub.INDEXNOW_KEY
live = urllib.request.urlopen(f"https://{HOST}/{key}.txt", timeout=20).read().decode().strip()
if live != key:
    sys.exit("the live site does not serve the key yet, deploy first")
body = json.dumps({"host": HOST, "key": key, "keyLocation": f"https://{HOST}/{key}.txt",
                   "urlList": [f"https://{HOST}{u}" for u in pdf2epub.site_urls()]}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
with urllib.request.urlopen(req, timeout=20) as r:
    print(r.status, "submitted", len(pdf2epub.site_urls()), "urls")  # 200 or 202 means accepted
