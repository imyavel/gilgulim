/* Врата кругооборотов — логика страницы главы (общая для 1.html … 40.html).
   Русский текст главы лежит в разметке; иврит, транслит и пословные
   соответствия этой главы — в <script id="data" type="application/json">. */
"use strict";
(function () {
  var root = document.documentElement;
  var main = document.getElementById("main");
  var art = document.getElementById("art");
  var toc = document.getElementById("toc");
  var pop = document.getElementById("pop");
  var popHe = pop.querySelector(".he");
  var popTr = pop.querySelector(".tr");

  // {n: номер главы, counts: [число § в главах 1…last], segs: [[id, [[he, tr, map], …]], …]}
  var D = JSON.parse(document.getElementById("data").textContent);
  var N = D.n;
  var COUNTS = D.counts;
  var firstSeg = D.segs.length ? D.segs[0][0] : null;

  /* "11.4" → [11, 4]; "11" → [11, 0]; иначе null */
  function parseId(s) {
    var m = /^(\d+)(?:\.(\d+))?$/.exec(s || "");
    return m ? [parseInt(m[1], 10), m[2] ? parseInt(m[2], 10) : 0] : null;
  }
  function knownChap(n) { return n >= 1 && n <= COUNTS.length; }
  function knownSeg(p) { return !!p && knownChap(p[0]) && p[1] >= 1 && p[1] <= COUNTS[p[0] - 1]; }

  // ------------------------------------- адрес чужой главы → её страница
  function readHash() {
    var h = location.hash.replace(/^#/, "");
    try { h = decodeURIComponent(h); } catch (e) { /* оставляем как есть */ }
    return h;
  }
  function foreign(p) { return !!p && p[0] !== N && knownChap(p[0]); }
  function leaveFor(p) {
    location.replace(p[0] + ".html" + (knownSeg(p) ? "#" + p[0] + "." + p[1] : ""));
  }
  var hash = readHash();
  var hp = parseId(hash);
  if (foreign(hp)) { leaveFor(hp); return; }

  // ------------------------------------------------------ ивритские числа
  /* Буквенная запись числа: одна буква — с герешем (א׳), несколько —
     гершаим перед последней (י״א, קפ״ד); 15 и 16 — ט״ו, ט״ז. */
  var ONES = "אבגדהוזחט", TENS = "יכלמנסעפצ", HUNDREDS = "קרשת";
  function hebNum(n) {
    var s = "";
    for (; n >= 400; n -= 400) s += "ת";
    if (n >= 100) { s += HUNDREDS.charAt(Math.floor(n / 100) - 1); n %= 100; }
    if (n === 15 || n === 16) { s += "ט" + ONES.charAt(n - 10); n = 0; }
    if (n >= 10) { s += TENS.charAt(Math.floor(n / 10) - 1); n %= 10; }
    if (n) s += ONES.charAt(n - 1);
    return s.length === 1 ? s + "׳" : s.slice(0, -1) + "״" + s.slice(-1);
  }

  var LETTER = {
    "א": "алеф", "ב": "бет", "ג": "гимель", "ד": "далет", "ה": "ѓей", "ו": "вав",
    "ז": "заин", "ח": "хет", "ט": "тет", "י": "йуд", "כ": "каф", "ל": "ламед",
    "מ": "мем", "נ": "нун", "ס": "самех", "ע": "аин", "פ": "пе", "צ": "цади",
    "ק": "куф", "ר": "реш", "ש": "шин", "ת": "тав"
  };
  function chapHe(n) { return "הקדמה " + hebNum(n); }
  /* Транслит названия: номер читается названиями букв через дефис (ѓакдама йуд-алеф). */
  function chapTr(n) {
    return "ѓакдама " + hebNum(n).replace(/[׳״]/g, "").split("").map(function (c) {
      return LETTER[c];
    }).join("-");
  }
  window.gilgulimHeb = { num: hebNum, title: chapHe, tr: chapTr };   // для prodcheck

  // группы попапа: "11.4:0" -> [he, tr, map]; "h" — заголовок «Глава N» (слова ↔ «הקדמה», номер)
  var GROUPS = { h: [chapHe(N), chapTr(N), [0, 1]] };
  D.segs.forEach(function (s) {
    s[1].forEach(function (g, i) { GROUPS[s[0] + ":" + i] = g; });
  });

  var lang = localStorage.getItem("gilgulim-lang") === "he" ? "he" : "ru";
  var curSeg = null, collapsed = false;
  var markSeg = localStorage.getItem("gilgulim-mark") || null;   // отметка читателя, одна на книгу

  // Слово: буквы/цифры, склеенные дефисом, апострофом или гершаимом.
  // Та же логика, что в tools/sources.py (RU_WORD) — от неё зависит индексация map.
  var WORD = /[\p{L}\p{N}]+(?:["'’ʼ‑-][\p{L}\p{N}]+)*/gu;

  function narrow() {                        // телефонная раскладка с гамбургером
    return window.matchMedia("(max-width: 900px)").matches;
  }

  function each(sel, fn, box) {
    Array.prototype.forEach.call((box || document).querySelectorAll(sel), fn);
  }

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* Оборачивает слова в <span class="w" data-i>, пунктуацию оставляет снаружи. */
  function wrapWords(text, cls) {
    var out = "", last = 0, i = 0, m;
    WORD.lastIndex = 0;
    while ((m = WORD.exec(text)) !== null) {
      out += esc(text.slice(last, m.index));
      out += '<span class="' + cls + '" data-i="' + i + '">' + esc(m[0]) + "</span>";
      last = m.index + m[0].length;
      i++;
    }
    return out + esc(text.slice(last));
  }

  /* Иврит и транслит режутся по пробелам — счёт слов совпадает с данными. */
  function wrapSpaced(text, cls) {
    var parts = text.split(/\s+/).filter(Boolean);
    return parts.map(function (w, i) {
      return '<span class="' + cls + '" data-i="' + i + '">' + esc(w) + "</span>";
    }).join(" ");
  }

  // ------------------------------------------------------------ режим HE
  function heSpan(text) {
    var sp = document.createElement("span");
    sp.className = "he";
    sp.lang = "he";
    sp.dir = "rtl";
    sp.textContent = text;
    return sp;
  }

  /* Ивритская версия главы строится один раз, рядом с русской; видимость
     переключает класс html.he. Id заголовка и параграфов общие. */
  var heBuilt = false;
  function buildHe() {
    if (heBuilt) return;
    heBuilt = true;
    var h2 = document.getElementById("h" + N);
    if (N === 1) h2.classList.add("nohe");   // заголовок главы 1 — сам § 1.1 «הקדמה א»
    else h2.appendChild(heSpan(chapHe(N)));
    D.segs.forEach(function (s) {
      var p = document.getElementById("s" + s[0]);
      if (!p) return;
      var sp = heSpan(" " + s[1].map(function (g) { return g[0]; }).join(" "));
      var lbl = document.createElement("span");
      lbl.className = "lbl";
      lbl.textContent = "[" + hebNum(parseId(s[0])[1]) + "]";
      sp.insertBefore(lbl, sp.firstChild);
      p.appendChild(sp);
    });
    each("nav.pn a", function (a) {                // стрелки наружу при чтении справа налево
      var t = chapHe(parseInt(a.dataset.chap, 10));
      a.appendChild(heSpan(a.classList.contains("prev") ? "→ " + t : t + " ←"));
    }, art);
  }

  function tocLang() {
    var he = lang === "he";
    toc.lang = he ? "he" : "ru";
    toc.dir = he ? "rtl" : "ltr";
    each("a", function (a) {
      if (!a.dataset.ru) a.dataset.ru = a.textContent;
      if (!he) a.textContent = a.dataset.ru;
      else if (a.dataset.seg) a.textContent = hebNum(parseId(a.dataset.seg)[1]);
      else a.textContent = chapHe(parseInt(a.dataset.chap, 10));
    }, toc);
  }

  function setLang(l) {
    lang = l;
    if (lang === "he") buildHe();
    root.classList.toggle("he", lang === "he");
    document.getElementById("btn-ru").classList.toggle("on", lang === "ru");
    document.getElementById("btn-he").classList.toggle("on", lang === "he");
    tocLang();
  }

  // ------------------------------------------------------- отметка (галка)
  /* Ставится вторым кликом по пункту оглавления, одна на всю книгу, живёт в
     localStorage. Привязана к параграфу; если его глава свёрнута или это
     другая глава — показывается на строке главы. Скроллинг её не меняет. */
  function renderMark() {
    each(".marked", function (el) { el.classList.remove("marked"); }, toc);
    var p = parseId(markSeg);
    if (!p) return;
    var el = (p[0] === N && !collapsed) ? toc.querySelector('a[data-seg="' + markSeg + '"]') : null;
    if (!el) el = toc.querySelector('.ch > a[data-chap="' + p[0] + '"]');
    if (el) el.classList.add("marked");
  }

  function toggleMark(segId) {
    markSeg = (markSeg === segId) ? null : segId;
    if (markSeg) localStorage.setItem("gilgulim-mark", markSeg);
    else localStorage.removeItem("gilgulim-mark");
    renderMark();
  }

  // ------------------------------------------------------- активный параграф
  function setActive(segId) {
    if (segId === curSeg) return;
    curSeg = segId;
    each("li a", function (a) {
      var on = a.dataset.seg === segId;
      a.classList.toggle("active", on);
      if (on && !collapsed) a.scrollIntoView({ block: "nearest" });
    }, toc);
    if (history.replaceState) history.replaceState(null, "", "#" + segId);
  }

  /* Активен последний сегмент, начавшийся выше верхней трети фрейма.
     Во время программного перехода (goto) молчит: активным остаётся тот
     пункт, по которому кликнули, — от этого зависит простановка галки. */
  var lockSpy = false, lockIdle = null, lockHard = null;

  function lockOn() {                    // начался программный переход
    lockSpy = true;
    clearTimeout(lockHard);
    lockHard = setTimeout(unlock, 3000); // страховка: скролл не случился вовсе
    bump();
  }
  function bump() {                      // скролл ещё едет — держим подавление
    clearTimeout(lockIdle);
    lockIdle = setTimeout(unlock, 160);  // 160 мс тишины = приехали
  }
  function unlock() {
    clearTimeout(lockIdle);
    clearTimeout(lockHard);
    lockSpy = false;
  }

  function spy() {
    if (lockSpy) return;
    var top = main.getBoundingClientRect().top;
    var line = top + main.clientHeight / 3;
    var segs = art.querySelectorAll("p.seg");
    var found = null;
    for (var i = 0; i < segs.length; i++) {
      if (segs[i].getBoundingClientRect().top <= line) found = segs[i];
      else break;
    }
    if (!found && segs.length) found = segs[0];
    if (found) setActive(found.id.slice(1));
  }

  var spying = false;
  main.addEventListener("scroll", function () {
    hidePop(0);
    if (lockSpy) { bump(); return; }     // едет программный переход — не пересчитываем
    if (spying) return;
    spying = true;
    requestAnimationFrame(function () { spying = false; spy(); });
  });

  /* Переход к параграфу. Для первого параграфа главы окно начинается с
     заголовка главы (если он виден в текущем режиме). */
  function goto(segId, smooth) {
    var el = document.getElementById("s" + segId);
    if (!el) return;
    var target = el;
    var h2 = document.getElementById("h" + N);
    if (segId === firstSeg && h2 && h2.getClientRects().length) target = h2;
    lockOn();
    // на телефоне плавную анимацию гасит любое касание экрана — переходим сразу
    target.scrollIntoView({ behavior: (smooth && !narrow()) ? "smooth" : "auto", block: "start" });
    setActive(segId);
  }

  /* Живое действие читателя отменяет подавление сразу. */
  ["wheel", "touchstart", "mousedown"].forEach(function (ev) {
    main.addEventListener(ev, unlock, { passive: true });
  });
  document.addEventListener("keydown", unlock);

  // --------------------------------------------------------------- события
  /* Одно действие по пункту оглавления — от мыши или от пальца. */
  function activate(el) {
    if (!el.dataset.seg) {                    // строка главы
      if (parseInt(el.dataset.chap, 10) === N) {
        collapsed = !collapsed;               // текущая — свернуть/развернуть
        el.parentNode.classList.toggle("open", !collapsed);
        renderMark();
      } else {
        document.body.classList.remove("menu");
        location.href = el.href;              // другая — её страница
      }
      return;
    }
    var seg = el.dataset.seg;
    var chosen = (seg === curSeg);            // пункт уже выбран — второй тап по нему
    goto(seg, true);
    if (chosen) toggleMark(seg);              // первый тап только переводит, галку не ставит
    // меню закрывается только на переходе; когда тап ставит или снимает
    // галку — остаётся открытым, чтобы читатель видел результат
    else if (narrow()) document.body.classList.remove("menu");
  }

  var HIT = "a[data-seg], a[data-chap]";
  var lastTap = 0;

  toc.addEventListener("click", function (e) {
    if (Date.now() - lastTap < 600) { e.preventDefault(); return; }   // уже сработало по тапу
    var el = e.target.closest(HIT);
    if (!el) return;
    if (!el.dataset.seg && parseInt(el.dataset.chap, 10) !== N) {
      // другая глава — обычная ссылка (в т. ч. Ctrl/средней кнопкой в новую вкладку)
      if (!(e.ctrlKey || e.metaKey || e.shiftKey || e.button)) document.body.classList.remove("menu");
      return;
    }
    e.preventDefault();
    activate(el);
  });

  /* Палец почти всегда чуть смещается, а Chrome от сдвига больше ~10 px
     начинает считать жест прокруткой: шлёт pointercancel и не присылает
     click — на телефоне срабатывал примерно один тап из пяти (замерено на
     устройстве). Поэтому тап определяем сами по касанию: одно касание,
     палец не уехал, область не прокрутилась, нажатие короткое. */
  function onTap(box, scroller, sel, fn) {
    var start = null;
    box.addEventListener("touchstart", function (e) {
      if (e.touches.length !== 1) { start = null; return; }
      var t = e.touches[0];
      start = { x: t.clientX, y: t.clientY, t: Date.now(),
                top: scroller.scrollTop, el: e.target.closest(sel) };
    }, { passive: true });
    box.addEventListener("touchcancel", function () { start = null; });
    box.addEventListener("touchend", function (e) {
      var s = start;
      start = null;
      if (!s || !s.el || e.changedTouches.length !== 1) return;
      var t = e.changedTouches[0];
      if (Math.abs(t.clientX - s.x) > 30 || Math.abs(t.clientY - s.y) > 30) return;  // жест-прокрутка
      if (Math.abs(scroller.scrollTop - s.top) > 10) return;                         // область уехала
      if (Date.now() - s.t > 700) return;                                            // долгое нажатие
      if (e.target.closest(sel) !== s.el) return;                                    // палец ушёл с пункта
      lastTap = Date.now();
      e.preventDefault();                     // гасим синтетический click следом
      fn(s.el, t);
    }, { passive: false });
  }
  onTap(toc, toc, HIT, activate);
  var pn = art.querySelector("nav.pn");
  if (pn) onTap(pn, main, "a", function (a) { location.href = a.href; });

  document.querySelector(".langs").addEventListener("click", function (e) {
    var b = e.target.closest("button[data-lang]");
    if (!b || b.dataset.lang === lang) return;
    localStorage.setItem("gilgulim-lang", b.dataset.lang);
    var keep = curSeg;
    hidePop(0);
    markWord(null);
    setLang(b.dataset.lang);
    if (keep) goto(keep, false);
  });

  document.getElementById("burger").addEventListener("click", function () {
    document.body.classList.toggle("menu");
  });
  document.getElementById("veil").addEventListener("click", function () {
    document.body.classList.remove("menu");
  });
  window.addEventListener("pageshow", function (e) {   // возврат «Назад» из кэша страниц
    if (e.persisted) document.body.classList.remove("menu");
  });
  window.addEventListener("hashchange", function () {  // адрес поменяли, не уходя со страницы
    var h = readHash(), p = parseId(h);
    if (foreign(p)) leaveFor(p);
    else if (p && p[1] && document.getElementById("s" + h)) goto(h, false);
  });

  // ----------------------------------------------------------------- попап
  var popGroup = null, hideTimer = null, lastEvent = null;

  function hidePop(delay) {
    clearTimeout(hideTimer);
    if (delay) {
      hideTimer = setTimeout(function () { pop.classList.remove("on"); popGroup = null; }, delay);
    } else {
      pop.classList.remove("on");
      popGroup = null;
    }
  }

  function groupKey(grp) {
    if (grp.dataset.g === "h") return "h";
    var p = grp.closest("p.seg");
    return p ? p.id.slice(1) + ":" + grp.dataset.g : null;
  }

  function showPop(grp, key, y) {
    clearTimeout(hideTimer);
    var g = GROUPS[key];
    if (!g) return;
    if (popGroup !== key) {
      popGroup = key;
      popHe.innerHTML = wrapSpaced(g[0], "hw");
      popTr.innerHTML = g[1] ? wrapSpaced(g[1], "tw") : '<span class="tw">(транслитерация недоступна)</span>';
    }
    pop.classList.add("on");
    place(grp, y);
  }

  function lineHeight(el) { return parseFloat(getComputedStyle(el).lineHeight); }

  // строка под курсором: фрагмент группы, ближайший к курсору по вертикали, растянутый до высоты строки
  function cursorLine(grp, y) {
    var rs = grp.getClientRects(), r = null, d = Infinity;
    for (var i = 0; i < rs.length; i++) {
      var dd = Math.abs((rs[i].top + rs[i].bottom) / 2 - y);
      if (dd < d) { d = dd; r = rs[i]; }
    }
    if (!r) r = grp.getBoundingClientRect();
    var lh = lineHeight(grp) || r.height, mid = (r.top + r.bottom) / 2;
    return { top: mid - lh / 2, bottom: mid + lh / 2, lh: lh };
  }

  // дальний край соседней строки текста ниже (dir 1) или выше (dir -1) строки курсора:
  // внутри абзаца — через высоту строки, у края абзаца — крайняя строка соседнего блока
  function farEdge(grp, line, dir) {
    var blk = grp.closest("#art > *"), b = blk.getBoundingClientRect();
    var step = dir > 0 ? line.bottom + line.lh : line.top - line.lh;
    if (dir > 0 ? line.bottom + line.lh / 2 < b.bottom : line.top - line.lh / 2 > b.top) return step;
    var sib = blk;
    do sib = dir > 0 ? sib.nextElementSibling : sib.previousElementSibling;
    while (sib && !sib.offsetHeight);
    if (!sib) return step;
    var s = sib.getBoundingClientRect(), slh = lineHeight(sib) || line.lh;
    return dir > 0 ? s.top + slh : s.bottom - slh;
  }

  // попап — через одну строку от строки курсора: мышь спускается (поднимается) на неё,
  // не заходя в попап, и попап сдвигается следом
  function place(grp, y) {
    var mrect = main.getBoundingClientRect();
    var col = art.getBoundingClientRect();
    pop.style.width = Math.min(col.width, mrect.width - 24) + "px";
    pop.style.left = (col.left - mrect.left + main.scrollLeft) + "px";
    var line = cursorLine(grp, y);
    var above = line.top - mrect.top;
    var below = mrect.bottom - line.bottom;
    var top = below >= above ? farEdge(grp, line, 1) : farEdge(grp, line, -1) - pop.offsetHeight;
    pop.style.top = Math.max(0, top - mrect.top + main.scrollTop) + "px";
  }

  function markWord(wEl, key) {
    each(".w.hot", function (e) { e.classList.remove("hot"); }, art);
    each(".hit", function (e) { e.classList.remove("hit"); }, pop);
    var g = wEl && GROUPS[key];
    if (!g) return;
    wEl.classList.add("hot");
    var j = g[2][parseInt(wEl.dataset.i, 10)];
    if (j === undefined || j === null || j < 0) return;
    var hw = popHe.querySelector('.hw[data-i="' + j + '"]');
    var tw = popTr.querySelector('.tw[data-i="' + j + '"]');
    if (hw) hw.classList.add("hit");
    if (tw) tw.classList.add("hit");
  }

  // слова оборачиваются лениво — при первом наведении на группу или касании её
  function wrapGroup(grp) {
    if (grp.dataset.w) return false;
    grp.innerHTML = wrapWords(grp.textContent, "w");
    grp.dataset.w = "1";
    return true;
  }

  // мышиные события, которые браузер досылает после касания, попап не трогают
  function afterTap() { return Date.now() - lastTap < 800; }

  function handle(e) {
    if (afterTap()) return;
    lastEvent = e;
    if (lang !== "ru") return;
    if (!e.shiftKey) {
      if (pop.classList.contains("on")) { hidePop(0); markWord(null); }
      return;
    }
    var el = document.elementFromPoint(e.clientX, e.clientY);
    var grp = el && el.closest ? el.closest(".grp") : null;
    if (!grp) { hidePop(150); markWord(null); return; }
    if (wrapGroup(grp)) el = document.elementFromPoint(e.clientX, e.clientY);
    var w = el && el.closest ? el.closest(".w") : null;
    var key = groupKey(grp);
    showPop(grp, key, e.clientY);
    markWord(w && grp.contains(w) ? w : null, key);
  }

  main.addEventListener("mousemove", handle);
  main.addEventListener("mouseleave", function () {
    if (!afterTap()) { hidePop(150); markWord(null); }
  });

  // палец вместо мыши: касание слова — попап и подсветка, касание другого слова — попап
  // переезжает к нему; касание выделенного слова, попапа или пустого места — закрыть
  var tapWord = null;

  function untap() { hidePop(0); markWord(null); tapWord = null; }

  function nearestWord(grp, x, y) {           // палец попал в пробел между словами
    var best = null, d = Infinity;
    each(".w", function (w) {
      var rs = w.getClientRects();
      for (var i = 0; i < rs.length; i++) {
        var dx = Math.max(rs[i].left - x, 0, x - rs[i].right);
        var dy = Math.max(rs[i].top - y, 0, y - rs[i].bottom);
        if (dx * dx + dy * dy < d) { d = dx * dx + dy * dy; best = w; }
      }
    }, grp);
    return best;
  }

  onTap(main, main, "#main", function (_, t) {
    if (lang !== "ru") return;
    var el = document.elementFromPoint(t.clientX, t.clientY);
    if (el && el.closest("a")) return;       // пред./след. — у них свой обработчик
    var grp = el && el.closest(".grp");
    if (!grp) { untap(); return; }
    if (wrapGroup(grp)) el = document.elementFromPoint(t.clientX, t.clientY);
    var w = (el && el.closest(".w")) || nearestWord(grp, t.clientX, t.clientY);
    if (!w || (w === tapWord && pop.classList.contains("on"))) { untap(); return; }
    var key = groupKey(grp);
    tapWord = w;
    showPop(grp, key, t.clientY);
    markWord(w, key);
  });
  document.addEventListener("keydown", function (e) {
    // Shift нажали, когда курсор уже стоит над текстом
    if (e.key === "Shift" && lastEvent) handle({
      clientX: lastEvent.clientX, clientY: lastEvent.clientY, shiftKey: true
    });
  });
  document.addEventListener("keyup", function (e) {
    if (e.key === "Shift") { hidePop(0); markWord(null); }
  });
  window.addEventListener("blur", function () { hidePop(0); markWord(null); });

  // ------------------------------------------------------------------ старт
  setLang(lang);
  if (markSeg && !knownSeg(parseId(markSeg))) {
    markSeg = null;                          // отметка на исчезнувшем параграфе
    localStorage.removeItem("gilgulim-mark");
  }
  if (hp && hp[1] && document.getElementById("s" + hash)) goto(hash, false);
  else if (firstSeg) setActive(firstSeg);   // начало главы: вверху заголовок, активен первый §
  renderMark();
  root.classList.remove("wait");            // всё на месте — показываем
})();
