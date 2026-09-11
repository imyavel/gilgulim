# -*- coding: utf-8 -*-
"""Парсинг исходников: перевод (translation.md) и оригинал (source/gilgulim_he.md).

Общий модуль для align.py и build.py. Ничего не пишет, только читает.
"""
import io
import os
import re
import sys
import unicodedata

RU_PATH = r"C:\Users\admin\gilgulim\translation.md"
HE_PATH = r"C:\Users\admin\gilgulim\source\gilgulim_he.md"
GLOSSARY_PATH = r"C:\Users\admin\gilgulim\glossary.md"

TRANSLATED_UPTO = 36  # переведены хакдамот 1..36

RU_CHAP = re.compile(r"^##\s+Хакдама\s+(\d+)\s*$")
HE_CHAP = re.compile(r"^##\s+Hakdamah\s+(\d+)\s*$")
RU_SEG = re.compile(r"^\*\*\[(\d+)\.(\d+)\]\*\*\s*")
HE_SEG = re.compile(r"^\[(\d+)\.(\d+)\]\s*")


def norm_ws(s):
    """Нормализация пробелов для сверки целостности."""
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)  # пометки переводчика (<!-- TODO -->) на сайт не идут
    s = s.replace("\u00a0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def norm_chars(s):
    """Сверка целостности: только символы, пробелы не в счёт (куски вырезаны из источника)."""
    return re.sub(r"\s+", "", s)


def _parse(path, chap_re, seg_re, upto):
    """Возвращает OrderedDict-подобный список [(n, [(sid, text), ...]), ...]."""
    with io.open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    chapters = []
    cur_n = None
    cur_segs = None
    cur_id = None
    buf = []

    def flush():
        if cur_id is not None:
            cur_segs.append((cur_id, norm_ws(" ".join(buf))))

    for line in lines:
        m = chap_re.match(line.strip())
        if m:
            flush()
            cur_id, buf = None, []
            cur_n = int(m.group(1))
            cur_segs = []
            chapters.append((cur_n, cur_segs))
            continue
        m = seg_re.match(line)
        if m:
            flush()
            n, s = int(m.group(1)), int(m.group(2))
            cur_id = "%d.%d" % (n, s)
            buf = [line[m.end():]]
            continue
        if cur_id is not None:
            if line.strip() == "" or line.strip() == "---":
                continue
            buf.append(line)
    flush()
    return [(n, segs) for n, segs in chapters if n <= upto]


def load_ru(upto=TRANSLATED_UPTO):
    return _parse(RU_PATH, RU_CHAP, RU_SEG, upto)


def load_he(upto=TRANSLATED_UPTO):
    return _parse(HE_PATH, HE_CHAP, HE_SEG, upto)


# --- разбиение на слова (должно совпадать с разбиением в index.html) ---
# Слово = буквы/цифры (любой алфавит), склеенные дефисом, апострофом или гершаимом:
# АБЕ"А, НаРа"Н, ға-Гилгулим. Та же логика продублирована в index.html (JS).
RU_WORD = re.compile(r"[^\W_]+(?:[\"'’ʼ‑-][^\W_]+)*", re.UNICODE)
HE_WORD_SPLIT = re.compile(r"\s+")


def ru_words(text):
    """Слова русского текста — так же, как их обернёт JS в <span class="w">."""
    return RU_WORD.findall(text)


def he_words(text):
    """Слова иврита/транслита — просто по пробелам."""
    return [w for w in HE_WORD_SPLIT.split(text.strip()) if w]


def pairs(upto=TRANSLATED_UPTO):
    """[(n, sid, ru_text, he_text)] по всем сегментам; кидает ValueError при рассинхроне."""
    ru = dict(load_ru(upto))
    he = dict(load_he(upto))
    out = []
    problems = []
    for n in sorted(ru):
        rsegs = ru[n]
        hsegs = dict(he.get(n, []))
        for sid, rtext in rsegs:
            htext = hsegs.get(sid)
            if htext is None:
                problems.append("нет оригинала для сегмента %s" % sid)
                htext = ""
            out.append((n, sid, rtext, htext))
    return out, problems


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ps, probs = pairs()
    print("сегментов:", len(ps))
    print("глав:", len(set(p[0] for p in ps)))
    print("проблем:", len(probs))
    for p in probs:
        print("  !", p)
    lens = sorted((len(r) + len(h), sid) for _, sid, r, h in ps)
    print("самые длинные:", lens[-5:])
    print("самые короткие:", lens[:3])
    print("сумма символов:", sum(l for l, _ in lens))
