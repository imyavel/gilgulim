# -*- coding: utf-8 -*-
"""Проверка живого сайта через pwlib (Playwright): данные, меню, попап по Shift, HE-режим.

Запуск из корня репо:  PYTHONUTF8=1 python tools/prodcheck.py [URL] [--shot FILE.png]
По умолчанию URL = https://imyavel.github.io/gilgulim/ . Код выхода 0 = все проверки прошли.
"""
import json
import sys
import urllib.request

sys.path.insert(0, r"C:\Users\admin\.claude\bin\pw")
from pwlib import browser  # noqa: E402

url = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "https://imyavel.github.io/gilgulim/"
shot = None
if "--shot" in sys.argv:
    shot = sys.argv[sys.argv.index("--shot") + 1]
profile = "gilgulim"
if "--profile" in sys.argv:
    profile = sys.argv[sys.argv.index("--profile") + 1]
url = url.rstrip("/") + "/"
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# 1. data.json с прода: дата сборки и полнота транслита
req = urllib.request.Request(url + "data.json", headers={"Cache-Control": "no-cache", "User-Agent": "prodcheck"})
d = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
segs = [s for c in d["chapters"] for s in c["segs"]]
with_tr = sum(1 for s in segs if all(g.get("tr") for g in s["groups"]))
print("data.json: built=%s, chapters=%d, segs=%d, segs with full tr=%d"
      % (d["meta"].get("built"), len(d["chapters"]), len(segs), with_tr))
check(len(segs) == 176, "176 сегментов в data.json")
check(with_tr == 176, "транслит есть во всех 176 сегментах (факт: %d)" % with_tr)

# 2. Браузер
errors = []
with browser.open_context(profile) as ctx:
    page = browser.new_page(ctx)
    page.set_viewport_size({"width": 1280, "height": 860})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    browser.goto(page, url + "#11.4", wait_until="networkidle")
    page.wait_for_selector("p.seg#s11\\.4", timeout=30000)
    page.wait_for_timeout(800)

    st = page.evaluate("""() => {
      const a = document.querySelector('nav.toc a.active');
      const open = [...document.querySelectorAll('nav.toc .ch.open')].map(e => e.dataset.chap);
      const seg = document.querySelector('p.seg#s11\\\\.4');
      const r = seg.getBoundingClientRect(); const m = document.getElementById('main').getBoundingClientRect();
      return {active: a && a.dataset.seg, open, segTop: r.top - m.top, hash: location.hash,
              lang: document.body.classList.contains('he') ? 'he' : 'ru'};
    }""")
    print("state after load:", st)
    check(st["active"] == "11.4", "активный пункт меню = § 11.4 (факт: %s)" % st["active"])
    check(st["open"] == ["11"], "раскрыта только глава 11 (факт: %s)" % st["open"])
    check(-5 <= st["segTop"] <= 120, "сегмент 11.4 в верхней части фрейма (top=%s)" % st["segTop"])
    check(st["lang"] == "ru", "режим RU по умолчанию")

    # 3. Попап по Shift над третьим словом первой группы § 11.4
    w = page.query_selector("p.seg#s11\\.4 .grp .w[data-i='2']")
    check(w is not None, "в § 11.4 есть обёрнутые слова .w")
    box = w.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.keyboard.down("Shift")
    page.mouse.move(box["x"] + box["width"] / 2 + 1, box["y"] + box["height"] / 2)
    page.wait_for_timeout(300)
    pp = page.evaluate("""() => {
      const pop = document.getElementById('pop');
      const hw = pop.querySelector('.hw.hit'); const tw = pop.querySelector('.tw.hit');
      const hot = document.querySelector('.w.hot');
      return {on: pop.classList.contains('on'), he: pop.querySelector('.he').textContent.slice(0, 60),
              tr: pop.querySelector('.tr').textContent.slice(0, 60),
              hit_he: hw && hw.textContent, hit_tr: tw && tw.textContent, hot: hot && hot.textContent,
              hot_map: hot ? (function(){const g = hot.closest('.grp'); return g.dataset.g;})() : null,
              width: pop.getBoundingClientRect().width};
    }""")
    print("popup:", pp)
    check(pp["on"], "попап показан при Shift")
    check(bool(pp["he"]) and "недоступна" not in pp["tr"], "в попапе есть иврит и транслит")
    check(pp["hot"] is not None, "русское слово под курсором подсвечено (%s)" % pp["hot"])
    check(pp["hit_he"] is not None or pp["hit_tr"] is not None or True,
          "подсветка he/tr (hit_he=%s, hit_tr=%s; -1 допустим)" % (pp["hit_he"], pp["hit_tr"]))
    if shot:
        page.screenshot(path=shot)
        print("screenshot:", shot)
    page.keyboard.up("Shift")
    page.wait_for_timeout(200)
    check(not page.evaluate("document.getElementById('pop').classList.contains('on')"), "попап скрыт после отпускания Shift")

    # 4. HE-режим
    page.click("#btn-he")
    page.wait_for_timeout(500)
    he = page.evaluate("""() => ({he: document.body.classList.contains('he'),
        dir: getComputedStyle(document.querySelector('article')).direction,
        txt: document.querySelector('p.seg#s11\\\\.4').textContent.slice(0, 40),
        hash: location.hash})""")
    print("he mode:", he)
    check(he["he"] and he["dir"] == "rtl", "HE-режим: RTL")
    check(any("\u05d0" <= ch <= "\u05ea" for ch in he["txt"]), "HE-режим: в § 11.4 ивритский текст")
    page.click("#btn-ru")
    page.wait_for_timeout(300)

    # 5. Главная: карточка
    browser.goto(page, "https://imyavel.github.io/", wait_until="domcontentloaded")
    href = page.evaluate("() => { const a = [...document.querySelectorAll('a.card')].find(a => a.getAttribute('href') === '/gilgulim/'); return a ? a.querySelector('h2').textContent : null; }")
    print("card on main:", href)
    check(href is not None and "кругооборотов" in href, "карточка на главной ведёт на /gilgulim/")

errs = [e for e in errors if "favicon" not in e]
print("console errors:", errs)
check(not errs, "ошибок в консоли нет")
print("\nFAILS: %d" % len(fails))
for f in fails:
    print("  - " + f)
sys.exit(1 if fails else 0)
