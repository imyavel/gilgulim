# -*- coding: utf-8 -*-
"""Сборка сайта из md-источников и кэша выравнивания.

Запуск из корня репо:  python tools/build.py
Пишет data.json (полный артефакт: вся книга, по нему сверяется prodcheck),
страницы глав 1.html … N.html по шаблону tools/page.html (русский текст главы —
в разметке, иврит/транслит/map только этой главы — встроенным JSON) и
index.html — переадресацию на главу 1 и со старых адресов #N.s.
Сегменты, для которых нет кэша выравнивания, всё равно попадают на сайт —
одной группой без транслита (попап для них не работает), и считаются в отчёте.
"""
import datetime
import hashlib
import html
import io
import json
import os
import re
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "align")
OUT = os.path.join(ROOT, "data.json")
TEMPLATE = os.path.join(ROOT, "tools", "page.html")
SITE = "https://imyavel.github.io/gilgulim/"
SITE_TITLE = u"Врата кругооборотов"
SITE_DESC = (u"Русский перевод книги «Шаар ѓа-Гилгулим» р. Хаима Виталя по учению АРИ, "
             u"с ивритским оригиналом и пословной транслитерацией.")


def chapter_title(n):
    """Как сайт называет главу по-русски (текст перевода не затрагивается)."""
    return u"Глава %d" % n


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


# ------------------------------------------------------------ страницы глав
def esc(text):
    return html.escape(text, quote=False)


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def asset(name):
    """Ссылка на общий файл с версией по содержимому — после деплоя браузер не
    возьмёт из кэша старый app.js к новой разметке."""
    with io.open(os.path.join(ROOT, name), "rb") as f:
        body = f.read().replace(b"\r\n", b"\n")
    return "%s?v=%s" % (name, hashlib.sha1(body).hexdigest()[:8])


def fill(template, values):
    """{{ключ}} → значение за один проход (подставленный текст не перечитывается)."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)], template)


def describe(ch, limit=150):
    """meta description: начало русского текста главы, по границе слова."""
    text = " ".join(g["ru"] for s in ch["segs"] for g in s["groups"])
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut.rstrip(u" ,;:—–-") + u"…"


def render_toc(chapters, n):
    """Все главы; у текущей — список параграфов (раскрыт)."""
    out = []
    for ch in chapters:
        if ch["n"] != n:
            out.append(u'<div class="ch"><a href="%d.html" data-chap="%d">%s</a></div>'
                       % (ch["n"], ch["n"], esc(ch["title"])))
            continue
        items = "".join(u'<li><a href="#%s" data-seg="%s">§ %s</a></li>' % (s["id"], s["id"], s["id"])
                        for s in ch["segs"])
        out.append(u'<div class="ch cur open"><a href="%d.html" data-chap="%d" aria-current="page">%s</a>'
                   u"<ul>%s</ul></div>" % (n, n, esc(ch["title"]), items))
    return "\n".join(out)


def render_article(ch, prev_ch, next_ch, note_end):
    """Русский текст главы. Группа выравнивания — <span class="grp" data-g=индекс>;
    слова в ней app.js оборачивает лениво, при первом наведении с Shift."""
    n = ch["n"]
    out = [u'<h2 id="h%d"><span class="ru"><span class="grp" data-g="h">%s</span></span></h2>'
           % (n, esc(ch["title"]))]
    for s in ch["segs"]:
        body = " ".join(u'<span class="grp" data-g="%d">%s</span>' % (gi, esc(g["ru"]))
                        for gi, g in enumerate(s["groups"]))
        out.append(u'<p class="seg" id="s%s"><span class="ru"><span class="lbl">[%s]</span> %s</span></p>'
                   % (s["id"], s["id"], body))
    links = []
    if prev_ch:
        links.append(u'<a class="prev" href="%d.html" rel="prev" data-chap="%d"><span class="ru">← %s</span></a>'
                     % (prev_ch["n"], prev_ch["n"], esc(prev_ch["title"])))
    if next_ch:
        links.append(u'<a class="next" href="%d.html" rel="next" data-chap="%d"><span class="ru">%s →</span></a>'
                     % (next_ch["n"], next_ch["n"], esc(next_ch["title"])))
    if links:
        out.append(u'<nav class="pn">%s</nav>' % "".join(links))
    if note_end:
        out.append(u'<p class="end-note" dir="ltr">%s</p>' % esc(note_end))
    return "\n".join(out)


def page_data(ch, counts):
    """Данные попапа и режима HE только этой главы. «<» экранирован: внутри
    <script> не может встретиться «</script>»."""
    d = {"n": ch["n"], "counts": counts,
         "segs": [[s["id"], [[g["he"], g["tr"], g["map"]] for g in s["groups"]]] for s in ch["segs"]]}
    return d, json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


class PageParser(HTMLParser):
    """Достаёт из готовой страницы тексты групп по параграфам и встроенный JSON."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.seg = None
        self.grp = None
        self.groups = {}
        self.in_data = False
        self.data = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "p" and a.get("class") == "seg":
            self.seg = a["id"][1:]
            self.groups[self.seg] = []
        elif tag == "span" and a.get("class") == "grp" and self.seg:
            self.grp = []
        elif tag == "script" and a.get("id") == "data":
            self.in_data = True

    def handle_endtag(self, tag):
        if tag == "span" and self.grp is not None:
            self.groups[self.seg].append("".join(self.grp))
            self.grp = None
        elif tag == "p":
            self.seg = None
        elif tag == "script":
            self.in_data = False

    def handle_data(self, text):
        if self.grp is not None:
            self.grp.append(text)
        if self.in_data:
            self.data.append(text)


def check_page(page, ch, data):
    """Текст перевода в разметке и данные в JSON — ровно те, что прошли check_groups."""
    p = PageParser()
    p.feed(page)
    p.close()
    errs = []
    want = dict((s["id"], [g["ru"] for g in s["groups"]]) for s in ch["segs"])
    if p.groups != want:
        bad = [sid for sid in want if p.groups.get(sid) != want[sid]]
        errs.append(u"текст в разметке не совпал: %s" % ", ".join(bad[:5] or ["лишние параграфы"]))
    try:
        if json.loads("".join(p.data)) != data:
            errs.append(u"встроенный JSON не совпал с данными главы")
    except ValueError as e:
        errs.append(u"встроенный JSON не читается: %s" % e)
    return errs


INDEX = u"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{title}}</title>
<script>
/* Вход на сайт — глава 1; старые адреса #N.s ведут на N.html#N.s, #N — на N.html. */
(function () {
  // число параграфов в главах 1…{{last}}
  var C = {{counts}};
  var h = location.hash.slice(1), to = "1.html";
  try { h = decodeURIComponent(h); } catch (e) {}
  var m = /^(\\d+)(?:\\.(\\d+))?$/.exec(h);
  var n = m ? parseInt(m[1], 10) : 0, s = m && m[2] ? parseInt(m[2], 10) : 0;
  if (n >= 1 && n <= C.length) {
    to = n + ".html";
    if (s >= 1 && s <= C[n - 1]) to += "#" + n + "." + s;
  }
  location.replace(to);
})();
</script>
<noscript><meta http-equiv="refresh" content="0; url=1.html"></noscript>
<meta name="description" content="{{desc}}">
<link rel="canonical" href="{{site}}1.html">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<meta name="theme-color" content="#6b2d5c">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Будущий Мир">
<meta property="og:locale" content="ru_RU">
<meta property="og:title" content="{{title}}">
<meta property="og:description" content="{{desc}}">
<meta property="og:url" content="{{site}}">
</head>
<body>
<p><a href="1.html">{{first}}</a></p>
</body>
</html>
"""


def build_pages(chapters, note_end):
    """Пишет N.html и index.html; возвращает [(имя, байт, доля главы в data.json, ошибки)]."""
    with io.open(TEMPLATE, encoding="utf-8") as f:
        template = re.sub(r"\{#.*?#\}\n?", "", f.read(), flags=re.S)
    counts = [len(c["segs"]) for c in chapters]
    for c in chapters:   # галка проверяется по числу § в главах — id должны идти подряд
        if [s["id"] for s in c["segs"]] != ["%d.%d" % (c["n"], i + 1) for i in range(len(c["segs"]))]:
            print(u"! глава %d: номера сегментов идут не подряд — проверка галки в app.js неточна" % c["n"])
    css, js = asset("app.css"), asset("app.js")
    names = set()
    out = []
    for i, ch in enumerate(chapters):
        prev_ch = chapters[i - 1] if i > 0 else None
        next_ch = chapters[i + 1] if i + 1 < len(chapters) else None
        data, data_json = page_data(ch, counts)
        name = "%d.html" % ch["n"]
        page = fill(template, {
            "title": esc(u"%s · %s" % (ch["title"], SITE_TITLE)),
            "description": html.escape(describe(ch)),
            "url": SITE + name,
            "css": css,
            "js": js,
            "toc": render_toc(chapters, ch["n"]),
            "article": render_article(ch, prev_ch, next_ch, note_end if next_ch is None else None),
            "data": data_json,
        })
        write_text(os.path.join(ROOT, name), page)
        names.add(name)
        share = len(json.dumps(ch, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        out.append((name, len(page.encode("utf-8")), share, check_page(page, ch, data)))
    for f in os.listdir(ROOT):           # страницы исчезнувших глав
        if re.match(r"^\d+\.html$", f) and f not in names:
            os.remove(os.path.join(ROOT, f))
            print(u"удалена устаревшая страница %s" % f)
    write_text(os.path.join(ROOT, "index.html"), fill(INDEX, {
        "title": esc(u"%s · Шаар ѓа-Гилгулим" % SITE_TITLE),
        "desc": html.escape(SITE_DESC),
        "site": SITE,
        "counts": json.dumps(counts, separators=(",", ":")),
        "last": str(chapters[-1]["n"]),
        "first": esc(u"%s · %s" % (SITE_TITLE, chapters[0]["title"])),
    }))
    return out


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
            cur = {"n": n, "title": chapter_title(n), "segs": []}
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

    # последняя опубликованная глава может быть переведена не целиком:
    # сверяем число её сегментов с оригиналом (глава из load_he не обрезается)
    last = chapters[-1]
    he_all = sources.load_he(10 ** 9)  # весь оригинал, без обрезки по TRANSLATED_UPTO
    he_total = len(dict(he_all).get(last["n"], []))
    # главы оригинала после последней опубликованной; пустые (без сегментов) не в счёт
    later = [(n, segs) for n, segs in he_all if n > last["n"]]
    complete = False
    if len(last["segs"]) < he_total:
        last_sid = last["segs"][-1]["id"]
        translated_upto = last_sid
        note_end = (u"Конец переведённого фрагмента (главы 1–%d и глава %d до § %s). "
                    u"Перевод продолжается." % (last["n"] - 1, last["n"], last_sid))
    elif all(not segs for _, segs in later):
        # опубликован весь текст оригинала
        complete = True
        translated_upto = str(sources.TRANSLATED_UPTO)
        note_end = u"Конец книги."   # решение оператора 2026-09-18: без перечня глав
    else:
        translated_upto = str(sources.TRANSLATED_UPTO)
        note_end = (u"Конец переведённого фрагмента (главы 1–%d). "
                    u"Перевод продолжается." % sources.TRANSLATED_UPTO)

    data = {
        "meta": {
            "title": SITE_TITLE,
            "subtitle": u"Шаар ѓа-Гилгулим · р. Хаим Виталь по учению АРИ",
            "translated_upto": translated_upto,
            "built": datetime.date.today().isoformat(),
            "note_end": note_end,
        },
        "chapters": chapters,
    }
    if complete:
        data["meta"]["complete"] = True
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(u"глав: %d" % len(chapters))
    print(u"последняя глава %d: %d из %d сегментов оригинала" % (last["n"], len(last["segs"]), he_total))
    print(u"сегментов: %d" % len(ps))
    print(u"групп: %d" % n_groups)
    print(u"сегментов без выравнивания (нет кэша): %d" % len(no_cache))
    if no_cache:
        print(u"   " + ", ".join(no_cache))
    print(u"сегментов с ошибками целостности: %d" % len(broken))
    for sid, why in broken:
        print(u"   %s — %s" % (sid, why))
    print(u"записано: %s (%.1f КБ)" % (OUT, os.path.getsize(OUT) / 1024.0))

    pages = build_pages(chapters, note_end)
    sizes = sorted((size, name) for name, size, _, _ in pages)
    ratios = sorted((float(size) / share, name) for name, size, share, _ in pages)
    bad_pages = [(name, errs) for name, _, _, errs in pages if errs]
    print(u"страниц глав: %d (%s … %s) + index.html (переадресация)" % (len(pages), pages[0][0], pages[-1][0]))
    print(u"вес страниц: min %.1f КБ (%s), max %.1f КБ (%s), сумма %.1f КБ"
          % (sizes[0][0] / 1024.0, sizes[0][1], sizes[-1][0] / 1024.0, sizes[-1][1],
             sum(sz for sz, _ in sizes) / 1024.0))
    print(u"вес страницы к доле её главы в data.json: min %.2f× (%s), max %.2f× (%s)"
          % (ratios[0][0], ratios[0][1], ratios[-1][0], ratios[-1][1]))
    over = [u"%s %.2f×" % (name, r) for r, name in ratios if r > 1.5]
    if over:
        print(u"   больше 1,5×: " + ", ".join(over))
    print(u"общие файлы: app.css %.1f КБ, app.js %.1f КБ"
          % (os.path.getsize(os.path.join(ROOT, "app.css")) / 1024.0,
             os.path.getsize(os.path.join(ROOT, "app.js")) / 1024.0))
    print(u"страниц с расхождением текста/данных: %d" % len(bad_pages))
    for name, errs in bad_pages:
        print(u"   %s — %s" % (name, "; ".join(errs)))
    return 1 if bad_pages else 0


if __name__ == "__main__":
    sys.exit(main())
