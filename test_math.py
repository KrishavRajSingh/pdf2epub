"""Math text repairs (11-19 lead: a LaTeX preprint and a 1999 Elsevier paper).

Run: python3 test_math.py
"""
import app


def span(text, font, x0, y0, x1, y1, size=10.0):
    return {"text": text, "font": font, "size": size, "flags": 0, "bbox": (x0, y0, x1, y1)}


def fixed(text, font):
    sp = span(text, font, 0, 0, 10, 10)
    app._fix_math_span(sp)
    return sp["text"]


# STIX math italics with the top bit lost read as Korean: "푥" is x
assert fixed("푥1 + 휀13", "STIXMath-Italic") == "x1 + ε13", fixed("푥1 + 휀13", "STIXMath-Italic")
# real Korean in a text font stays
assert fixed("한국어", "NanumGothic") == "한국어"
# 1999 Elsevier Pi fonts: "zs0" is z=0, "Ž ." are parentheses, "´" is epsilon
assert fixed("s", "ScienceTypeCustomPi-No5T") == "="
assert fixed("y", "ScienceTypeCustomPi-No5T") == "−"
assert fixed("Ž.", "SizedSym151") == "()"
assert fixed("´", "MathematicalPi-One") == "ε"
assert fixed("CiÕil", "ElsevierSpecialPi") == "Civil"
# the same letters in Times are just letters
assert fixed("sy", "Times-Roman") == "sy"
# LaTeX built with the wrong input encoding
assert fixed("DâĂŹErrico", "STIXGeneral-Regular") == "D’Errico"

# a big bracket on a PDF line of its own goes back between the words of its visual line
b = {"type": 0, "bbox": (0, 0, 200, 30), "lines": [
    {"bbox": (40, 0, 100, 14), "spans": [span("(", "SizedSym151", 40, 0, 44, 14, 14),
                                          span(")", "SizedSym151", 70, 0, 74, 14, 14)]},
    {"bbox": (0, 2, 120, 12), "spans": [span("node", "Times-Roman", 0, 2, 30, 12),
                                         span("i, j", "Times-Roman", 46, 2, 66, 12),
                                         span("next", "Times-Roman", 80, 2, 100, 12)]},
]}
app._merge_bands(b)
assert len(b["lines"]) == 1, b["lines"]
t = "".join(s["text"] for s in b["lines"][0]["spans"])
assert t == "node (i, j) next", t
# a math bracket does not make the line heading-sized
assert app._line_size(b["lines"][0]) == 10.0

# a prose line with a Pi-font bracket is text, an operator line is an equation
raw = [
    {"type": 0, "bbox": (40, 100, 300, 112), "lines": [{"bbox": (40, 100, 300, 112), "spans": [
        span("was made in Ref. ", "Times-Roman", 40, 100, 120, 112),
        span("[", "ScienceTypeCustomPi-No5T", 120, 100, 124, 112),
        span("3", "Times-Roman", 124, 100, 130, 112),
        span("]", "ScienceTypeCustomPi-No5T", 130, 100, 134, 112)]}]},
    {"type": 0, "bbox": (80, 200, 260, 214), "lines": [{"bbox": (80, 200, 260, 214), "spans": [
        span("u = K p", "STIXMath-Italic", 80, 200, 260, 214)]}]},
    {"type": 0, "bbox": (480, 202, 500, 212), "lines": [{"bbox": (480, 202, 500, 212), "spans": [
        span("(3)", "Times-Roman", 480, 202, 500, 212)]}]},
]
eqs = app._equations(raw, 800)
assert [sorted(ks) for _, ks in eqs] == [[1, 2]], eqs
print("ok test_math")
