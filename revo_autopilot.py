#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РЕВО-ПАСПОРТ СТРАНИЦЫ · канон ORNAMENTAL MYTHO-REALISM.
Ренессансная точность + гравюрный штрих + орнамент Сецессиона + плоскость укиё-э +
символистский миф. Фронтальный план — орнамент и решётка; средний — икона-медальон с
архетипической фигурой (ЧЕЛОВЕК=МИФ, не индивид); фон — мифическое пространство.
Куётся СТРОГО из фактов страницы: файлы, папки, коммиты, лексикон README, топики.
Один исходник: песочница правит CFG атрибутом, автопилот в репо несёт свой CFG.
Только stdlib — работает в GitHub Actions."""
import hashlib, json, os, re, subprocess

try:
    CFG = json.loads(r'''{"name": "voice-atlas-llm", "num": 59, "school": "АРФА ГОЛОСОВ", "desc": "Атлас-LLM: модель-эксперт по клонированию голоса (дизентанглмент, TTS/VC/SVC/SVS) — LoRA-обучение на корпусе атласа 2026, RAG, гейты качества", "topics": ["atlas", "llm", "lora", "python", "speech", "tts", "voice-cloning"], "releases": 8, "palette": {"bg": "#EFE6CF", "bg2": "#F6EFDC", "ink": "#241C10", "gold": "#9A7B23", "gold2": "#C9A227", "dim": "#6E6249", "accent": "#C43B27"}}''')
except Exception:
    CFG = {"name": "REVO", "num": 0, "school": "", "desc": "", "topics": [], "releases": 0,
           "palette": dict(bg="#EFE6CF", bg2="#F6EFDC", ink="#241C10", gold="#9A7B23",
                           gold2="#C9A227", dim="#6E6249", accent="#D5281B")}

MONO = "'Cascadia Mono', ui-monospace, Consolas, monospace"
SERIF = "Georgia, 'Times New Roman', serif"
CANON = "ORNAMENTAL MYTHO-REALISM"
STOP = {"полимат", "полимата", "кузня", "кузни", "revo", "reve", "раунд", "round", "дом",
        "дома", "доме", "хозяин", "хозяина", "github", "gitlab", "https", "http", "com",
        "org", "net", "www", "readme", "license", "репозиторий", "репо", "страница",
        "страницы", "which", "their", "there", "about", "сайте", "проекта", "проект"}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def wrap2(text, width=94):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
        if len(lines) == 2:
            break
    if cur and len(lines) < 2:
        lines.append(cur)
    return lines


def lexicon(text, n=4):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[|*_`>#\[\]()!-]", " ", text)
    freq = {}
    for w in re.findall(r"[а-яёa-z][а-яёa-z-]{4,}", text.lower()):
        if w in STOP or len(w) > 18:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [w.upper() for w, _ in top]


def ext_of(path):
    base = path.rsplit("/", 1)[-1]
    if base.startswith("."):
        return ".git-файл"
    m = re.search(r"\.([A-Za-z0-9]+)$", base)
    return ("." + m.group(1).lower()) if m else "без-расш."


def facts_from_paths(paths, n_commits, last_date, size_kb, readme_text, topics, desc, releases):
    files = [p for p in paths if "/.git/" not in p and not p.startswith(".git/")]
    dirs = {p.rsplit("/", 1)[0] for p in files if "/" in p}
    exts = {}
    for p in files:
        exts[ext_of(p)] = exts.get(ext_of(p), 0) + 1
    top = sorted(exts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    sig = hashlib.sha256(("|".join(sorted(files)) + desc).encode()).hexdigest()[:8]
    return {"exts": top, "n_files": len(files), "n_dirs": len(dirs), "n_commits": n_commits,
            "last_date": last_date, "size_kb": size_kb,
            "lexicon": lexicon(readme_text or ""), "topics": topics[:4],
            "hash8": sig, "releases": releases}


def hatch(sid, color, w=0.5, gap=4.2, ang=45):
    return (f'<pattern id="{sid}" width="{gap}" height="{gap}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate({ang})"><rect width="{gap}" height="{gap}" fill="none"/>'
            f'<line x1="0" y1="0" x2="0" y2="{gap}" stroke="{color}" stroke-width="{w}"/></pattern>')


def lattice(pal, W, H, step=64, ink=None, node=None):
    """Орнаментальная геометрическая решётка Сецессиона: тонкая сетка + узлы-квадраты."""
    ink = ink or pal["gold"]; node = node or pal["gold2"]
    out = [f'<g stroke="{ink}" stroke-width="0.45" opacity="0.30">']
    for x in range(step, W, step):
        out.append(f'<line x1="{x}" y1="14" x2="{x}" y2="{H-14}"/>')
    for y in range(step, H, step):
        out.append(f'<line x1="14" y1="{y}" x2="{W-14}" y2="{y}"/>')
    out.append('</g><g fill="none" stroke="%s" stroke-width="0.8" opacity="0.5">' % node)
    for x in range(step, W, step):
        for y in range(step, H, step):
            if (x // step + y // step) % 2 == 0:
                out.append(f'<rect x="{x-3}" y="{y-3}" width="6" height="6"/>')
            else:
                out.append(f'<circle cx="{x}" cy="{y}" r="2.6"/>')
    out.append('</g>')
    return "".join(out)


def meander(pal, x0, y0, x1, cell=16, sw=1.4):
    """Греческий ключ (меандр) — лента-орнамент от x0 до x1 на высоте y0."""
    c, col = cell, pal["gold2"]
    out = [f'<g fill="none" stroke="{col}" stroke-width="{sw}" opacity="0.85">']
    n = int((x1 - x0) // (c * 3))
    for i in range(n):
        x = x0 + i * c * 3
        out.append(f'<path d="M {x} {y0} L {x} {y0-c} L {x+c} {y0-c} L {x+c} {y0-c/2} '
                   f'L {x+c/2} {y0-c/2} L {x+c/2} {y0-c*0.75}"/>')
        out.append(f'<line x1="{x+c*1.2}" y1="{y0}" x2="{x+c*2.8}" y2="{y0}"/>')
    out.append('</g>')
    return "".join(out)


def myth_figure(pal, cx, cy, r):
    """Икона-медальон: архетипическая фигура человека (не индивид — миф).
    Голова-профиль в гравюрном штрихе, нимб-решётка, плащ, плоскость укиё-э."""
    acc, gold, gold2, ink = pal["accent"], pal["gold"], pal["gold2"], pal["ink"]
    s = [f'<g transform="translate({cx},{cy})">']
    s.append(f'<circle r="{r}" fill="none" stroke="{gold}" stroke-width="1.6"/>')
    s.append(f'<circle r="{r-7}" fill="none" stroke="{gold2}" stroke-width="0.7" opacity="0.8"/>')
    s.append(f'<circle r="{r-2}" fill="url(#hatchm)" opacity="0.4"/>')
    s.append(f'<g stroke="{gold2}" stroke-width="0.7" opacity="0.9">')
    for a in range(0, 360, 30):
        s.append(f'<line x1="0" y1="-{r-4}" x2="0" y2="-{r-11}" transform="rotate({a})"/>')
    s.append('</g>')
    # нимб-решётка
    s.append(f'<circle cy="-{r*0.56:.0f}" r="{r*0.21:.0f}" fill="none" stroke="{gold}" stroke-width="1.1"/>')
    s.append(f'<circle cy="-{r*0.56:.0f}" r="{r*0.27:.0f}" fill="none" stroke="{gold2}" stroke-width="0.5" opacity="0.7"/>')
    # профиль-архетип: гравюрный контур, пропорции черепа (затылок-лоб-нос-губы-подбородок-шея)
    hr = r*0.26
    hx, hy = -r*0.04, -r*0.54
    s.append(f'<path d="M {hx-r*0.02:.1f} {hy-hr*1.00:.1f} '
             f'C {hx-hr*0.75:.1f} {hy-hr*0.95:.1f} {hx-hr*0.95:.1f} {hy-hr*0.45:.1f} {hx-hr*0.78:.1f} {hy-hr*0.00:.1f} '
             f'L {hx-hr*0.62:.1f} {hy+hr*0.35:.1f} L {hx-hr*0.70:.1f} {hy+hr*0.95:.1f} '
             f'L {hx+hr*0.30:.1f} {hy+hr*0.95:.1f} L {hx+hr*0.28:.1f} {hy+hr*0.45:.1f} '
             f'C {hx+hr*0.42:.1f} {hy+hr*0.55:.1f} {hx+hr*0.52:.1f} {hy+hr*0.48:.1f} {hx+hr*0.55:.1f} {hy+hr*0.35:.1f} '
             f'L {hx+hr*0.42:.1f} {hy+hr*0.22:.1f} L {hx+hr*0.52:.1f} {hy+hr*0.12:.1f} L {hx+hr*0.40:.1f} {hy+hr*0.02:.1f} '
             f'L {hx+hr*0.62:.1f} {hy-hr*0.10:.1f} L {hx+hr*0.38:.1f} {hy-hr*0.22:.1f} '
             f'C {hx+hr*0.52:.1f} {hy-hr*0.32:.1f} {hx+hr*0.50:.1f} {hy-hr*0.45:.1f} {hx+hr*0.35:.1f} {hy-hr*0.50:.1f} '
             f'C {hx+hr*0.30:.1f} {hy-hr*0.72:.1f} {hx+hr*0.15:.1f} {hy-hr*0.98:.1f} {hx-r*0.02:.1f} {hy-hr*1.00:.1f} Z" '
             f'fill="{ink}" stroke="{gold2}" stroke-width="1.0"/>')
    # золотая прядь-дуга в черепе + бровь
    s.append(f'<g fill="none" stroke="{gold2}" stroke-width="0.8" opacity="0.95">'
             f'<path d="M {hx-hr*0.55:.1f} {hy-hr*0.55:.1f} C {hx-hr*0.35:.1f} {hy-hr*0.90:.1f} {hx+hr*0.05:.1f} {hy-hr*0.95:.1f} {hx+hr*0.25:.1f} {hy-hr*0.70:.1f}"/>'
             f'<path d="M {hx+hr*0.12:.1f} {hy-hr*0.38:.1f} L {hx+hr*0.34:.1f} {hy-hr*0.36:.1f}"/></g>')
    # плащ-треугольник (плоская плоскость укиё-э) с подолом
    s.append(f'<path d="M {-r*0.58:.1f} {r*0.90:.1f} L 0 {-r*0.10:.1f} L {r*0.58:.1f} {r*0.90:.1f} '
             f'L {r*0.44:.1f} {r*0.90:.1f} L 0 {r*0.14:.1f} L {-r*0.44:.1f} {r*0.90:.1f} Z" '
             f'fill="{acc}" opacity="0.92" stroke="{gold}" stroke-width="1.0"/>')
    s.append(f'<path d="M {-r*0.34:.1f} {r*0.88:.1f} L 0 {r*0.20:.1f} L {r*0.34:.1f} {r*0.88:.1f}" '
             f'fill="url(#hatchm)" opacity="0.5" stroke="none"/>')
    s.append(f'<path d="M {-r*0.58:.1f} {r*0.90:.1f} L {r*0.58:.1f} {r*0.90:.1f}" fill="none" stroke="{gold2}" stroke-width="0.8"/>')
    # руки-линии (гравюра)
    s.append(f'<path d="M {-r*0.52:.1f} {r*0.24:.1f} L {-r*0.20:.1f} {r*0.38:.1f}" fill="none" stroke="{ink}" stroke-width="1.1" opacity="0.85"/>')
    s.append(f'<path d="M {r*0.52:.1f} {r*0.24:.1f} L {r*0.20:.1f} {r*0.38:.1f}" fill="none" stroke="{ink}" stroke-width="1.1" opacity="0.85"/>')
    s.append('</g>')
    return "".join(s)


def build_svg(facts):
    pal = CFG["palette"]
    bg, bg2 = pal["bg"], pal.get("bg2", pal["bg"])
    ink, gold, gold2, dim = pal["ink"], pal["gold"], pal["gold2"], pal["dim"]
    acc = pal.get("accent", "#D5281B")
    W, H = 1280, 400
    num, name, school = CFG["num"], CFG["name"], CFG["school"]
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">']
    e.append(f'<defs><radialGradient id="rp{num}" cx="0.5" cy="0.42" r="1.1">'
             f'<stop offset="0" stop-color="{bg2}"/><stop offset="1" stop-color="{bg}"/></radialGradient>'
             + hatch("hatchm", gold2, 0.5, 4.2, 45) + hatch("hatchv", ink, 0.5, 5.5, -45) + '</defs>')
    e.append(f'<rect width="{W}" height="{H}" fill="{bg}"/>')
    e.append(f'<rect width="{W}" height="{H}" fill="url(#rp{num})" opacity="0.94"/>')
    # фон: мифическое пространство — дальняя арка и горы-знаки (плоскость укиё-э)
    e.append(f'<path d="M 900 {H-44} Q 1000 {130} 1180 {H-44} Z" fill="{gold}" opacity="0.14"/>')
    e.append(f'<path d="M 960 {H-44} Q 1060 {190} 1236 {H-44} Z" fill="{ink}" opacity="0.18"/>')
    e.append(f'<circle cx="1120" cy="120" r="34" fill="{acc}" opacity="0.30"/>')
    e.append(f'<circle cx="1120" cy="120" r="46" fill="none" stroke="{gold2}" stroke-width="0.7" opacity="0.7"/>')
    e.append(lattice(pal, W, H))
    # кайма: двойная + меандр
    e.append(f'<rect x="10" y="10" width="{W-20}" height="{H-20}" fill="none" stroke="{gold}" stroke-width="1.6"/>')
    e.append(f'<rect x="17" y="17" width="{W-34}" height="{H-34}" fill="none" stroke="{gold2}" stroke-width="0.6" opacity="0.75"/>')
    e.append(meander(pal, 26, 388, W-26))
    e.append(meander(pal, 26, 12, W-26, cell=12, sw=1.1))
    # угловые розетки
    for (x, y, sgn) in ((17, 17, 1), (W-17, 17, -1), (17, H-17, 1), (W-17, H-17, -1)):
        e.append(f'<g transform="translate({x},{y}) scale({sgn},1)"><path d="M 0 0 L 26 0 L 26 5 L 5 5 L 5 26 L 0 26 Z" '
                 f'fill="{acc}" opacity="0.9"/><circle cx="13" cy="13" r="3.2" fill="{gold2}"/></g>')
    # шапка канона
    e.append(f'<text x="34" y="64" font-family="{MONO}" font-size="11" fill="{gold}" letter-spacing="3.4">{CANON} · РЕВО-ПАСПОРТ СТРАНИЦЫ · {esc(school.upper())}</text>')
    ticks = "".join(f'<line x1="0" y1="-17" x2="0" y2="-14" transform="rotate({a})"/>' for a in range(0, 360, 30))
    e.append(f'<g transform="translate({W-58},60)"><circle r="15" fill="none" stroke="{acc}" stroke-width="1.3"/>'
             f'<circle r="11" fill="none" stroke="{acc}" stroke-width="0.55" opacity="0.6"/>'
             f'<text y="4" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{gold2}">{num}</text>'
             f'<g stroke="{acc}" stroke-width="0.7">{ticks}</g></g>')
    nm = name.upper()
    fs = min(48, max(24, 560 / (len(nm) * 0.78)))
    e.append(f'<text x="34" y="{146:.0f}" font-family="{SERIF}" font-size="{fs:.1f}" fill="{ink}" letter-spacing="4">{esc(nm)}</text>')
    e.append(f'<line x1="34" y1="172" x2="700" y2="172" stroke="{gold}" stroke-width="1" opacity="0.85"/>')
    lines = wrap2(facts.get("desc") or CFG.get("desc") or "", 90)
    for i, ln in enumerate([l for l in lines if l][:2]):
        e.append(f'<text x="34" y="{200+i*21}" font-family="{MONO}" font-size="12.5" fill="{dim}" letter-spacing="0.3">{esc(ln)}</text>')
    # лексикон в рамках-лапках
    lx = facts.get("lexicon") or []
    if lx:
        e.append(f'<text x="34" y="258" font-family="{MONO}" font-size="10.5" fill="{gold}" letter-spacing="2.5">ЛЕКСИКОН ЭТОЙ СТРАНИЦЫ (из README)</text>')
        cx = 34
        for w in lx[:4]:
            cw = int(len(w) * 9.2 + 26)
            e.append(f'<path d="M {cx} 272 L {cx+10} 266 L {cx+cw-10} 266 L {cx+cw} 272 L {cx+cw} 296 L {cx+cw-10} 302 L {cx+10} 302 L {cx} 296 Z" '
                     f'fill="none" stroke="{gold2}" stroke-width="0.9"/>'
                     f'<text x="{cx+cw/2:.0f}" y="289" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{ink}" letter-spacing="1">{esc(w)}</text>')
            cx += cw + 10
    # строение страницы: гравюрные штрих-полосы
    x0 = 810
    e.append(f'<text x="{x0}" y="76" font-family="{MONO}" font-size="10.5" fill="{gold}" letter-spacing="2.5">СТРОЕНИЕ СТРАНИЦЫ · ФАЙЛЫ ПО ТИПАМ</text>')
    exts = facts.get("exts") or []
    mx = max((c for _, c in exts), default=1)
    for i, (x, c) in enumerate(exts):
        y = 98 + i * 21
        bw = int(8 + 210 * (c / mx) ** 0.62)
        e.append(f'<text x="{x0}" y="{y+9}" font-family="{MONO}" font-size="10.5" fill="{ink}" letter-spacing="0.5">{esc(x)}</text>')
        e.append(f'<rect x="{x0+66}" y="{y}" width="{bw}" height="12" fill="url(#hatchv)" opacity="0.9"/>')
        e.append(f'<rect x="{x0+66}" y="{y}" width="{bw}" height="12" fill="{gold}" opacity="0.28"/>')
        e.append(f'<rect x="{x0+66}" y="{y}" width="{bw}" height="12" fill="none" stroke="{gold2}" stroke-width="0.5"/>')
        e.append(f'<text x="{x0+66+bw+8:.0f}" y="{y+9}" font-family="{MONO}" font-size="10.5" fill="{dim}">{c}</text>')
    # медальон-человек=миф
    e.append(myth_figure(pal, 738, 234, 100))
    # три числа в кольцах-розетках (выше чипов топиков, без перекрытия)
    trio = [("ФАЙЛОВ", facts.get("n_files")), ("ПАПОК", facts.get("n_dirs")), ("КОММИТОВ", facts.get("n_commits"))]
    for i, (lab, v) in enumerate(trio):
        cx = x0 + 45 + i * 145
        e.append(f'<g transform="translate({cx},266)"><circle r="25" fill="none" stroke="{acc}" stroke-width="1.2"/>'
                 f'<circle r="21" fill="none" stroke="{gold2}" stroke-width="0.5" opacity="0.8"/>'
                 f'<text y="4.5" text-anchor="middle" font-family="{MONO}" font-size="{10.5 if v and v>9999 else 12}" fill="{gold2}">{v}</text>'
                 f'<text y="40" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="{dim}" letter-spacing="2">{lab}</text></g>')
    tp = facts.get("topics") or []
    tx = x0
    for t in tp:
        tw = int(len(t) * 6.6 + 18)
        if tx + tw > W-44:
            break
        e.append(f'<rect x="{tx}" y="326" rx="0" width="{tw}" height="20" fill="{acc}"/>'
                 f'<text x="{tx+tw/2:.0f}" y="340" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="#F5EFE2" letter-spacing="0.8">{esc(t)}</text>')
        tx += tw + 10
    e.append(f'<text x="34" y="338" font-family="{SERIF}" font-size="15" fill="{acc}" letter-spacing="2">ЧЕЛОВЕК=МИФ · МИФ=ЧЕЛОВЕК</text>')
    e.append(f'<line x1="34" y1="352" x2="1216" y2="352" stroke="{gold}" stroke-width="0.6" opacity="0.5"/>')
    e.append(f'<text x="640" y="371" text-anchor="middle" font-family="{MONO}" font-size="10" fill="{dim}" letter-spacing="1.6">'
             f'ОБНОВЛЕНО {esc(str(facts.get("last_date") or ""))} · {facts.get("size_kb")} КБ · КОММИТОВ {facts.get("n_commits")} · РЕЛИЗОВ {facts.get("releases")} · SHA-{esc(facts.get("hash8",""))} · РЕВО В ОСНОВЕ ВСЕГО · REVE=РЕВО</text>')
    e.append("</svg>")
    return "".join(e)


def patch_readme(md, facts):
    block = (
        "<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->\n"
        '<div align="center">\n'
        f'  <img src="revo-page.svg" width="100%" alt="РЕВО-паспорт страницы {CFG["name"]} в каноне ORNAMENTAL MYTHO-REALISM: орнаментальная решётка, медальон-миф, строение файлов, лексикон — по фактическому контенту" />\n'
        "</div>\n\n"
        "| ФАЙЛОВ | ПАПОК | КОММИТОВ | ОБНОВЛЕНО | РЕЛИЗОВ |\n"
        "|---:|---:|---:|---|---:|\n"
        f'| {facts.get("n_files")} | {facts.get("n_dirs")} | {facts.get("n_commits")} | {facts.get("last_date")} | {facts.get("releases")} |\n'
        "<!--ФОРЖ:ПАСПОРТ:КОНЕЦ-->"
    )
    if "<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->" in md:
        md = re.sub(r"<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->.*?<!--ФОРЖ:ПАСПОРТ:КОНЕЦ-->", block.replace("\\", "\\\\"), md, flags=re.S)
        return md
    if "<!--ФОРЖ:МУЗА:КОНЕЦ-->" in md:
        return md.replace("<!--ФОРЖ:МУЗА:КОНЕЦ-->", "<!--ФОРЖ:МУЗА:КОНЕЦ-->\n\n" + block, 1)
    if "<!--ФОРЖ:АККАУНТ:КОНЕЦ-->" in md:
        return md.replace("<!--ФОРЖ:АККАУНТ:КОНЕЦ-->", "<!--ФОРЖ:АККАУНТ:КОНЕЦ-->\n\n" + block, 1)
    i = md.find("</div>")
    if i != -1 and md.find("<div") != -1 and i - md.find("<div") < 600:
        return md[:i + 6] + "\n\n" + block + md[i + 6:]
    return block + "\n\n" + md


def collect_local():
    paths = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.split()
    n_commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout.strip()
    last_date = subprocess.run(["git", "log", "-1", "--format=%cs"], capture_output=True, text=True).stdout.strip()
    size_kb = sum((os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(".")
                   for f in fn if ".git" not in dp), 0) // 1024
    readme = ""
    if os.path.exists("README.md"):
        readme = open("README.md", encoding="utf-8", errors="ignore").read()
    f = facts_from_paths(paths, int(n_commits or 1), last_date, size_kb, readme,
                         CFG.get("topics") or [], CFG.get("desc") or "", CFG.get("releases") or 0)
    return f


if __name__ == "__main__":
    facts = collect_local()
    svg = build_svg(facts)
    open("revo-page.svg", "w", encoding="utf-8").write(svg)
    if os.path.exists("README.md"):
        md = open("README.md", encoding="utf-8").read()
        open("README.md", "w", encoding="utf-8").write(patch_readme(md, facts))
    print(f"РЕВО-ПАСПОРТ ({CANON}): {CFG['name']} — файлов {facts['n_files']}, папок {facts['n_dirs']}, "
          f"коммитов {facts['n_commits']}, лексикон {' '.join(facts['lexicon'])}, SHA-{facts['hash8']}")
