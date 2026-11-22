"""Page furniture keys (11-22 QA): a footer whose page number is a symbol-font glyph must key the
same on every page, and a glyph alone must key to "" so it is dropped, not kept as a heading."""
from app import _furn_key, DROP_CAP

assert _furn_key(" Free eBooks at Planet eBook.com") == _furn_key(" Free eBooks at Planet eBook.com") \
    == "free ebooks at planet ebook.com"
assert _furn_key("Moby Dick ") == _furn_key("Moby Dick 12") == "moby dick"
assert _furn_key("") == "" and _furn_key("\x18") == "" and _furn_key("214") == ""
assert _furn_key("It was a bright cold day") == "it was a bright cold day"
assert all(DROP_CAP.fullmatch(t) for t in ("I", "W", "‘", "‘I"))
assert not any(DROP_CAP.fullmatch(t) for t in ("It", "a", "12", "IV"))
print("ok: furniture keys")
