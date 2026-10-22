"""Send a Shelf key to someone who paid, and chase leads that came in over the web.

why: the key is what lifts the 500-page cap, and a subscriber who never gets the key has
paid for nothing. the lead loop is the other half: someone who typed an email into the
cap-rejection box is a buyer we have no address for, so pull those off the railway log.

usage:
    python3 scripts/keys.py grant <email>          # mint a key and email it
    python3 scripts/keys.py leads                 # email anyone who left a lead
    python3 scripts/keys.py watch                 # both, every 5 minutes
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LOG_DIR", str(ROOT / "growth"))

import app as pdf2epub  # noqa: E402

SENT = ROOT / "growth" / ".key-emails-sent.txt"
LEAD_LOG = ROOT / "growth" / ".leads-seen.txt"
MAIL = pdf2epub.SHELF_MAIL
SITE = "https://epub.ftak.net"


def gws(*args):
    p = subprocess.run(["gws", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-300:] or p.stdout[-300:])
    return p.stdout


def seen(path: Path) -> set:
    try:
        return {x.strip() for x in path.read_text().splitlines() if x.strip()}
    except OSError:
        return set()


def mark(path: Path, value: str):
    with path.open("a") as fh:
        fh.write(value + "\n")


def mail_to(to: str, subject: str, body: str):
    gws("gmail", "+send", "--to", to, "--subject", subject, "--body", body)


def push_key(key: str):
    """Put the key where the live site reads it: the railway volume at /data.

    ponytail: the site on railway reads /data/shelf-keys.txt, this script runs on the mac.
    without this the key is minted in a file nobody serves.
    """
    local = ROOT / "growth" / "shelf-keys.txt"
    local.parent.mkdir(parents=True, exist_ok=True)
    with local.open("a") as fh:
        fh.write(f"manual {key}\n")
    # the remote file is the one the site reads, so merge into it and upload the whole thing
    tmp = ROOT / "growth" / ".shelf-keys.download"
    subprocess.run(["railway", "service", "files", "download", "/data/shelf-keys.txt", str(tmp)],
                   capture_output=True, text=True)
    body = tmp.read_text() if tmp.exists() else ""
    tmp.unlink(missing_ok=True)
    if key in body:
        return key
    merged = (body.rstrip("\n") + f"\nmanual {key}\n") if body else f"manual {key}\n"
    up = ROOT / "growth" / ".shelf-keys.upload"
    up.write_text(merged)
    r = subprocess.run(["railway", "service", "files", "upload", str(up), "/data/shelf-keys.txt",
                        "--overwrite"], capture_output=True, text=True)
    up.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"  warning: could not push key to the volume: {r.stderr[-160:]}")
        print("  the key is in growth/shelf-keys.txt, copy it to /data/shelf-keys.txt by hand")
    return key


def grant(email: str):
    """Mint a key, email it, and print it."""
    key = pdf2epub.secrets.token_urlsafe(15)
    push_key(key)
    link = f"{SITE}/?k={key}"
    mail_to(email, "Your pdf2epub Shelf key", f"""Here is your Shelf key.

Put it on the end of the converter link and your uploads get the paid limits, 2,000 pages per
file and 500MB instead of 500 pages and 200MB:

{link}

No account, no password. Shelf is $10 a month for 1,000 pages of your own, batch conversion of
a whole shelf, and the EPUB sent straight to your Kindle. If you want me to convert a specific
PDF by hand instead, just reply to this email with the file.

Krishav""")
    mark(SENT, email)
    print(f"granted {email} key {key} link {link}")
    return key


def lead_route_live() -> bool:
    """Is the /lead route deployed yet? it only exists after the build lands."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(SITE + "/shelf", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200
    except Exception:
        return False


def pull_leads() -> list:
    """Read lead lines off the live log.

    ponytail: the log file on the railway volume is the source of truth and it has every line
    in it, so download it rather than scraping stdout, which only holds the recent tail.
    """
    tmp = ROOT / "growth" / ".conversions.download"
    r = subprocess.run(["railway", "service", "files", "download", "/data/conversions.log", str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        # fall back to stdout when the download is not possible
        out = subprocess.run(["railway", "logs", "--service", "pdf2epub", "--lines", "2000"],
                             capture_output=True, text=True)
        text = out.stdout
    else:
        text = tmp.read_text(errors="replace")
        tmp.unlink(missing_ok=True)
    leads = []
    for m in re.finditer(r'\{[^\n]*"err":\s*"lead:[^"]*"[^\n]*\}', text):
        try:
            r2 = json.loads(m.group(0))
        except ValueError:
            continue
        if r2.get("email"):
            leads.append(r2)
    return leads


def chase_leads():
    done = seen(LEAD_LOG)
    leads = [l for l in pull_leads() if l["email"] not in done]
    for l in leads:
        email = l["email"]
        try:
            mail_to(email, "Your PDF is over the free limit, I can convert it", f"""You hit the
free limit on the converter, so here is the way through.

I will convert the file by hand, no charge, usually the same day. Reply to this email with the
PDF attached and it comes back as an EPUB with real chapters and a table of contents.

If you are working through a shelf rather than one book, Shelf is $10 a month for 1,000 pages
of your own, no per-file ceiling, batch conversion of a whole shelf, and the EPUB sent straight
to your Kindle: {SITE}/shelf

Either way, reply and I will do it.

Krishav""")
            mark(LEAD_LOG, email)
            print(f"chased lead {email} (reason {l.get('err')})")
        except Exception as e:
            print(f"lead {email} failed: {str(e)[:120]}")
    return len(leads)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "leads"
    if cmd == "grant":
        if len(sys.argv) < 3:
            print("usage: keys.py grant <email>")
            return 1
        grant(sys.argv[2].strip())
        return 0
    if cmd == "leads":
        print(f"chased {chase_leads()} leads")
        return 0
    if cmd == "watch":
        while True:
            try:
                # ponytail: /lead only exists once the build lands, so until then there is
                # nothing to pull. check first, so this loop costs one http call, not a
                # 196KB download every five minutes for a route that 404s.
                if not lead_route_live():
                    time.sleep(300)
                    continue
                chase_leads()
            except Exception as e:
                print("loop error:", str(e)[:200])
            time.sleep(300)
    print("unknown command")
    return 1


if __name__ == "__main__":
    sys.exit(main())
