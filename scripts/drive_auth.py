"""One-time: get a Drive refresh token for the OCR-only Google account, for the server's Drive OCR.

usage: python3 scripts/drive_auth.py
Opens Google's consent page (sign in with the OCR account, not the owner's); the token lands in
~/.config/pdf2epub/drive.json (mode 600). Then set DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET and
DRIVE_REFRESH_TOKEN on Railway from that file. Scope is drive.file: the app sees only files it made.
"""
import http.server
import json
import os
import secrets
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

CLIENT = Path.home() / ".config/gws/client_secret.json"  # desktop OAuth client, project in production
OUT = Path.home() / ".config/pdf2epub/drive.json"
SCOPE = "https://www.googleapis.com/auth/drive.file"


def main():
    c = next(iter(json.loads(CLIENT.read_text()).values()))
    state, got = secrets.token_urlsafe(16), {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                got["code"] = q["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Done, you can close this tab." if got else b"No code in this request.")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent select_account", "state": state})
    print("open:", url, flush=True)
    webbrowser.open(url)
    while "code" not in got:
        srv.handle_request()
    body = urllib.parse.urlencode({"code": got["code"], "client_id": c["client_id"], "client_secret": c["client_secret"],
                                   "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))
    if "refresh_token" not in tok:
        raise SystemExit("no refresh token in Google's answer; run again")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"DRIVE_CLIENT_ID": c["client_id"], "DRIVE_CLIENT_SECRET": c["client_secret"],
                               "DRIVE_REFRESH_TOKEN": tok["refresh_token"]}))
    os.chmod(OUT, 0o600)
    print(f"saved {OUT} (scope {tok.get('scope')})")


if __name__ == "__main__":
    main()
