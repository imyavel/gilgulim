# -*- coding: utf-8 -*-
"""Выравнивание перевода с оригиналом через headless Claude (`claude -p`).

Для каждого сегмента получает разбиение на группы (ru/he/tr/map), проверяет
целостность и кладёт результат в кэш data/align/<N.s>.json. Уже закэшированные
сегменты не пересчитываются — при дозагрузке новых глав повторный прогон дешёвый.

Запуск из корня репо:  python tools/align.py [--only 1.2,1.3] [--limit N] [--jobs 4]
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data", "align")
COST_LOG = os.path.join(ROOT, "data", "align_cost.jsonl")
ERR_MD = os.path.join(ROOT, "data", "align_errors.md")
PROMPT_TPL = os.path.join(ROOT, "tools", "align_prompt.md")

SYSTEM_PROMPT = (
    u"Ты — точный инструмент выравнивания текстов иврит-русский. "
    u"Отвечаешь только валидным JSON по заданной схеме, без пояснений и markdown-ограды."
)

BATCH_CHARS = 6000   # суммарно ru+he на батч
BATCH_SEGS = 5       # не больше стольких сегментов в батче
MAX_ATTEMPTS = 3

_print_lock = threading.Lock()
_cost_lock = threading.Lock()


def log(msg):
    with _print_lock:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()


# ---------------------------------------------------------------- токенизация
def tokens_ru(text):
    return [(m.group(0), m.start()) for m in sources.RU_WORD.finditer(text)]


def tokens_he(text):
    return [(m.group(0), m.start()) for m in re.finditer(r"\S+", text)]


def snap(seg_text, group_texts, tok_fn, word_fn):
    """Режет seg_text на точные срезы по границам групп, предложенным моделью.

    Возвращает (срезы, None) или (None, описание ошибки). Тексты групп берутся
    ИЗ ИСТОЧНИКА, поэтому целостность гарантирована конструктивно; ответ модели
    нужен только чтобы найти границы и убедиться, что слова те же самые.
    """
    toks = tok_fn(seg_text)
    gwords = [word_fn(g) for g in group_texts]
    total = sum(len(w) for w in gwords)
    if total != len(toks):
        return None, u"слов в группах %d, в исходном сегменте %d" % (total, len(toks))
    cum = 0
    starts = []
    for gi, ws in enumerate(gwords):
        if not ws:
            return None, u"группа %d пустая" % gi
        starts.append(0 if gi == 0 else toks[cum][1])
        for k, w in enumerate(ws):
            src = toks[cum + k][0]
            if src != w:
                return None, (u"группа %d, слово %d: в ответе %s, в источнике %s "
                              u"(текст менять нельзя)" % (gi, k, w, src))
        cum += len(ws)
    starts.append(len(seg_text))
    out = []
    for gi in range(len(gwords)):
        piece = seg_text[starts[gi]:starts[gi + 1]].strip()
        if not piece:
            return None, u"группа %d после нарезки пустая" % gi
        out.append(piece)
    if sources.norm_ws(" ".join(out)) != sources.norm_ws(seg_text):
        return None, u"склейка групп не совпала с сегментом"
    return out, None


def validate(sid, ru_text, he_text, groups):
    """Проверяет ответ модели, возвращает (готовые группы, None) либо (None, ошибка)."""
    if not isinstance(groups, list) or not groups:
        return None, u"groups пуст или не список"
    for gi, g in enumerate(groups):
        if not isinstance(g, dict):
            return None, u"группа %d не объект" % gi
        for key in ("ru", "he", "tr", "map"):
            if key not in g:
                return None, u"группа %d: нет поля %s" % (gi, key)
        if not isinstance(g["map"], list):
            return None, u"группа %d: map не список" % gi

    ru_cut, err = snap(ru_text, [g["ru"] for g in groups], tokens_ru, sources.ru_words)
    if err:
        return None, u"RU: " + err
    he_cut, err = snap(he_text, [g["he"] for g in groups], tokens_he, sources.he_words)
    if err:
        return None, u"HE: " + err

    out = []
    for gi, g in enumerate(groups):
        ru, he = ru_cut[gi], he_cut[gi]
        hw = sources.he_words(he)
        tw = sources.he_words(g["tr"])
        if len(tw) != len(hw):
            return None, (u"группа %d: слов в tr %d, в he %d (tr: %s | he: %s)"
                          % (gi, len(tw), len(hw), " ".join(tw[:6]), " ".join(hw[:6])))
        rw = sources.ru_words(ru)
        mp = g["map"]
        if len(mp) != len(rw):
            return None, (u"группа %d: длина map %d, слов в ru %d (ru начинается: %s)"
                          % (gi, len(mp), len(rw), " ".join(rw[:8])))
        norm = []
        for v in mp:
            if not isinstance(v, int) or isinstance(v, bool) or v < -1 or v >= len(hw):
                return None, (u"группа %d: значение map %s вне диапазона -1..%d"
                              % (gi, v, len(hw) - 1))
            norm.append(v)
        out.append({"he": he, "tr": " ".join(tw), "ru": ru, "map": norm})
    return out, None


# ------------------------------------------------------------------- вызов LLM
def build_prompt(batch, note=None):
    tpl = io.open(PROMPT_TPL, encoding="utf-8").read()
    parts = [tpl]
    if note:
        parts.append(u"\n### ВНИМАНИЕ: предыдущая попытка отклонена\n%s\nИсправь именно это.\n" % note)
    for sid, ru, he in batch:
        parts.append(u"\n--- Сегмент %s ---\nRU: %s\n\nHE: %s\n" % (sid, ru, he))
    parts.append(u"\nВерни JSON по схеме для сегментов: %s" % ", ".join(b[0] for b in batch))
    return "".join(parts)


def claude_exe():
    """На Windows npm-обёртка называется claude.cmd — shutil.which это учитывает."""
    import shutil
    for name in ("claude.cmd", "claude.exe", "claude"):
        p = shutil.which(name)
        if p:
            return p
    raise RuntimeError("не найден исполняемый файл claude")


def call_claude(prompt, timeout=2400):
    cmd = [claude_exe(), "-p", "--model", "opus", "--output-format", "json",
           "--strict-mcp-config", "--system-prompt", SYSTEM_PROMPT]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, input=prompt.encode("utf-8"), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout, env=env)
    if p.returncode != 0:
        raise RuntimeError("claude exit %d: %s"
                           % (p.returncode, p.stderr.decode("utf-8", "replace")[:400]))
    raw = json.loads(p.stdout.decode("utf-8", "replace"))
    cost = raw.get("total_cost_usd", 0.0) or 0.0
    with _cost_lock:
        with io.open(COST_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "cost": cost}) + "\n")
    return raw.get("result", ""), cost


JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        m = JSON_RE.search(text)
        if not m:
            raise
        return json.loads(m.group(0))


def cache_path(sid):
    return os.path.join(CACHE_DIR, sid + ".json")


def process_batch(batch, stats):
    """Обрабатывает батч; несошедшиеся сегменты добивает поодиночке."""
    pending = list(batch)
    notes = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if not pending:
            return
        groups_batch = [pending] if attempt == 1 else [[s] for s in pending]
        still = []
        for grp in groups_batch:
            note = "\n".join(notes.get(s[0], "") for s in grp).strip() or None
            try:
                text, cost = call_claude(build_prompt(grp, note))
                with _cost_lock:
                    stats["cost"] += cost
                    stats["calls"] += 1
                data = extract_json(text)
                got = {}
                for s in data.get("segments", []):
                    got[s.get("id")] = s.get("groups")
            except Exception as e:
                for s in grp:
                    notes[s[0]] = u"Ответ не разобран: %s" % str(e)[:300]
                    still.append(s)
                log(u"  [%s] попытка %d: %s" % (",".join(s[0] for s in grp), attempt, str(e)[:150]))
                continue
            for sid, ru, he in grp:
                if sid not in got or not got[sid]:
                    notes[sid] = u"Сегмент %s отсутствовал в ответе." % sid
                    still.append((sid, ru, he))
                    continue
                ok, err = validate(sid, ru, he, got[sid])
                if err:
                    notes[sid] = u"Сегмент %s: %s" % (sid, err)
                    still.append((sid, ru, he))
                    log(u"  [%s] попытка %d отклонена: %s" % (sid, attempt, err[:170]))
                    continue
                with io.open(cache_path(sid), "w", encoding="utf-8") as f:
                    json.dump({"id": sid, "groups": ok}, f, ensure_ascii=False, indent=1)
                with _cost_lock:
                    stats["done"] += 1
                    n_done = stats["done"]
                log(u"  [%s] ok, групп %d (готово %d)" % (sid, len(ok), n_done))
        pending = still
    for sid, ru, he in pending:
        with _cost_lock:
            stats["failed"].append((sid, notes.get(sid, u"неизвестно")))
        log(u"  [%s] ПРОВАЛ после %d попыток" % (sid, MAX_ATTEMPTS))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="список id сегментов через запятую")
    ap.add_argument("--limit", type=int, help="обработать не больше N сегментов")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="пересчитать даже закэшированные")
    args = ap.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)

    ps, problems = sources.pairs()
    for p in problems:
        log("! " + p)
    only = set(args.only.split(",")) if args.only else None
    todo = []
    for n, sid, ru, he in ps:
        if only and sid not in only:
            continue
        if not args.force and os.path.exists(cache_path(sid)):
            continue
        todo.append((sid, ru, he))
    if args.limit:
        todo = todo[:args.limit]

    log(u"сегментов всего %d, к обработке %d" % (len(ps), len(todo)))
    if not todo:
        return

    batches, cur, cur_chars = [], [], 0
    for item in todo:
        c = len(item[1]) + len(item[2])
        if cur and (len(cur) >= BATCH_SEGS or cur_chars + c > BATCH_CHARS):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(item)
        cur_chars += c
    if cur:
        batches.append(cur)
    log(u"батчей: %d, потоков: %d" % (len(batches), args.jobs))

    stats = {"cost": 0.0, "calls": 0, "done": 0, "failed": []}
    t0 = time.time()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        list(ex.map(lambda b: process_batch(b, stats), batches))

    dt = time.time() - t0
    log(u"\nготово: %d, провалов: %d, вызовов LLM: %d, стоимость $%.2f, время %.1f мин"
        % (stats["done"], len(stats["failed"]), stats["calls"], stats["cost"], dt / 60))
    if stats["failed"]:
        with io.open(ERR_MD, "a", encoding="utf-8") as f:
            f.write(u"\n## Прогон %s\n\n" % time.strftime("%Y-%m-%d %H:%M"))
            for sid, why in stats["failed"]:
                f.write(u"- **%s** — %s\n" % (sid, why))
        log(u"список провалов дописан в %s" % ERR_MD)


if __name__ == "__main__":
    main()
