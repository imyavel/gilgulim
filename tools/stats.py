# -*- coding: utf-8 -*-
"""Статистика качества выравнивания по кэшу data/align/.

Запуск из корня репо:  python tools/stats.py
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "align")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ps, _ = sources.pairs()
    n_seg = n_grp = n_ru = n_he = n_minus = 0
    big = []          # группы длиннее 400 символов ru
    ru_per_grp = []
    for _, sid, ru_text, he_text in ps:
        p = os.path.join(CACHE_DIR, sid + ".json")
        if not os.path.exists(p):
            continue
        groups = json.load(io.open(p, encoding="utf-8"))["groups"]
        n_seg += 1
        n_grp += len(groups)
        for g in groups:
            rw = sources.ru_words(g["ru"])
            n_ru += len(rw)
            n_he += len(sources.he_words(g["he"]))
            n_minus += sum(1 for v in g["map"] if v < 0)
            ru_per_grp.append(len(rw))
            if len(g["ru"]) > 400:
                big.append((sid, len(g["ru"])))
    if not n_seg:
        print("кэш пуст")
        return
    ru_per_grp.sort()
    print(u"сегментов в кэше: %d" % n_seg)
    print(u"групп: %d (в среднем %.1f на сегмент)" % (n_grp, n_grp / float(n_seg)))
    print(u"слов ru: %d, слов he: %d" % (n_ru, n_he))
    print(u"слов ru на группу: медиана %d, минимум %d, максимум %d"
          % (ru_per_grp[len(ru_per_grp) // 2], ru_per_grp[0], ru_per_grp[-1]))
    print(u"доля слов ru без пары в оригинале (map = -1): %.1f%%" % (100.0 * n_minus / n_ru))
    print(u"групп длиннее 400 символов: %d" % len(big))
    if big:
        print(u"   " + ", ".join("%s (%d)" % b for b in big[:10]))


if __name__ == "__main__":
    main()
