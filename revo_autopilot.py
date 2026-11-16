#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РЕВО-ПАСПОРТ СТРАНИЦЫ — движок контентного изображения.
Куёт revo-page.svg СТРОГО из фактов страницы: файлы, папки, коммиты, размер, дата,
лексикон README, топики. Один исходник: песочница правит CFG атрибутом, автопилот в репо
несёт свой CFG, вшитый при деплое. Только stdlib — работает в GitHub Actions."""
import hashlib, json, os, re, subprocess

try:
    CFG = json.loads(r'''{"name": "voice-atlas-llm", "num": 59, "school": "АРФА ГОЛОСОВ", "desc": "Атлас-LLM: модель-эксперт по клонированию голоса (дизентанглмент, TTS/VC/SVC/SVS) — LoRA-обучение на корпусе атласа 2026, RAG, гейты качества", "topics": ["atlas", "llm", "lora", "python", "speech", "tts", "voice-cloning"], "releases": 8, "palette": {"bg": "#0F0A0C", "bg2": "#181016", "ink": "#EED8CE", "gold": "#B08D3E", "gold2": "#F2C464", "dim": "#8A5E6C"}}''')
except Exception:  # пустая заглушка для импорта в песочнице; CFG подменяется атрибутом
    CFG = {"name": "REVO", "num": 0, "school": "", "desc": "", "topics": [], "releases": 0,
           "palette": dict(bg="#EDE9E0", bg2="#F4F1EA", ink="#17150F", gold="#8A6D2F",
                           gold2="#B08D3E", dim="#6E675B")}

MONO = "'Cascadia Mono', ui-monospace, Consolas, monospace"
SERIF = "Georgia, 'Times New Roman', serif"
REVO = "#D5281B"
STOP = {"полимат", "полимата", "кузня", "кузни", "revo", "reve", "раунд", "round", "дом",
        "дома", "доме", "хозяин", "хозяина", "github", "gitlab", "https", "http", "com",
        "org", "net", "www", "readme", "license", "репозиторий", "репо", "страница",
        "страницы", "which", "their", "there", "about", "сайте", "проекта", "проект"}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def wrap2(text, width=94):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
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


def build_svg(facts):
    pal = CFG["palette"]
    bg, bg2 = pal["bg"], pal.get("bg2", pal["bg"])
    ink, gold, gold2, dim = pal["ink"], pal["gold"], pal["gold2"], pal["dim"]
    num = CFG["num"]
    name = CFG["name"]
    school = CFG["school"]
    e = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 400" width="1280" height="400">']
    e.append(f'<defs><radialGradient id="rp{num}" cx="0.5" cy="0.46" r="1.05">'
             f'<stop offset="0" stop-color="{bg2}"/><stop offset="1" stop-color="{bg}"/></radialGradient></defs>')
    e.append(f'<rect width="1280" height="400" fill="{bg}"/>')
    e.append(f'<rect width="1280" height="400" fill="url(#rp{num})" opacity="0.92"/>')
    e.append(f'<rect x="14" y="14" width="1252" height="372" fill="none" stroke="{gold}" stroke-width="1.3"/>')
    e.append(f'<rect x="22" y="22" width="1236" height="356" fill="none" stroke="{gold}" stroke-width="0.55" opacity="0.55"/>')
    for (x, y, dx, dy) in ((22, 22, 1, 1), (1258, 22, -1, 1), (22, 378, 1, -1), (1258, 378, -1, -1)):
        e.append(f'<path d="M {x} {y+dy*13} L {x} {y} L {x+dx*13} {y}" fill="none" stroke="{gold2}" stroke-width="1.4"/>')
    e.append(f'<path d="M 22 54 L 22 22 L 54 22 Z" fill="{REVO}"/>')
    e.append(f'<text x="64" y="66" font-family="{MONO}" font-size="11" fill="{gold}" letter-spacing="4">РЕВО-ПАСПОРТ СТРАНИЦЫ · {esc(school.upper())}</text>')
    ticks = "".join(f'<line x1="0" y1="-17" x2="0" y2="-14" transform="rotate({a})"/>' for a in range(0, 360, 30))
    e.append(f'<g transform="translate(1236,48)"><circle r="15" fill="none" stroke="{REVO}" stroke-width="1.3"/>'
             f'<circle r="11" fill="none" stroke="{REVO}" stroke-width="0.55" opacity="0.6"/>'
             f'<text y="4" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{gold2}">{num}</text>'
             f'<g stroke="{REVO}" stroke-width="0.7">{ticks}</g></g>')
    nm = name.upper()
    fs = min(50, max(24, 620 / (len(nm) * 0.78)))
    ls = 5 if fs >= 38 else 3
    e.append(f'<text x="64" y="{150:.0f}" font-family="{SERIF}" font-size="{fs:.1f}" fill="{ink}" letter-spacing="{ls}">{esc(nm)}</text>')
    e.append(f'<line x1="64" y1="178" x2="740" y2="178" stroke="{gold}" stroke-width="1" opacity="0.85"/>')
    lines = wrap2(facts.get("desc") or CFG.get("desc") or "", 92)
    d1 = lines[0] if len(lines) > 0 else ""
    d2 = lines[1] if len(lines) > 1 else ""
    if d1:
        e.append(f'<text x="64" y="206" font-family="{MONO}" font-size="13" fill="{dim}" letter-spacing="0.3">{esc(d1)}</text>')
    if d2:
        e.append(f'<text x="64" y="226" font-family="{MONO}" font-size="13" fill="{dim}" letter-spacing="0.3">{esc(d2)}</text>')
    lx = facts.get("lexicon") or []
    if lx:
        e.append(f'<text x="64" y="262" font-family="{MONO}" font-size="10.5" fill="{gold}" letter-spacing="2.5">ЛЕКСИКОН ЭТОЙ СТРАНИЦЫ (из README)</text>')
        cx = 64
        for w in lx[:4]:
            cw = int(len(w) * 9.2 + 24)
            e.append(f'<rect x="{cx}" y="274" width="{cw}" height="24" fill="none" stroke="{gold2}" stroke-width="0.9"/>'
                     f'<text x="{cx+cw/2:.0f}" y="290" text-anchor="middle" font-family="{MONO}" font-size="11" fill="{ink}" letter-spacing="1">{esc(w)}</text>')
            cx += cw + 10
    x0 = 800
    e.append(f'<text x="{x0}" y="78" font-family="{MONO}" font-size="10.5" fill="{gold}" letter-spacing="2.5">СТРОЕНИЕ СТРАНИЦЫ · ФАЙЛЫ ПО ТИПАМ</text>')
    exts = facts.get("exts") or []
    mx = max((c for _, c in exts), default=1)
    for i, (x, c) in enumerate(exts):
        y = 100 + i * 21
        bw = int(8 + 240 * (c / mx) ** 0.62)
        e.append(f'<text x="{x0}" y="{y+9}" font-family="{MONO}" font-size="10.5" fill="{ink}" letter-spacing="0.5">{esc(x)}</text>')
        e.append(f'<rect x="{x0+66}" y="{y}" width="{bw}" height="12" fill="{gold}" opacity="0.82"/>')
        e.append(f'<text x="{x0+66+bw+8:.0f}" y="{y+9}" font-family="{MONO}" font-size="10.5" fill="{dim}">{c}</text>')
    trio = [("ФАЙЛОВ", facts.get("n_files")), ("ПАПОК", facts.get("n_dirs")), ("КОММИТОВ", facts.get("n_commits"))]
    for i, (lab, v) in enumerate(trio):
        cx = x0 + 45 + i * 145
        e.append(f'<g transform="translate({cx},278)"><circle r="25" fill="none" stroke="{REVO}" stroke-width="1.2"/>'
                 f'<text y="4.5" text-anchor="middle" font-family="{MONO}" font-size="{10.5 if v and v>9999 else 12}" fill="{gold2}">{v}</text>'
                 f'<text y="44" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="{dim}" letter-spacing="2">{lab}</text></g>')
    tp = facts.get("topics") or []
    tx = x0
    for t in tp:
        tw = int(len(t) * 6.6 + 18)
        if tx + tw > 1236:
            break
        e.append(f'<rect x="{tx}" y="318" rx="4" width="{tw}" height="20" fill="{REVO}"/>'
                 f'<text x="{tx+tw/2:.0f}" y="332" text-anchor="middle" font-family="{MONO}" font-size="9.5" fill="#F5EFE2" letter-spacing="0.8">{esc(t)}</text>')
        tx += tw + 10
    e.append(f'<line x1="64" y1="348" x2="1216" y2="348" stroke="{gold}" stroke-width="0.6" opacity="0.5"/>')
    e.append(f'<text x="640" y="371" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{dim}" letter-spacing="2">'
             f'ОБНОВЛЕНО {esc(str(facts.get("last_date") or ""))} · {facts.get("size_kb")} КБ · КОММИТОВ {facts.get("n_commits")} · РЕЛИЗОВ {facts.get("releases")} · SHA-{esc(facts.get("hash8",""))} · РЕВО В ОСНОВЕ ВСЕГО · REVE=РЕВО</text>')
    e.append("</svg>")
    return "".join(e)


def patch_readme(md, facts):
    block = (
        "<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->\n"
        '<div align="center">\n'
        f'  <img src="revo-page.svg" width="100%" alt="РЕВО-паспорт страницы {CFG["name"]}: строение файлов, лексикон, числа — по фактическому контенту" />\n'
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
    print(f"РЕВО-ПАСПОРТ: {CFG['name']} — файлов {facts['n_files']}, папок {facts['n_dirs']}, "
          f"коммитов {facts['n_commits']}, лексикон {' '.join(facts['lexicon'])}, SHA-{facts['hash8']}")
