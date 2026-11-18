"""_suspect flags books whose structure a glance would call broken (log only).

Run: python3 test_suspect.py
"""
import os, sys, tempfile
from pathlib import Path

os.environ["LOG_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import _suspect

PARA = ("p", "word " * 400)


def book(n_ch, paras=3):
    return [[("h1", f"Chapter {i}")] + [PARA] * paras for i in range(n_ch)]


def main():
    # 11-18 novel before the fix: 954 chapters in 404 pages
    assert _suspect(book(954, 0), 404) == "chapters"
    # 11-14 memoir before the fix: 207 chapters in 370 pages
    assert _suspect(book(207), 370) == "chapters"
    # the same novel after the fix, a normal novel, a short paper
    assert _suspect(book(54), 404) == ""
    assert _suspect(book(30), 300) == ""
    assert _suspect(book(3), 12) == ""
    # many chapters of a sentence or two each: paragraph starts read as headings
    assert _suspect([[("h1", "x"), ("p", "a few words here")]] * 30, 200) == "tiny-chapters"
    print("ok: suspect")


if __name__ == "__main__":
    main()
