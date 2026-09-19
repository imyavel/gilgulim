# -*- coding: utf-8 -*-
"""Слияние порций этапа parts/p<этап>*.md в translation.md с унификацией терминов.

    python merge_parts.py 6            сухой прогон (проверки + отчёт)
    python merge_parts.py 6 --write    дописать в translation.md

Порции этапа N: parts/p<N>a01.md, p<N>a02.md, …, p<N>b01.md, … (буква = субагент,
порядок букв = порядок текста в книге). Запускать из translation/ (репо gilgulim)."""
import glob
import io
import re
import sys

ROOT = ""  # пути относительно translation/
# этап -> (первый сегмент, последний сегмент) включительно
STAGES = {
    6: ((36, 1), (36, 122)),
    7: ((37, 1), (38, 74)),
    8: ((38, 75), (38, 126)),
    9: ((38, 127), (38, 184)),
    10: ((39, 1), (40, 26)),
}
# раздел 3 глоссария: термин -> полная форма при первом вводе
TERMS = {
    'З"А': "Зеир Анпин", 'А"А': "Арих Анпин", 'АВ"И': "Абба ве-Има",
    'ЗО"Н': "Зеир Анпин и Нуква", 'АБЕ"А': "Ацилут, Брия, Ецира, Асия",
    'БЕ"А': "Брия, Ецира, Асия", 'ХАГА"Т': "Хесед, Гвура, Тиферет",
    'НЕЃ"И': "Нецах, Ѓод, Есод", 'ХУ"Б': "Хохма и Бина", 'ХУ"Г': "Хесед и Гвура",
    'НаРа"Н': "Нефеш, Руах, Нешама", 'НаРаНХа"Й': "Нефеш, Руах, Нешама, Хая, Ехида",
    'НаРаН"Х': "Нефеш, Руах, Нешама, Хая", 'МА"Н': "маим нуквин", 'МА"Д': "маим духрин",
    'А"В': "гематрия 72 имени АВА\"Я", 'СА"Г': "гематрия 63", 'М"А': "гематрия 45",
    'БО"Н': "гематрия 52", 'АВА"Я': "четырёхбуквенное Имя", 'АВАЙо"т': "",
    'МЦП"Ц': "имя-атбаш от АВА\"Я", 'АВГИТ"Ц': "первая шестёрка 42-буквенного имени",
    'ПаРДе"С': "пшат, ремез, драш, сод", 'атба"ш': "шифр замены букв",
}

stage = int(sys.argv[1])
(h0, s0), (h1, s1) = STAGES[stage]
order = sorted(glob.glob(ROOT + "parts/p%d[a-z][0-9][0-9].md" % stage))
print("файлы:", [f.split("/")[-1].split("\\")[-1] for f in order])

text = ""
for fn in order:
    t = io.open(fn, encoding="utf-8").read()
    if t.startswith("\ufeff"):
        t = t[1:]
    text += t.strip("\n") + "\n\n"

tr = io.open(ROOT + "translation.md", encoding="utf-8").read()

# 1. Унификация ѓ: НЕХ"И/Ход -> НЕЃ"И/Ѓод (практика хакдамот 1–18)
before = text
text = text.replace('НЕХ"И', 'НЕЃ"И')
text = re.sub(r"\bХод(а|у|ом|е)?\b", lambda m: "Ѓод" + (m.group(1) or ""), text)
print("унификация ѓ: изменено символов", sum(1 for a, b in zip(before, text) if a != b) + abs(len(before) - len(text)))

# 2. Полная форма — только при первом появлении термина в порядке книги
for term, full in TERMS.items():
    pat = "%s (%s)" % (term, full) if full else None
    introduced = term in tr
    n = text.count(pat) if pat else 0
    if pat and n:
        if introduced:
            text = text.replace(pat, term)
            print("%s: введён раньше, снято полных форм %d" % (term, n))
        elif n > 1:
            first = text.find(pat) + len(pat)
            text = text[:first] + text[first:].replace(pat, term)
            print("%s: вводится в этом этапе, полных форм было %d, оставлена первая" % (term, n))
        else:
            print("%s: вводится в этом этапе" % term)
    other = [m.start() for m in re.finditer(r"(?<![А-Яа-яЁёЃѓ])" + re.escape(term) + r" \(", text)]
    if pat:
        other = [i for i in other if not text.startswith(pat, i)]
    if other:
        print("   ? %s: скобки не по канону глоссария %d: %s" % (term, len(other),
              [text[i:i + 60].replace("\n", " ") for i in other[:3]]))

# 3. Проверки
src = io.open(ROOT + "source/gilgulim_he.md", encoding="utf-8").read()
key = lambda w: tuple(int(x) for x in w.split("."))
want = [w for w in re.findall(r"^\[(\d+\.\d+)\]", src, re.M) if (h0, s0) <= key(w) <= (h1, s1)]
got = re.findall(r"^\*\*\[(\d+\.\d+)\]\*\*", text, re.M)
heads = re.findall(r"^## Хакдама (\d+)\s*$", text, re.M)
want_heads = [str(h) for h in range(h0, h1 + 1) if (h, 1) >= (h0, s0)]
assert want == got, (len(want), len(got), [x for x in want if x not in got], [x for x in got if x not in want])
assert heads == want_heads, (heads, want_heads)
stray = [ln[:60] for ln in text.split("\n") if ln.strip() and not ln.startswith("**[") and not ln.startswith("## ")]
print("сегментов:", len(got), "| глав-заголовков:", heads, "| строк вне сегментов:", len(stray))
for s in stray[:10]:
    print("   ?", s)
todos = re.findall(r"^\*\*\[(\d+\.\d+)\]\*\*.*?<!--", text, re.M)
print("TODO:", len(re.findall(r"<!--", text)), "в сегментах", todos)
print("слов RU:", len(text.split()))

# новый текст должен продолжать translation.md без разрыва
prev = [w for w in re.findall(r"^\[(\d+\.\d+)\]", src, re.M) if key(w) < (h0, s0)][-1]
last = re.findall(r"^\*\*\[(\d+\.\d+)\]\*\*", tr, re.M)[-1]
assert last == prev, ("в translation.md последняя метка", last, "ожидалась", prev)

if "--write" in sys.argv:
    sep = "" if tr.endswith("\n\n") else ("\n" if tr.endswith("\n") else "\n\n")
    with io.open(ROOT + "translation.md", "a", encoding="utf-8", newline="") as f:
        f.write(sep + text)
    tr2 = io.open(ROOT + "translation.md", encoding="utf-8").read()
    print("записано; последняя метка:", re.findall(r"^\*\*\[(\d+\.\d+)\]\*\*", tr2, re.M)[-1],
          "| всего сегментов:", len(re.findall(r"^\*\*\[", tr2, re.M)))
else:
    print("СУХОЙ ПРОГОН OK (для записи: --write)")
