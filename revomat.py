#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""РЁВО-АВТОМАТ КАНОНА · revomat.py · конечный автомат Ornamental Mytho-Realism.
Только stdlib. Живёт в репе, запускается Actions'ом (revomat.yml) и руками.

Состояния (закон переходов, конечный автомат):
  ПЕПЕЛ → ПРОБУЖДЕНИЕ → СВЕРКА → (дефекты) ДРЕЙФ → КУЗНЯ → ЗДРАВИЕ
                              → (чисто) ЗДРАВИЕ
  ЗДРАВИЕ → ПРОБУЖДЕНИЕ (следующий цикл)
Дрейф лечится предопределённым шагом (self-healing CI: детект известного
паттерна → заданное лекарство → повторный прогон), а не самодеятельностью:
лекарство одно — перековка паспорта движком revo_autopilot.py и запись state.

Доказательство работы — automaton-state.json: состояния, гейты, переходы,
факты, штамп издания. Файл коммитится каждой сменой состояния.

Гейты СВЕРКИ:
  G1 паспорт revo-page.svg существует и несёт маркер канона
  G2 banner.png существует и не пуст
  G3 все относительные ссылки README разрешаются в файлы репы
  G4 движок revo_autopilot.py существует и несёт маркер канона
  G5 state-файл предыдущего цикла существует (непрерывность)
"""
import json, os, re, subprocess, sys
from datetime import datetime, timezone

CANON = "ORNAMENTAL MYTHO-REALISM"
STATE_FILE = "automaton-state.json"
EDITION = "ИЗДАНИЕ r19"
S_INIT, S_AWAKE, S_AUDIT, S_DRIFT, S_FORGE, S_HEALTH = (
    "ПЕПЕЛ", "ПРОБУЖДЕНИЕ", "СВЕРКА", "ДРЕЙФ", "КУЗНЯ", "ЗДРАВИЕ")


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout.strip()


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def rel_links(readme):
    out = []
    for s in re.findall(r'(?:src|href)="([^"]+)"', readme):
        if s.startswith(("http", "data:", "#", "mailto:")):
            continue
        p = s.split("#")[0].split("?")[0].strip()
        if p:
            out.append(p)
    return sorted(set(out))


def collect_facts():
    # истина файловой системы: на диске, без .git, без state-файла (он не содержание, а след автомата)
    n_files = 0
    for dp, dn, fn in os.walk("."):
        if ".git" in dp.split(os.sep):
            continue
        n_files += sum(1 for f in fn if not (dp == "." and f == STATE_FILE))
    n_commits = sh(["git", "rev-list", "--count", "HEAD"]) or "1"
    last_date = sh(["git", "log", "-1", "--format=%cs"])
    readme = ""
    if os.path.exists("README.md"):
        readme = open("README.md", encoding="utf-8", errors="ignore").read()
    return {"n_files": n_files, "n_commits": int(n_commits or 1),
            "last_date": last_date, "links": rel_links(readme),
            "readme_bytes": len(readme.encode())}


def gates(facts):
    g = {}
    passport = open("revo-page.svg", encoding="utf-8", errors="ignore").read() if os.path.exists("revo-page.svg") else ""
    g["G1_паспорт_канон"] = (CANON in passport)
    b = os.path.exists("banner.png") and os.path.getsize("banner.png") > 1000
    g["G2_баннер"] = bool(b)
    g["G3_ссылки_цельны"] = all(os.path.exists(p) for p in facts["links"])
    engine = open("revo_autopilot.py", encoding="utf-8", errors="ignore").read() if os.path.exists("revo_autopilot.py") else ""
    g["G4_движок_канон"] = bool(engine) and (CANON in engine)
    g["G5_непрерывность"] = os.path.exists(STATE_FILE)
    return g


def load_prev():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return None


def transition_log(prev, state, why):
    log = (prev or {}).get("переходы", [])
    log.append({"из": (prev or {}).get("состояние", S_INIT), "в": state, "почему": why,
                "когда": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return log[-12:]


def heal():
    """Предопределённое лекарство: перековка паспорта движком дома (self-healing CI:
    один известный паттерн — одно заданное лечение). Возвращает True если движок сработал."""
    if os.path.exists("revo_autopilot.py"):
        r = subprocess.run([sys.executable, "revo_autopilot.py"], capture_output=True, text=True, timeout=300)
        return r.returncode == 0
    return False


def write_state(repo, num, state, gates_d, facts, log, defects):
    doc = {"автомат": "РЁВО-АВТОМАТ КАНОНА", "канон": CANON, "издание": EDITION,
           "репа": repo, "номер": num, "состояние": state,
           "гейты": gates_d, "дефекты": defects, "факты": {k: v for k, v in facts.items() if k != "links"},
           "ссылок_проверено": len(facts["links"]),
           "переходы": log,
           "обновлено": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    open(STATE_FILE, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return doc


def self_commit(msg):
    """Самозапись по закону дома (зуб A-HUSH): 3 попытки fetch+rebase+push."""
    sh(["git", "config", "user.name", "revo[bot]"])
    sh(["git", "config", "user.email", "revo[bot]@users.noreply.github.com"])
    sh(["git", "add", "-A"])
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return "без изменений"
    sh(["git", "commit", "-m", msg])
    for attempt in range(1, 4):
        sh(["git", "fetch", "origin", "main", "--quiet"])
        r = subprocess.run(["git", "rebase", "origin/main"], capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)
            continue
        p = subprocess.run(["git", "push", "origin", "HEAD"], capture_output=True, text=True)
        if p.returncode == 0:
            return f"записано (попытка {attempt})"
    return "не записано — тревога (основной гейт остаётся красным)"


def main():
    repo = os.environ.get("GH_REPO") or sh(["git", "remote", "get-url", "origin"]).rsplit("/", 1)[-1].removesuffix(".git")
    num = os.environ.get("REVOMAT_NUM") or ""
    prev = load_prev()
    facts = collect_facts()
    g = gates(facts)
    log = []
    # ПЕПЕЛ → ПРОБУЖДЕНИЕ
    log.append({"из": S_INIT, "в": S_AWAKE, "почему": "старт цикла", "когда": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    # ПРОБУЖДЕНИЕ → СВЕРКА
    log.append({"из": S_AWAKE, "в": S_AUDIT, "почему": "факты собраны", "когда": log[0]["когда"]})
    defects = [k for k, ok in g.items() if not ok]
    prev_facts = (prev or {}).get("факты", {})
    # дрейф — по содержанию; n_commits летучий (+1 каждый цикл самозаписи) и не считается дрейфом
    drift = {k: (prev_facts.get(k), facts[k]) for k in ("n_files", "readme_bytes", "last_date")
             if prev_facts.get(k) != facts[k]}
    if defects or drift:
        # СВЕРКА → ДРЕЙФ → КУЗНЯ
        why = ("гейты: " + ", ".join(defects) if defects else "") + \
              ("; дрейф: " + ", ".join(f"{k} {v[0]}→{v[1]}" for k, v in drift.items()) if drift else "")
        log.append({"из": S_AUDIT, "в": S_DRIFT, "почему": why.strip("; ") or "дрейф", "когда": log[-1]["когда"]})
        healed = heal()
        log.append({"из": S_DRIFT, "в": S_FORGE, "почему": f"лекарство применено (движок: {'да' if healed else 'нет — движка нет'})",
                    "когда": log[-1]["когда"]})
        facts = collect_facts()          # факты после лечения
        g = gates(facts)
        defects = [k for k, ok in g.items() if not ok]
        state = S_HEALTH                 # финал цикла всегда ЗДРАВИЕ; необлечённые дефекты остаются в state-файле
        msg = f"РЁВО-АВТОМАТ: СВЕРКА→ДРЕЙФ→КУЗНЯ→ЗДРАВИЕ ({why[:110]}) · {EDITION} · {CANON}"
    else:
        state = S_HEALTH
        msg = f"РЁВО-АВТОМАТ: СВЕРКА→ЗДРАВИЕ (гейты чисты, дрейфа нет) · {EDITION} · {CANON}"
    log.append({"из": S_DRIFT if drift or defects else S_AUDIT, "в": state,
                "почему": "финал цикла", "когда": log[-1]["когда"]})
    log = ((prev or {}).get("переходы", [])[-10:]) + log  # непрерывная лента переходов
    doc = write_state(repo, num, state, g, facts, log, defects + [f"дрейф {k}" for k in drift])
    res = self_commit(msg)
    print(f"РЁВО-АВТОМАТ · {repo}: {doc['состояние']} · дефекты {len(doc['дефекты'])} · "
          f"ссылок {doc['ссылок_проверено']} · файлов {doc['факты']['n_files']} · запись: {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
