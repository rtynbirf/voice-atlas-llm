#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ДОМ-АВТОМАТ v1 · статусный движок флота.

Не текст О правилах, а исполнитель правил. Конституция дома = таблица
(fsm.json); состояние вычисляется из наблюдаемых фактов, а не декларируется:
  - дата_конца в прошлом -> ПРОСРОЧЕН (автомат считает, автор не пишет);
  - ПОДТВЕРЖДЕНО требует >=2 разных исполнителей реальных случаев;
  - поле "виновный" в записях запрещено (бесвинно, SRE);
  - хэш-цепь журнала амнистий рвётся при любом стирании/правке (append-only);
  - канон-хэш fsm.json вшит в автомат: правка конституции мимо процедуры
    = санкция 2 в любом репозитории флота;
  - пульс = зелёные прогоны этого воркфлоу подряд (Actions API);
    красные прогоны подряд >= N = "пересмотр вне графика" (гипотеза N=3,
    пульс-приближение: точный счёт сбоев правила живёт в реестре 22).

Мировая опора (кузов свой): policy-as-code (OPA/Sentinel), statechart-таблицы,
blameless postmortem (Google SRE), Остром: границы/мониторинг/санкции.

Режимы:
  --check           проверить репозиторий: exit 0 = зелёный, 2 = санкция
  --state           вывести вычисленное состояние JSON и выйти (exit по санкции)
  --amnesty ID ШАГ  амнистия первого признания (гипотеза ПРИЛОЖЕНИЯ):
                    ПРОСРОЧЕН -> ПИЛОТ, запись в ДОМ/журнал_amnistii.jsonl,
                    дата_конца карточки сдвигается на окно_амнистии_дней
  --selftest        векторы автомата (offline)

Python 3.9+, stdlib only. НЕ СЕКРЕТ: токен не хранит, читает GH_TOKEN из env.
"""
import hashlib
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

EXIT_OK = 0
EXIT_SANCTION = 2
CANON_FILENAME = "fsm.json"
JOURNAL_FILENAME = "журнал_amnistii.jsonl"
FORBIDDEN_KEYS = ("виновный", "вина_на", "виновник", "blame", "culprit", "имя_потерпевшего")
WF_PATH = ".github/workflows/dom-avtomat.yml"


def canonical_fsm_hash():
    """Канон-хэш конституции. Вшит: правка fsm.json где угодно = санкция."""
    return "4918bb78ccedee284881f8455fddeed3be7ff77370911427e2e6c5517bec85ba"


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _words(text):
    import re
    return len([w for w in re.split(r"\s+", str(text)) if w])


# ---------------------------------------------------------------- находка
def find_dom(root):
    """ДОМ-каталог: рядом с автоматом или в корне репо."""
    here = Path(__file__).resolve().parent
    if (here / CANON_FILENAME).exists():
        return here
    cand = Path(root) / "ДОМ"
    if (cand / CANON_FILENAME).exists():
        return cand
    return None


def find_cards(root):
    for name in ("kartochki", "ДОМ/карточки", "ДОМ/kartochki"):
        p = Path(root) / name
        if p.is_dir() and list(p.glob("*.json")):
            return p
    return None


# ------------------------------------------------------------- граница
def check_boundary(dom_dir):
    """sha256(fsm.json) == канон. Остром: чёткие границы. Правка мимо процедуры = санкция.
    Возвращает (ок, злые, добрые) — доброе в санкции не попадает."""
    fsm = dom_dir / CANON_FILENAME
    got = _sha(fsm.read_text(encoding="utf-8"))
    want = canonical_fsm_hash()
    if got != want:
        return False, [f"ГРАНИЦА НАРУШЕНА: хэш fsm.json {got[:12]} != канон {want[:12]}"], []
    return True, [], ["ГРАНИЦА ЦЕЛА: конституция синхронна с каноном дома"]


def blameless_scan(obj, where, reasons):
    """Бесвинно: поле 'виновный' и имена потерпевших запрещены схемой."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                reasons.append(f"БЕСВИННО НАРУШЕНО: поле {k!r} в {where} запрещено схемой")
            blameless_scan(v, where, reasons)
    elif isinstance(obj, list):
        for item in obj:
            blameless_scan(item, where, reasons)


# ------------------------------------------------------------- карточки
def compute_card(card, today):
    """Статус ВЫЧИСЛЯЕТСЯ. Возвращает (вычислен, санкции, факты)."""
    facts = {}
    sanctions = []
    declared = card.get("статус")
    de = card.get("дата_конца")
    try:
        end = date.fromisoformat(str(de)) if de else None
    except ValueError:
        end = None
        sanctions.append(f"дата_конца не ISO: {de!r}")
    if end is not None:
        facts["до_конца_дней"] = (end - today).days
    execs = card.get("исполнители") or []
    execs = [str(e) for e in execs if str(e)]
    facts["исполнителей"] = len(set(execs))
    if declared == "ПОДТВЕРЖДЕНО":
        if facts["исполнителей"] < 2:
            sanctions.append("СТАТУС ЛОЖЕН: ПОДТВЕРЖДЕНО требует >=2 разных исполнителей")
            return "ЛОЖЕН", sanctions, facts
        return "ПОДТВЕРЖДЕНО", sanctions, facts
    if declared in ("СНЕСЕНА", "ЗАМЕНЕНА"):
        return declared, sanctions, facts
    # ЗАЯВЛЕНА / ПИЛОТ: дата решает, не автор
    if end is None:
        sanctions.append("ПИЛОТ/ЗАЯВЛЕНА без даты_конца = вечный закон; автомат не пропускает")
        return "ЛОЖЕН", sanctions, facts
    if end <= today:
        return "ПРОСРОЧЕН", sanctions, facts
    return declared if declared else "ЛОЖЕН", sanctions, facts


def check_cards(cards_dir, today, fsm):
    """Вычислить состояние всех карточек. Перескок статуса мимо таблицы ловится."""
    reasons = []
    rows = []
    transitions = {tuple(t) for t in fsm.get("переходы", [])}
    for f in sorted(cards_dir.glob("*.json")):
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            reasons.append(f"{f.name}: КАРТОЧКА КРИВАЯ (json: {e})")
            continue
        blameless_scan(card, f"карточка {card.get('id', f.name)}", reasons)
        computed, sanc, facts = compute_card(card, today)
        reasons.extend(sanc)
        rows.append({"id": card.get("id", f.stem), "заявлен": card.get("статус"),
                     "вычислен": computed, **facts})
        # перескок: заявленный статус должен быть достижим из допустимых источников
        if computed in ("ПОДТВЕРЖДЕНО", "ЗАМЕНЕНА", "СНЕСЕНА"):
            srcs = [a for (a, b) in transitions if b == computed]
            if srcs and card.get("статус") not in srcs and card.get("статус") != computed:
                reasons.append(f"ПЕРЕХОД ЗАПРЕЩЁН: в {computed} можно из {srcs}, а не из {card.get('статус')!r}")
    return rows, reasons


# --------------------------------------------------- журнал амнистий
def journal_chain_verify(journal_path):
    """Хэш-цепь: строка i несёт prev=sha256(строка i-1 целиком). Рваная цепь = правка/стирание."""
    reasons, ok = [], True
    if not journal_path.exists():
        return True, ["ЖУРНАЛ: пуст (амнистий не было)"], reasons
    prev = ""
    n = 0
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            reasons.append(f"ЖУРНАЛ ПОРВАН: строка {n+1} не JSON")
            return False, ["ЖУРНАЛ ПОРВАН"], reasons
        if rec.get("prev") != prev:
            reasons.append(f"ЖУРНАЛ ПОРВАН: строка {n+1} несёт чужой prev (стирание/правка?)")
            return False, ["ЖУРНАЛ ПОРВАН"], reasons
        blameless_scan(rec, f"журнал строка {n+1}", reasons)
        prev = _sha(line)
        n += 1
    return True, [f"ЖУРНАЛ ЦЕЛ: цепь {n} звеньев не порвана"], reasons


def journal_append(journal_path, record):
    """Дописывание с датой, без стирания. Каждая строка несёт хэш предыдущей."""
    prev = ""
    if journal_path.exists():
        lines = [l for l in journal_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            prev = _sha(lines[-1])
    record = dict(record)
    record["prev"] = prev
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with journal_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ------------------------------------------------------------- пульс
def pulse(repo_env, token):
    """Зелёные/красные прогоны dom-avtomat подряд (Actions API). Без токена: честно неизвестно."""
    if not repo_env or not token:
        return {"зелёных_подряд": None, "красных_подряд": None, "источник": "GH_TOKEN/GH_REPO нет"}
    url = f"https://api.github.com/repos/{repo_env}/actions/runs?per_page=30"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}", "User-Agent": "dom-avtomat"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            runs = json.loads(r.read()).get("workflow_runs", [])
    except Exception as e:
        return {"зелёных_подряд": None, "красных_подряд": None, "источник": f"API недоступен: {e}"}
    runs = [r for r in runs if r.get("path") == WF_PATH and r.get("status") == "completed"]
    green = red = 0
    for r in runs:  # от свежего к старому
        if r.get("conclusion") == "success":
            if red:
                break
            green += 1
        elif r.get("conclusion") in ("failure", "timed_out", "action_required"):
            if green:
                break
            red += 1
        else:
            break
    return {"зелёных_подряд": green, "красных_подряд": red, "источник": "Actions API"}


# ------------------------------------------------------------- check
def run_check(root, today, out):
    dom = find_dom(root)
    if dom is None:
        out["состояние"] = "ВНЕ ДОМА"
        out["санкции"] = ["ДОМ/ с fsm.json не найден: репозиторий не несёт конституцию"]
        return EXIT_SANCTION
    ok, bad, good = check_boundary(dom)
    out["граница"] = good
    reasons_all = list(bad)
    fsm = json.loads((dom / CANON_FILENAME).read_text(encoding="utf-8"))
    cards_dir = find_cards(root)
    rows = []
    if cards_dir:
        rows, r = check_cards(cards_dir, today, fsm)
        reasons_all.extend(r)
        for row in rows:
            if row["вычислен"] == "ПРОСРОЧЕН":
                reasons_all.append(f"ПРОСРОЧЕН: карточка {row['id']} — амнистия или пересмотр")
    chain_ok, chain_msgs, r = journal_chain_verify(dom / JOURNAL_FILENAME)
    out["журнал"] = chain_msgs
    reasons_all.extend(r)
    p = pulse(os.environ.get("GH_REPO"), os.environ.get("GH_TOKEN"))
    out["пульс"] = p
    params = fsm.get("параметры", {})
    if p.get("красных_подряд") is not None:
        if p["красных_подряд"] >= params.get("пульс_пересмотра", 3):
            reasons_all.append(f"ПУЛЬС: {p['красных_подряд']} красных подряд — пересмотр вне графика (гипотеза N=3)")
        elif p["зелёных_подряд"] and p["зелёных_подряд"] >= params.get("пульс_готовности", 3) and rows:
            reasons_all.append("ПУЛЬС: механизм жив >=3 зелёных подряд; подтверждение дают только 2 исполнителя реальных случаев (реестр 22)")
    hard = [x for x in reasons_all if any(x.startswith(p) for p in
            ("ГРАНИЦА", "СТАТУС", "БЕСВИННО", "ЖУРНАЛ ПОРВАН", "ПЕРЕХОД ЗАПРЕЩЁН", "ДОМ/", "ПИЛОТ/ЗАЯВЛЕНА", "дата_конца"))]
    soft = [x for x in reasons_all if x not in hard]
    out["состояние"] = "ЗЕЛЁНЫЙ" if not hard else "САНКЦИЯ"
    out["карточки"] = rows
    out["санкции"] = hard
    out["замечания"] = soft
    out["счётчик_санкций"] = len(hard)
    return EXIT_OK if not hard else EXIT_SANCTION


# ------------------------------------------------------------- амнистия
def run_amnesty(root, card_id, step, today):
    """Амнистия первого признания: ПРОСРОЧЕН -> ПИЛОТ, запись остаётся, цена прощается."""
    dom = find_dom(root)
    if dom is None:
        print("ДОМ/ не найден — амнистии негде жить")
        return EXIT_SANCTION
    fsm = json.loads((dom / CANON_FILENAME).read_text(encoding="utf-8"))
    window = fsm.get("параметры", {}).get("окно_амнистии_дней", 14)
    cards_dir = find_cards(root)
    if cards_dir is None:
        print("Карточек в репо нет — амнистия применяется к карточкам дома")
        return EXIT_SANCTION
    target = None
    for f in sorted(cards_dir.glob("*.json")):
        card = json.loads(f.read_text(encoding="utf-8"))
        if card.get("id") == card_id:
            target = (f, card)
    if target is None:
        print(f"Карточка {card_id!r} не найдена")
        return EXIT_SANCTION
    f, card = target
    computed, _, _ = compute_card(card, today)
    if computed != "ПРОСРОЧЕН":
        print(f"АМНИСТИЯ ОТКАЗАНА: {card_id} вычислен {computed}, а не ПРОСРОЧЕН — амнистировать нечего")
        return EXIT_SANCTION
    new_end = today + timedelta(days=window)
    card["дата_конца"] = new_end.isoformat()
    f.write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    journal_append(dom / JOURNAL_FILENAME, {
        "дата": today.isoformat(), "тип": "амнистия", "карточка": card_id,
        "шаг": step, "исполнитель": os.environ.get("ДОМ_ИСПОЛНИТЕЛЬ", "дом-автомат"),
        "дата_конца_новая": new_end.isoformat(),
    })
    print(f"АМНИСТИЯ ДАНА: {card_id} ПРОСРОЧЕН -> ПИЛОТ до {new_end}; запись в журнале осталась")
    return EXIT_OK


# ------------------------------------------------------------- selftest
def selftest():
    import tempfile
    today = date.today()
    ok = fail = 0

    def vector(name, cond):
        nonlocal ok, fail
        ok += 1 if cond else 0
        fail += 0 if cond else 1
        print(f"  вектор {ok + fail}: {name} [{'OK' if cond else 'ПРОВАЛ'}]")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dom = td / "ДОМ"
        dom.mkdir()
        (dom / CANON_FILENAME).write_text(
            (Path(__file__).resolve().parent / CANON_FILENAME).read_text(encoding="utf-8"),
            encoding="utf-8")
        ok1, _bad1, _good1 = check_boundary(dom)
        vector("канон-хэш цел", ok1)
        (dom / CANON_FILENAME).write_text('{"версия":"0.0.1"}', encoding="utf-8")
        ok2, bad2, _ = check_boundary(dom)
        vector("правка fsm.json мимо процедуры = санкция", (not ok2) and any("ГРАНИЦА НАРУШЕНА" in x for x in bad2))
        (dom / CANON_FILENAME).write_text(
            (Path(__file__).resolve().parent / CANON_FILENAME).read_text(encoding="utf-8"),
            encoding="utf-8")
        base = {"id": "t", "кто": "агент", "действие": "работает", "условия": "живой ключ",
                "результат": "зелёный", "при_сбое": "запись в реестр", "пересмотр": "2 недели",
                "происхождение": "канон", "статус": "ПИЛОТ", "исполнители": ["A"]}
        fresh = dict(base, дата_конца=str(today + timedelta(days=10)))
        computed, sanc, _ = compute_card(fresh, today)
        vector("свежий ПИЛОТ вычислен как ПИЛОТ", computed == "ПИЛОТ" and not sanc)
        old = dict(base, дата_конца=str(today - timedelta(days=1)))
        computed, _, _ = compute_card(old, today)
        vector("истёкший ПИЛОТ автомат считает ПРОСРОЧЕН", computed == "ПРОСРОЧЕН")
        bad = dict(base, статус="ПОДТВЕРЖДЕНО", дата_конца=str(today + timedelta(days=5)))
        computed, sanc, _ = compute_card(bad, today)
        vector("ПОДТВЕРЖДЕНО с 1 исполнителем = СТАТУС ЛОЖЕН", computed == "ЛОЖЕН" and sanc)
        good = dict(bad, исполнители=["A", "B"])
        computed, sanc, _ = compute_card(good, today)
        vector("ПОДТВЕРЖДЕНО с 2 исполнителями = зелёный", computed == "ПОДТВЕРЖДЕНО" and not sanc)
        blame = dict(fresh, виновный="кто-то")
        reasons = []
        blameless_scan(blame, "test", reasons)
        vector("поле 'виновный' ловится схемой", any("БЕСВИННО" in x for x in reasons))
        jp = dom / JOURNAL_FILENAME
        journal_append(jp, {"дата": str(today), "тип": "амнистия", "карточка": "t", "шаг": "признание", "исполнитель": "ХОЗЯИН"})
        line2 = {"дата": str(today), "тип": "амнистия", "карточка": "t2", "шаг": "шаг2", "исполнитель": "агент"}
        journal_append(jp, line2)
        okc, _, _ = journal_chain_verify(jp)
        vector("хэш-цепь журнала цела", okc)
        lines = jp.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["шаг"] = "переписанное признание"
        lines[0] = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        jp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        okc, _, _ = journal_chain_verify(jp)
        vector("переписанная строка рвёт цепь = санкция", not okc)
        fsm = json.loads((dom / CANON_FILENAME).read_text(encoding="utf-8"))
        transitions = {tuple(t) for t in fsm["переходы"]}
        vector("ЗАЯВЛЕНА->ПОДТВЕРЖДЕНО перескок запрещён таблицей", ("ЗАЯВЛЕНА", "ПОДТВЕРЖДЕНО") not in transitions)
        vector("СНЕСЕНА терминальна: выходов из неё в таблице нет", not [b for (a, b) in transitions if a == "СНЕСЕНА"])
    print(f"ДОМ-АВТОМАТ: векторы {ok}/{ok + fail}; статусы вычисляются, границы бьют, цепь рвётся честно")
    return fail == 0


# ------------------------------------------------------------- main
def main():
    args = sys.argv[1:]
    root = Path.cwd()
    if "--selftest" in args:
        sys.exit(0 if selftest() else 1)
    if "--amnesty" in args:
        i = args.index("--amnesty")
        cid, step = args[i + 1], args[i + 2] if len(args) > i + 2 else "признание без шага"
        sys.exit(run_amnesty(root, cid, step, date.today()))
    out = {}
    rc = run_check(root, date.today(), out)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        lines = ["## ДОМ-АВТОМАТ · вычисленное состояние", ""]
        lines.append(f"**Состояние: {out.get('состояние')}** · санкций: {out.get('счётчик_санкций', 0)}")
        if out.get("карточки"):
            lines += ["", "| карточка | заявлен | вычислен | до конца (дн.) | исполнителей |", "|---|---|---|---|---|"]
            for r in out["карточки"]:
                lines.append(f"| {r['id']} | {r['заявлен']} | {r['вычислен']} | {r.get('до_конца_дней', '—')} | {r.get('исполнителей', 0)} |")
        if out.get("граница"):
            lines += ["", *out["граница"]]
        if out.get("пульс"):
            lines.append(f"*Пульс: {out['пульс']['зелёных_подряд']} зелёных / {out['пульс']['красных_подряд']} красных подряд ({out['пульс']['источник']})*")
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    if "--state" not in args:
        for k in ("граница", "журнал", "санкции", "замечания"):
            for line in out.get(k) or []:
                print(line)
    sys.exit(rc)


if __name__ == "__main__":
    main()
