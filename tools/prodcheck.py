# -*- coding: utf-8 -*-
"""Проверка сайта через pwlib (Playwright): страницы глав, вход и старые ссылки, попап по Shift
(текст и заголовок «Глава N»), подсказка, RU/HE, пред./след., галка, мобильная раскладка.

Запуск из корня репо:
    PYTHONUTF8=1 python tools/prodcheck.py [URL] [--seg 11.4] [--shots DIR]

URL по умолчанию https://imyavel.github.io/gilgulim/ ; локально — сервер, отдающий репо
под путём /gilgulim/ (не корнем). Якорный сегмент --seg (по умолчанию 11.4, длинный — иначе
скроллспай уводит активный пункт). Ожидаемые главы и сегменты берутся из локальной сборки
data.json. --shots DIR — сохранить скриншоты (десктоп 1920×1080 и телефон 375×812).
Код выхода 0 = все проверки прошли.
"""
import argparse
import io
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, r"C:\Users\admin\.claude\bin\pw")
from pwlib import browser  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ap = argparse.ArgumentParser()
ap.add_argument("url", nargs="?", default="https://imyavel.github.io/gilgulim/")
ap.add_argument("--seg", default="11.4", help="якорный сегмент проверки (по умолчанию 11.4)")
ap.add_argument("--shots", help="каталог для скриншотов")
ap.add_argument("--profile", default="gilgulim")
args = ap.parse_args()

url = args.url.rstrip("/") + "/"
seg = args.seg
chap = int(seg.split(".")[0])
sel = "#s" + seg.replace(".", r"\.")        # CSS-селектор сегмента (точка в id экранируется)
shots = args.shots
if shots:
    os.makedirs(shots, exist_ok=True)

local = os.path.join(ROOT, "data.json")
if not os.path.exists(local):
    sys.exit("нет локального data.json — соберите (tools/build.py)")
book = json.load(io.open(local, encoding="utf-8"))
CHAPS = [c["n"] for c in book["chapters"]]
COUNTS = dict((c["n"], len(c["segs"])) for c in book["chapters"])
expect_segs = sum(COUNTS.values())
LAST = CHAPS[-1]
print("ожидается из локального data.json: глав %d, сегментов %d" % (len(CHAPS), expect_segs))

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# --------------------------------------------- эталон ивритских чисел (независимо от app.js)
def heb_num(n):
    ones, tens, hundreds = u"אבגדהוזחט", u"יכלמנסעפצ", u"קרשת"
    s = u"ת" * (n // 400)
    n %= 400
    if n >= 100:
        s += hundreds[n // 100 - 1]
        n %= 100
    if n in (15, 16):
        s += u"ט" + ones[n - 10]
    else:
        if n >= 10:
            s += tens[n // 10 - 1]
        if n % 10:
            s += ones[n % 10 - 1]
    return s + u"\u05F3" if len(s) == 1 else s[:-1] + u"\u05F4" + s[-1]


NAMES = dict(zip(u"אבגדהוזחטיכלמנסעפצקרשת", [
    u"алеф", u"бет", u"гимель", u"далет", u"ѓей", u"вав", u"заин", u"хет", u"тет", u"йуд", u"каф",
    u"ламед", u"мем", u"нун", u"самех", u"аин", u"пе", u"цади", u"куф", u"реш", u"шин", u"тав"]))


def heb_title(n):
    return u"הקדמה " + heb_num(n)


def heb_tr(n):
    return u"ѓакдама " + u"-".join(NAMES[c] for c in heb_num(n) if c in NAMES)


def fetch(path):
    req = urllib.request.Request(url + path, headers={"Cache-Control": "no-cache", "User-Agent": "prodcheck"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode("utf-8")


# 1. data.json (полный артефакт сборки) и все страницы глав по HTTP
_, body = fetch("data.json")
d = json.loads(body)
segs = [s for c in d["chapters"] for s in c["segs"]]
with_tr = sum(1 for s in segs if all(g.get("tr") for g in s["groups"]))
print("data.json: built=%s, chapters=%d, segs=%d, segs with full tr=%d"
      % (d["meta"].get("built"), len(d["chapters"]), len(segs), with_tr))
check(len(segs) == expect_segs, "%d сегментов в data.json (факт: %d)" % (expect_segs, len(segs)))
check(with_tr == expect_segs, "транслит есть во всех %d сегментах (факт: %d)" % (expect_segs, with_tr))

bad = []
for n in CHAPS:
    try:
        st, html = fetch("%d.html" % n)
    except Exception as e:  # noqa: BLE001 — 404 и сеть
        bad.append("%d.html: %s" % (n, e))
        continue
    need = [u"<title>Глава %d · Врата кругооборотов</title>" % n,
            u'<link rel="canonical" href="https://imyavel.github.io/gilgulim/%d.html">' % n,
            u'<meta property="og:url" content="https://imyavel.github.io/gilgulim/%d.html">' % n,
            u'<meta name="description" content="']
    miss = [x for x in need if x not in html]
    if st != 200 or miss:
        bad.append("%d.html: status %s, нет %s" % (n, st, miss))
check(not bad, "все %d страниц отдают 200, title/canonical/og:url/description на месте %s"
      % (len(CHAPS), bad[:3] if bad else ""))

# 2. Браузер
errors, requests = [], []
HE_RE = u"[\u05d0-\u05ea]"


def state(page):
    return page.evaluate("""(sel) => {
      const a = document.querySelector('nav.toc li a.active');
      const open = [...document.querySelectorAll('nav.toc .ch.open > a')].map(e => +e.dataset.chap);
      const seg = document.querySelector(sel);
      const m = document.getElementById('main').getBoundingClientRect();
      return {path: location.pathname.split('/').pop(), hash: location.hash,
              active: a && a.dataset.seg, open, cls: document.documentElement.className,
              segTop: seg ? seg.getBoundingClientRect().top - m.top : null};
    }""", sel)


def wait_path(page, name, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if page.url.split("#")[0].endswith("/" + name):
            break
        page.wait_for_timeout(200)
    page.wait_for_load_state("load")
    page.wait_for_timeout(700)


def open_page(page, path):
    if page.url.split("#")[0] == (url + path).split("#")[0]:
        page.goto("about:blank")      # иначе смена одного hash — без перезагрузки страницы
    browser.goto(page, url + path, wait_until="load")
    page.wait_for_timeout(700)


def shot(page, name):
    if shots:
        p = os.path.join(shots, name)
        page.screenshot(path=p)
        print("screenshot:", p)


def visible(page, css):
    return page.evaluate("(s) => { const e = document.querySelector(s); return !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden'; }", css)


def hover_word(page, grp_css, i):
    """Навести мышь с Shift на слово i группы (слова оборачиваются при первом наведении)."""
    r = page.evaluate("(s) => { const g = document.querySelector(s); g.scrollIntoView({block: 'center'}); const r = g.getClientRects()[0]; return {x: r.left + 4, y: r.top + r.height / 2}; }", grp_css)
    page.wait_for_timeout(300)
    page.mouse.move(r["x"], r["y"])
    page.keyboard.down("Shift")
    page.mouse.move(r["x"] + 1, r["y"])
    page.wait_for_timeout(200)
    w = page.evaluate("([s, i]) => { const w = document.querySelector(s + ' .w[data-i=\"' + i + '\"]'); if (!w) return null; const r = w.getClientRects()[0]; return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }", [grp_css, i])
    if w:
        page.mouse.move(w["x"], w["y"])
        page.mouse.move(w["x"] + 1, w["y"])
        page.wait_for_timeout(250)
    return page.evaluate("""() => {
      const pop = document.getElementById('pop');
      const q = (s) => { const e = document.querySelector(s); return e && e.textContent; };
      return {on: pop.classList.contains('on'), he: pop.querySelector('.he').textContent,
              tr: pop.querySelector('.tr').textContent, hot: q('#art .w.hot'),
              hit_he: q('#pop .hw.hit'), hit_tr: q('#pop .tw.hit')};
    }""")


with browser.open_context(args.profile) as ctx:
    page = browser.new_page(ctx)
    page.set_viewport_size({"width": 1920, "height": 1080})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))

    open_page(page, "1.html")
    page.evaluate("localStorage.clear()")

    # 2.1 вход и старая ссылка
    open_page(page, "")
    wait_path(page, "1.html")
    check(page.url.split("#")[0].endswith("/1.html"), "/gilgulim/ → 1.html (факт: %s)" % page.url)
    open_page(page, "#" + seg)
    wait_path(page, "%d.html" % chap)
    st = state(page)
    print("state after old link:", st)
    check(st["path"] == "%d.html" % chap and st["hash"] == "#" + seg,
          "/gilgulim/#%s → %d.html#%s (факт: %s%s)" % (seg, chap, seg, st["path"], st["hash"]))
    check(st["active"] == seg, "активный пункт меню = § %s (факт: %s)" % (seg, st["active"]))
    check(st["open"] == [chap], "раскрыта только глава %d (факт: %s)" % (chap, st["open"]))
    check(st["segTop"] is not None and -5 <= st["segTop"] <= 120, "§ %s в верхней части фрейма (top=%s)" % (seg, st["segTop"]))
    check("he" not in st["cls"].split() and "wait" not in st["cls"].split(), "режим RU по умолчанию, статья показана (class=%r)" % st["cls"])

    # 2.2 RU: «Глава N», подсказка
    ru = page.evaluate("""() => ({toc: [...document.querySelectorAll('nav.toc .ch > a')].map(a => a.textContent),
        h2: document.querySelector('#art h2').innerText.trim(), title: document.title,
        hint: document.querySelector('#side .hint').textContent.replace(/\\s+/g, ' ').trim()})""")
    check(ru["toc"] == [u"Глава %d" % n for n in CHAPS], "RU: оглавление «Глава 1» … «Глава %d»" % LAST)
    check(ru["h2"] == u"Глава %d" % chap, "RU: заголовок «Глава %d» (факт: %s)" % (chap, ru["h2"]))
    check(ru["title"] == u"Глава %d · Врата кругооборотов" % chap, "RU: <title> (факт: %s)" % ru["title"])
    check(visible(page, "#side .hint") and ru["hint"] == u"Для транслитерации зажмите Shift и водите мышью",
          "RU: подсказка видна, текст дословно (%s)" % ru["hint"])
    shot(page, "desk-ru.png")

    # 2.3 ивритские числа в app.js против эталона
    js = page.evaluate("() => ({num: Array.from({length: 200}, (_, i) => gilgulimHeb.num(i + 1)), tr: Array.from({length: %d}, (_, i) => gilgulimHeb.tr(i + 1))})" % LAST)
    bad_num = [n for n in range(1, 201) if js["num"][n - 1] != heb_num(n)]
    bad_tr = [n for n in range(1, LAST + 1) if js["tr"][n - 1] != heb_tr(n)]
    check(not bad_num, u"ивритские числа 1–200 совпали с эталоном (15=%s, 16=%s, 184=%s) %s"
          % (js["num"][14], js["num"][15], js["num"][183], bad_num[:5]))
    check(not bad_tr, u"транслит названий 1–%d (11: %s) %s" % (LAST, js["tr"][10], bad_tr[:5]))

    # 2.4 попап на тексте: слово с парой в оригинале
    g0 = page.evaluate("(id) => { const d = JSON.parse(document.getElementById('data').textContent); return d.segs.find(s => s[0] === id)[1][0]; }", seg)
    ru_words = page.evaluate("""(s) => (document.querySelector(s).textContent.match(/[\\p{L}\\p{N}]+(?:["'’ʼ‑-][\\p{L}\\p{N}]+)*/gu) || [])""",
                             sel + ' .grp[data-g="0"]')
    wi = next((i for i, j in enumerate(g0[2]) if j >= 0 and len(ru_words[i]) >= 3), None)
    check(wi is not None, "в § %s есть слово с парой в оригинале" % seg)
    pp = hover_word(page, sel + ' .grp[data-g="0"]', wi)
    want_he, want_tr = g0[0].split()[g0[2][wi]], g0[1].split()[g0[2][wi]]
    print("popup on text:", {k: (v[:60] if isinstance(v, str) else v) for k, v in pp.items()})
    check(pp["on"] and pp["he"].strip() == " ".join(g0[0].split()), "попап по Shift на тексте: иврит группы")
    check(pp["tr"].strip() == " ".join(g0[1].split()), "попап на тексте: транслит группы")
    check(pp["hot"] == ru_words[wi] and pp["hit_he"] == want_he and pp["hit_tr"] == want_tr,
          u"подсветка: «%s» ↔ %s / %s (факт: %s ↔ %s / %s)"
          % (ru_words[wi], want_he, want_tr, pp["hot"], pp["hit_he"], pp["hit_tr"]))
    shot(page, "desk-ru-popup.png")
    page.keyboard.up("Shift")
    page.wait_for_timeout(200)
    check(not page.evaluate("document.getElementById('pop').classList.contains('on')"), "попап скрыт после отпускания Shift")

    # 2.5 попап на заголовке «Глава N»
    page.evaluate("document.getElementById('main').scrollTop = 0")
    page.wait_for_timeout(300)
    h0 = hover_word(page, "#art h2 .grp", 0)
    check(h0["on"] and h0["he"] == heb_title(chap) and h0["tr"] == heb_tr(chap),
          u"попап на заголовке: %s / %s (факт: %s / %s)" % (heb_title(chap), heb_tr(chap), h0["he"], h0["tr"]))
    check(h0["hot"] == u"Глава" and h0["hit_he"] == u"הקדמה" and h0["hit_tr"] == u"ѓакдама",
          u"подсветка «Глава» ↔ הקדמה / ѓакдама (факт: %s ↔ %s / %s)" % (h0["hot"], h0["hit_he"], h0["hit_tr"]))
    shot(page, "desk-ru-heading-popup.png")
    h1 = hover_word(page, "#art h2 .grp", 1)
    check(h1["hot"] == str(chap) and h1["hit_he"] == heb_num(chap) and h1["hit_tr"] == heb_tr(chap).split(" ")[1],
          u"подсветка «%d» ↔ %s / %s (факт: %s ↔ %s / %s)"
          % (chap, heb_num(chap), heb_tr(chap).split(" ")[1], h1["hot"], h1["hit_he"], h1["hit_tr"]))
    page.keyboard.up("Shift")
    page.mouse.move(5, 5)

    # 2.6 пред./след.
    pn = page.evaluate("""() => [...document.querySelectorAll('nav.pn a')].map(a => [a.className, a.getAttribute('href'), a.innerText.trim()])""")
    check(pn == [["prev", "%d.html" % (chap - 1), u"← Глава %d" % (chap - 1)],
                 ["next", "%d.html" % (chap + 1), u"Глава %d →" % (chap + 1)]],
          u"глава %d: ссылки пред./след. (факт: %s)" % (chap, pn))
    page.click("nav.pn a.next")
    wait_path(page, "%d.html" % (chap + 1))
    st = page.evaluate("() => ({path: location.pathname.split('/').pop(), top: document.getElementById('main').scrollTop, active: (document.querySelector('nav.toc li a.active') || {dataset: {}}).dataset.seg})")
    check(st["path"] == "%d.html" % (chap + 1) and st["top"] < 5 and st["active"] == "%d.1" % (chap + 1),
          u"клик «след.» → %d.html, вверху заголовок, активен § %d.1 (факт: %s)" % (chap + 1, chap + 1, st))
    open_page(page, "%d.html" % CHAPS[0])
    pn1 = page.evaluate("() => [...document.querySelectorAll('nav.pn a')].map(a => a.className)")
    check(pn1 == ["next"], u"глава %d: только «след.» (факт: %s)" % (CHAPS[0], pn1))
    open_page(page, "%d.html" % LAST)
    endst = page.evaluate("""() => { const pn = document.querySelector('nav.pn'), e = document.querySelector('.end-note');
        return {links: [...pn.querySelectorAll('a')].map(a => a.className), note: e && e.textContent,
                after: !!e && !!(pn.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING)}; }""")
    check(endst["links"] == ["prev"] and endst["after"] and (endst["note"] or "").startswith(u"Конец"),
          u"глава %d: только «пред.», после неё концовка (%s)" % (LAST, endst["note"]))
    page.evaluate("document.querySelector('.end-note').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(400)
    shot(page, "desk-%d-end.png" % LAST)

    # 2.7 галка: ставится на странице N, видна со страницы M на строке главы N и не стирается
    mark_seg = "%d.%d" % (chap, min(6, COUNTS[chap]))
    open_page(page, "%d.html" % chap)
    for _ in range(2):   # первый клик переводит, второй ставит галку
        page.click('nav.toc a[data-seg="%s"]' % mark_seg)
        page.wait_for_timeout(900)
    m1 = page.evaluate("(s) => ({ls: localStorage.getItem('gilgulim-mark'), on: document.querySelector('nav.toc a[data-seg=\"' + s + '\"]').classList.contains('marked')})", mark_seg)
    check(m1["ls"] == mark_seg and m1["on"], u"галка на § %s поставлена (%s)" % (mark_seg, m1))
    other = chap + 1 if chap < LAST else chap - 1
    open_page(page, "%d.html" % other)
    m2 = page.evaluate("(n) => ({ls: localStorage.getItem('gilgulim-mark'), marked: [...document.querySelectorAll('nav.toc .marked')].map(e => e.dataset.chap || e.dataset.seg)})", chap)
    check(m2["ls"] == mark_seg and m2["marked"] == [str(chap)],
          u"со страницы %d галка на строке главы %d и не стёрта (факт: %s)" % (other, chap, m2))
    open_page(page, "%d.html" % chap)
    m3 = page.evaluate("() => [...document.querySelectorAll('nav.toc .marked')].map(e => e.dataset.seg || e.dataset.chap)")
    check(m3 == [mark_seg], u"вернулись на %d.html — галка на § %s (факт: %s)" % (chap, mark_seg, m3))
    page.evaluate("localStorage.removeItem('gilgulim-mark')")

    # 2.8 HE
    open_page(page, "%d.html#%s" % (chap, seg))
    page.click("#btn-he")
    page.wait_for_timeout(600)
    he = page.evaluate("""(sel) => {
      const toc = document.getElementById('toc'), art = document.getElementById('art');
      const vis = (e) => e && e.getClientRects().length > 0;
      return {cls: document.documentElement.className, dir: toc.getAttribute('dir'), lang: toc.getAttribute('lang'),
        chaps: [...toc.querySelectorAll('.ch > a')].map(a => a.textContent),
        paras: [...toc.querySelectorAll('li a')].map(a => a.textContent),
        tocText: toc.innerText, artText: art.innerText,
        h2: art.querySelector('h2').innerText.trim(), h2vis: vis(art.querySelector('h2')),
        seg: document.querySelector(sel).innerText.trim().slice(0, 60),
        artDir: getComputedStyle(art).direction,
        pn: [...art.querySelectorAll('nav.pn a')].map(a => a.innerText.trim()),
        head: document.querySelector('#side h1').textContent + ' | ' + document.querySelector('#side .sub').textContent};
    }""", sel)
    print("HE:", {k: he[k] for k in ("cls", "dir", "lang", "h2", "seg", "artDir", "pn")})
    check("he" in he["cls"].split() and he["artDir"] == "rtl", "HE: режим включён, текст RTL")
    check(he["dir"] == "rtl" and he["lang"] == "he", "HE: оглавление dir=rtl lang=he")
    check(he["chaps"] == [heb_title(n) for n in CHAPS], u"HE: главы в оглавлении «%s» … «%s»" % (heb_title(1), heb_title(LAST)))
    check(he["paras"] == [heb_num(i) for i in range(1, COUNTS[chap] + 1)],
          u"HE: параграфы — номера буквами (%s)" % " ".join(he["paras"][:6]))
    check(u"Глава" not in he["tocText"] and u"Глава" not in he["artText"] and "§" not in he["tocText"],
          u"HE: «Глава N» и «§» нет в оглавлении и тексте")
    check(he["h2"] == heb_title(chap) and he["h2vis"], u"HE: заголовок «%s» (факт: %s)" % (heb_title(chap), he["h2"]))
    num = int(seg.split(".")[1])
    check(he["seg"].startswith(u"[%s]" % heb_num(num)) and any(u"\u05d0" <= ch <= u"\u05ea" for ch in he["seg"][5:]),
          u"HE: метка «[%s]» и ивритский текст в § %s (%s)" % (heb_num(num), seg, he["seg"][:30]))
    check(he["pn"] == [u"→ " + heb_title(chap - 1), heb_title(chap + 1) + u" ←"], u"HE: пред./след. на иврите (%s)" % he["pn"])
    check(not visible(page, "#side .hint"), "HE: подсказка скрыта")
    check(he["head"] == u"Врата кругооборотов | Шаар ѓа-Гилгулим · р. Хаим Виталь по учению АРИ", "HE: шапка панели не изменилась")
    page.evaluate("document.getElementById('main').scrollTop = 0")
    page.wait_for_timeout(300)
    shot(page, "desk-he.png")
    open_page(page, "1.html")
    he1 = page.evaluate("""() => ({cls: document.documentElement.className, h2: document.getElementById('h1').getClientRects().length,
        first: document.getElementById('s1.1').innerText.trim().slice(0, 20), toc1: document.querySelector('nav.toc .ch > a').textContent})""")
    check("he" in he1["cls"].split() and he1["toc1"] == heb_title(1), u"HE сохраняется при переходе на другую страницу")
    check(he1["h2"] == 0 and he1["first"].startswith(u"[%s] הקדמה א" % heb_num(1)),
          u"HE, глава 1: сгенерированного заголовка нет, первым идёт § 1.1 (%s)" % he1["first"])
    page.click("#btn-ru")
    page.wait_for_timeout(300)
    back = page.evaluate("() => ({cls: document.documentElement.className, toc1: document.querySelector('nav.toc .ch > a').textContent})")
    check("he" not in back["cls"].split() and back["toc1"] == u"Глава 1" and visible(page, "#side .hint"),
          u"снова RU: «Глава 1», подсказка видна")

    # 2.9 чужой параграф на странице → его страница
    open_page(page, "5.html#7.3")
    wait_path(page, "7.html")
    st = state(page)
    check(st["path"] == "7.html" and st["hash"] == "#7.3", "5.html#7.3 → 7.html#7.3 (факт: %s%s)" % (st["path"], st["hash"]))

    # 2.10 мобильная раскладка: телефон с касаниями (pointer: coarse). Размер — через Playwright
    # (своё переопределение метрик по CDP он сбрасывает на скриншоте), касания — через CDP.
    page.set_viewport_size({"width": 375, "height": 812})
    cdp = ctx.new_cdp_session(page)
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})

    def tap(css):
        r = page.evaluate("(s) => { const e = document.querySelector(s); e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; }", css)
        page.wait_for_timeout(250)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": r["x"], "y": r["y"]}]})
        page.wait_for_timeout(60)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    open_page(page, "%d.html#%s" % (chap, seg))
    mob = page.evaluate("() => ({coarse: matchMedia('(pointer: coarse)').matches, w: innerWidth, burger: getComputedStyle(document.getElementById('burger')).display})")
    print("mobile:", mob)
    check(mob["coarse"] and mob["w"] == 375 and mob["burger"] != "none", "телефон: касания, 375 px, гамбургер виден")
    check(not visible(page, "#side .hint"), "телефон: подсказка скрыта")
    shot(page, "mob-ru.png")
    tap("#burger")
    page.wait_for_timeout(400)
    check(page.evaluate("document.body.classList.contains('menu')"), "телефон: тап по гамбургеру открывает меню")
    shot(page, "mob-menu.png")
    tap('nav.toc a[data-seg="%d.2"]' % chap)
    page.wait_for_timeout(700)
    ms = page.evaluate("() => ({menu: document.body.classList.contains('menu'), active: (document.querySelector('nav.toc li a.active') || {}).textContent})")
    check(not ms["menu"] and ms["active"] == u"§ %d.2" % chap, u"телефон: тап по § %d.2 — переход, меню закрыто (%s)" % (chap, ms))
    tap("#burger")
    page.wait_for_timeout(400)
    tap('nav.toc .ch > a[data-chap="%d"]' % (chap + 1))
    wait_path(page, "%d.html" % (chap + 1))
    ms = page.evaluate("() => ({path: location.pathname.split('/').pop(), hash: location.hash, top: document.getElementById('main').scrollTop, menu: document.body.classList.contains('menu')})")
    check(ms["path"] == "%d.html" % (chap + 1) and ms["hash"] == "#%d.1" % (chap + 1) and ms["top"] < 5 and not ms["menu"],
          u"телефон: тап по главе %d в меню — её страница с начала, меню закрыто (%s)" % (chap + 1, ms))
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": False})
    page.set_viewport_size({"width": 1920, "height": 1080})

    # 2.11 главная: карточка
    browser.goto(page, "https://imyavel.github.io/", wait_until="domcontentloaded")
    card = page.evaluate("() => { const a = [...document.querySelectorAll('a.card')].find(a => a.getAttribute('href') === '/gilgulim/'); return a ? a.querySelector('h2').textContent : null; }")
    print("card on main:", card)
    check(card is not None and u"кругооборотов" in card, "карточка на главной ведёт на /gilgulim/")

dj = [r for r in requests if r.split("?")[0].split("#")[0].endswith("/data.json")]
check(not dj, "страницы не запрашивают data.json (запросов: %d)" % len(dj))
errs = [e for e in errors if "favicon" not in e]
print("console errors:", errs)
check(not errs, "ошибок в консоли нет")
print("\nFAILS: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
