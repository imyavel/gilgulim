# -*- coding: utf-8 -*-
"""translation.md -> translation.rtf. Запускать из C:\\Users\\admin\\gilgulim."""
import re

SRC, DST = "translation.md", "translation.rtf"

def esc(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif o < 128:
            out.append(ch)
        else:
            if o > 32767:
                o -= 65536
            out.append("\\u%d?" % o)
    return "".join(out)

def inline(s):
    # **bold** -> {\b ...}
    return re.sub(r"\*\*(.+?)\*\*", lambda m: "{\\b %s}" % m.group(1), s)

lines = open(SRC, encoding="utf-8").read().splitlines()
body = []
for ln in lines:
    t = re.sub(r"<!--\s*(.*?)\s*-->", r"[\1]", ln.strip())
    if not t or t == "---":
        continue
    if t.startswith("## "):
        body.append("\\pard\\sb360\\sa180\\qc{\\b\\fs32 %s}\\par" % inline(esc(t[3:])))
    elif t.startswith("# "):
        body.append("\\pard\\sb240\\sa240\\qc{\\b\\fs40 %s}\\par" % inline(esc(t[2:])))
    else:
        body.append("\\pard\\sb120\\sa120\\qj\\fi360\\fs24 %s\\par" % inline(esc(t)))

rtf = ("{\\rtf1\\ansi\\ansicpg1251\\deff0"
       "{\\fonttbl{\\f0 Times New Roman;}}"
       "\\f0\\fs24\n" + "\n".join(body) + "\n}")
open(DST, "w", encoding="ascii").write(rtf)
print(DST, "written,", len(rtf), "bytes")
