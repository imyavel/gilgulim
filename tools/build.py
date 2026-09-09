# -*- coding: utf-8 -*-
"""Сборка data.json из md-источников и кэша выравнивания.

Запуск из корня репо:  python tools/build.py
Сегменты, для которых нет кэша выравнивания, всё равно попадают на сайт —
одной группой без транслита (попап для них не работает), и считаются в отчёте.
"""
import datetime
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "align")
OUT = os.path.join(ROOT, "data.json")


def check_groups(sid, ru_text, he_text, groups):
    """Целостность: склейка групп == исходный текст; счётчики слов сходятся."""
    errs = []
    if sources.norm_chars("".join(g["ru"] for g in groups)) != sources.norm_chars(ru_text):
        errs.append(u"склейка ru не совпала с переводом")
    if sources.norm_chars("".join(g["he"] for g in groups)) != sources.norm_chars(he_text):
        errs.append(u"склейка he не совпала с оригиналом")
    for gi, g in enumerate(groups):
        hw = sources.he_words(g["he"])
        if len(sources.he_words(g["tr"])) != len(hw):
            errs.append(u"группа %d: слов в tr не столько же, сколько в he" % gi)
        rw = sources.ru_words(g["ru"])
        if len(g["map"]) != len(rw):
            errs.append(u"группа %d: длина map != числу слов ru" % gi)
        for v in g["map"]:
            if v < -1 or v >= len(hw):
                errs.append(u"группа %d: индекс map вне диапазона" % gi)
                break
    return errs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ps, problems = sources.pairs()
    for p in problems:
        print("!", p)

    chapters = []
    cur = None
    n_groups = 0
    no_cache = []
    broken = []

    for n, sid, ru_text, he_text in ps:
        if cur is None or cur["n"] != n:
            cur = {"n": n, "title": u"Хакдама %d" % n, "segs": []}
            chapters.append(cur)
        path = os.path.join(CACHE_DIR, sid + ".json")
        groups = None
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as f:
                groups = json.load(f).get("groups")
            errs = check_groups(sid, ru_text, he_text, groups)
            if errs:
                broken.append((sid, "; ".join(errs)))
                groups = None
        if groups is None:
            if sid not in [b[0] for b in broken]:
                no_cache.append(sid)
            # запасной вариант: сегмент виден на сайте, но без попапа
            groups = [{"he": he_text, "tr": "", "ru": ru_text,
                       "map": [-1] * len(sources.ru_words(ru_text))}]
        n_groups += len(groups)
        cur["segs"].append({"id": sid, "groups": groups})

    data = {
        "meta": {
            "title": u"Врата кругооборотов",
            "subtitle": u"Шаар ѓа-Гилгулим · р. Хаим Виталь по учению АРИ",
            "translated_upto": str(sources.TRANSLATED_UPTO),
            "built": datetime.date.today().isoformat(),
            "note_end": (u"Конец переведённого фрагмента (хакдамот 1–%d). "
                         u"Перевод продолжается." % sources.TRANSLATED_UPTO),
        },
        "chapters": chapters,
    }
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(u"глав: %d" % len(chapters))
    print(u"сегментов: %d" % len(ps))
    print(u"групп: %d" % n_groups)
    print(u"сегментов без выравнивания (нет кэша): %d" % len(no_cache))
    if no_cache:
        print(u"   " + ", ".join(no_cache))
    print(u"сегментов с ошибками целостности: %d" % len(broken))
    for sid, why in broken:
        print(u"   %s — %s" % (sid, why))
    print(u"записано: %s (%.1f КБ)" % (OUT, os.path.getsize(OUT) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
