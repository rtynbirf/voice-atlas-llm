#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Клеточная нога крови: получил конверт → сверил с собой и летописью →
дописал эхо в летопись роя → подготовил кровь для следующей клетки.

Работает в CI клетки. stdlib-only. Все шаги печатают ФАКТ (HTTP-код, хеш,
статус) — кровь не бывает «примерно доставлена».

Переменные окружения:
  BLOOD_ENVELOPE   — JSON конверта от предыдущего тела (client_payload.envelope)
  CELL_NAME        — имя клетки (например runtime-protocol)
  CELL_SHA         — наблюдаемый HEAD клетки (github.sha)
  GH_TOKEN         — токен с доступом к летописи и dispatch
  BLOOD_LEDGER_REPO  — репо летописи (по умолчанию rtynbirf/cell-swarm)
  BLOOD_LEDGER_PATH  — путь клеточной летописи (по умолчанию
                       blood/CELLS-LEDGER.jsonl, развёл русел ADR-0004 правка
                       2026-11-09: LEDGER.jsonl остаётся летописью пульсов П-24)

Флаги:
  --dry-run            — сверить и напечатать, ничего не писать
  --manual-check       — ручной workflow_dispatch: только целостность летописи
                         живьём, без эха и без передачи крови (см. manual_check)
  --next-repo NAME     — собрать dispatch-тело для следующей клетки в файл
  --next-output PATH   — куда положить dispatch-тело (по умолчанию /tmp/next_dispatch.json)
  --stale-retries N    — ретрай-окно переходящих ран: до N попыток сверки (по умолчанию 3)
  --stale-pause S      — пауза между попытками, секунд (по умолчанию 30)
  --echo-retries N     — ретрай-окно эха (гонка file_sha): до N попыток PUT (по умолчанию 3)
  --echo-pause S       — пауза между попытками эха, секунд (по умолчанию 10)

Ретрай-окно переходящих ран (TODO ×5 п.1, живой кейс run 42401466454): чужая
летопись в момент сверки может переписываться параллельной волной (гонка
кровообращения). Переходящие классы — сверка повторяется: летопись
STRUCTURE/CHAIN_BROKEN (переписанный/пустой срез — именно им проявился
инцидент «конвертов 0»), входящий конверт STALE (просрочка ttl) и
CHAIN_BROKEN (хвост летописи не тот, на который конверт ссылается — срез
летописи мог не содержать ещё не долитых строк). Постоянные раны — честный
отказ сразу, без ретрая: FORGED (подделка не лечится повтором),
SEQ_STAGNANT, неразобранный конверт. Исчерпание окна: рваная летопись —
честный красный (кровь остановлена); входящий STALE — честный ноль
(TH-KNOW-1: кровь не текла, без лжи и без красного старения в инцидент).

Ретрай-окно эха (TODO ×6 п.4, волна ×8): между чтением летописи и PUT эха
чужая клетка может долить свою строку — GitHub ответит HTTP 409 (sha устарел).
Лечение то же, что у сверки: свежий срез (перечитать, сверить цепь, собрать
эхо ЗАНОВО против нового хвоста — свежий seq и свежий prev_hash), не повтор
вердикта по старым байтам. Идемпотентность: если наше эхо уже стоит в свежем
срезе (тот же src и тот же pulse) — дубля нет, кровь продолжает течь.
Переходящие HTTP: 409 (гонка file_sha), 422 с sha-миссматчем, 5xx (сервер).
Постоянные: прочие 4xx — отказ сразу; свежий срез FORGED/SEQ_STAGNANT —
отказ сразу; STRUCTURE/CHAIN_BROKEN — переходящая гонка переписи.
Исчерпание окна эха — честный exit 3: эхо не долито, летопись без факта.
"""
import base64
import json
import os
import sys
import time
import urllib.request

from blood import (
    DRIFT,
    FORGED,
    STALE,
    VERIFIED,
    accept,
    canonical_json,
    chain_verify,
    make_envelope,
    tail_hash,
    verify_envelope,
)

OBSERVED = "OBSERVED"  # клетка без ожидания: наблюдает, не сверяется (ADR-0013 ядра)

API = "https://api.github.com"

_sleep = time.sleep  # инъекция паузы: приёмки подменяют, продакшн спит честно


def _flag_int(argv, name, default, minimum):
    """Целый CLI-флаг с честной гарда: мусор/вырожденное значение — ФАКТ-exit
    до любого сетевого шага, не тихий дефолт (угадчик — яд)."""
    if name not in argv:
        return default
    raw = argv[argv.index(name) + 1] if argv.index(name) + 1 < len(argv) else ""
    try:
        val = int(raw)
    except (ValueError, TypeError):
        sys.exit(f"ФАКТ: {name} не целое ({raw!r}) — кровь не течёт вслепую")
    if val < minimum:
        sys.exit(f"ФАКТ: {name}={val} ниже минимума {minimum} — окно вырождено, отказ")
    return val


def reconcile_pulse(token, incoming, stale_retries=3, stale_pause=30, sleep_fn=None):
    """Этапы 1–2 крови (летопись → прививка конверта) в ретрай-окне переходящих ран.

    Каждая попытка ЗАНОВО читает летопись: гонка переписи лечится свежим
    срезом, а не повтором вердикта по старым байтам. Возвращает словарь:
      state="ok"              — можно течь дальше (lines, file_sha, ledger_where готовы)
      state="ledger_broken"   — летопись сломана во всех попытках (честный красный)
      state="stale_exhausted"  — входящий STALE во всех попытках (честный ноль)
    Постоянные раны поднимают sys.exit сразу (FORGED/SEQ_STAGNANT/мусор).
    sleep_fn — инъекция паузы для приёмок (тесты не спят, продакшн спит честно).
    """
    pause = sleep_fn or _sleep
    last_ledger = last_env = None  # последние приговоры для честного отчёта
    for attempt in range(1, stale_retries + 1):
        print(f"ФАКТ: сверка крови, попытка {attempt}/{stale_retries}")
        lines, file_sha, ledger_where = read_ledger(token)
        ok, reason, n = chain_verify(lines)
        print(f"ФАКТ: летопись {ledger_where}: цепь {'целая' if ok else 'СЛОМАНА'} "
              f"({reason}), конвертов {n}")
        if ok:
            tail = tail_hash(lines)
            if incoming.get("hash") == tail:
                print("ФАКТ: входящий конверт уже в летописи (идемпотентный повтор) — кровь продолжает течь")
                return {"state": "ok", "lines": lines, "file_sha": file_sha,
                        "ledger_where": ledger_where}
            ok_env, reason_env = verify_envelope(incoming, tail)
            if ok_env:
                return {"state": "ok", "lines": lines, "file_sha": file_sha,
                        "ledger_where": ledger_where}
            last_env = reason_env
            if reason_env == FORGED:
                sys.exit(f"ФАКТ: входящий конверт отклонён: FORGED — подделка не лечится "
                         f"повтором (seq={incoming.get('seq')}, ts={incoming.get('ts')})")
            if reason_env == "SEQ_STAGNANT" or reason_env == "STRUCTURE":
                print(f"ФАКТ: входящий конверт отклонён: {reason_env} — постоянная рана, "
                      f"ретрай бессмысленен (seq={incoming.get('seq')}, ts={incoming.get('ts')})")
                sys.exit(2)
            # STALE / CHAIN_BROKEN — переходящие: в свежем срезе летописи хвост
            # мог доехать (параллельная волна долила строки) или эхо уже в цепи.
            last_ledger = None
        else:
            last_ledger = (reason, n)
            if reason not in ("STRUCTURE", "CHAIN_BROKEN"):
                # FORGED/SEQ_STAGNANT — подделка/дисциплина не лечатся повтором.
                sys.exit("ФАКТ: летопись подделана — кровь остановлена до разбора")
        if attempt < stale_retries:
            print(f"ФАКТ: рана переходящая ({last_ledger[0] if last_ledger else last_env}) — "
                  f"пауза {stale_pause}с до повторной сверки")
            pause(stale_pause)
    if last_ledger is not None:
        reason, n = last_ledger
        print(f"ФАКТ: ретрай-окно исчерпано ({stale_retries} попыток): летопись "
              f"{reason}, конвертов {n} — гонка не утихла, кровь остановлена честно")
        return {"state": "ledger_broken"}
    print(f"ФАКТ: ретрай-окно исчерпано ({stale_retries} попыток): входящий конверт "
          f"{last_env} (seq={incoming.get('seq')}, ts={incoming.get('ts')}) — "
          f"кровь не текла, эхо не писано, передача не собрана (честный ноль)")
    return {"state": "stale_exhausted"}


def api(method, url, token, payload=None):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def read_ledger(token):
    repo = os.environ.get("BLOOD_LEDGER_REPO", "rtynbirf/cell-swarm")
    path = os.environ.get("BLOOD_LEDGER_PATH", "blood/CELLS-LEDGER.jsonl")
    st, data = api("GET", f"{API}/repos/{repo}/contents/{path}?ref=main", token)
    if st == 404:
        return [], None, f"{repo}/{path} ещё не существует"
    if st != 200:
        sys.exit(f"ФАКТ: летопись не прочитана, HTTP {st}")
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content.splitlines(), data["sha"], f"{repo}/{path}"


def build_echo(lines, cell, expected, status, pulse_seq):
    """Собрать эхо-конверт клетки против хвоста ДАННОГО среза летописи.

    Чистая сборка: seq учитывает чужие эха клетки в срезе (монотонность пары
    src→dst), prev_hash — хеш хвоста среза. В гонке срез меняется — эхо
    собирается заново (append_echo), не переиспользуется по старым байтам.
    """
    seq = 1
    for raw in lines:
        raw = raw.strip()
        if raw:
            e = json.loads(raw)
            if e.get("src") == cell:
                seq = max(seq, e["seq"] + 1)
    echo = make_envelope(
        src=cell, dst="cell-swarm", seq=seq,
        payload={"observed": os.environ.get("CELL_SHA", ""),
                 "expected": expected,
                 "status": status,
                 "pulse": pulse_seq},
        prev_hash=tail_hash(lines), ttl_s=900)
    return echo, canonical_json(echo)


def append_echo(token, lines, file_sha, incoming, cell, expected, status,
                echo_retries=3, echo_pause=10, sleep_fn=None):
    """Шаг 4 крови: дописать эхо в летопись в ретрай-окне гонки file_sha (TODO ×6 п.4).

    Переходящие раны эха: HTTP 409 (чужая клетка долила строку между чтением
    и PUT — sha устарел), 422 с sha-миссматчем, 5xx. Лечение — свежий срез:
    перечитать летопись, сверить цепь, собрать эхо ЗАНОВО против нового
    хвоста и переслить PUT (не повтор вердикта по старым байтам).
    Идемпотентность: наше эхо уже в свежем срезе (тот же src, тот же pulse) —
    дубля нет, кровь продолжает течь.
    Постоянные раны: прочие 4xx — отказ сразу; свежий срез FORGED/SEQ_STAGNANT —
    отказ сразу (подделка и дисциплина не лечатся повтором);
    STRUCTURE/CHAIN_BROKEN — переходящая гонка переписи (как в reconcile_pulse).
    Исчерпание окна — честный sys.exit(3): эхо не долито, летопись без факта.
    Возвращает долетевшее эхо (собранное заново или найденное в срезе) —
    его несёт дальше шаг 5 (кровь следующей клетки).
    sleep_fn — инъекция паузы для приёмок (тесты не спят, продакшн спит честно).
    """
    pause = sleep_fn or _sleep
    repo = os.environ.get("BLOOD_LEDGER_REPO", "rtynbirf/cell-swarm")
    path = os.environ.get("BLOOD_LEDGER_PATH", "blood/CELLS-LEDGER.jsonl")
    last = "окно не открыто"
    for attempt in range(1, echo_retries + 1):
        print(f"ФАКТ: эхо в летопись, попытка {attempt}/{echo_retries}")
        echo, echo_line = build_echo(lines, cell, expected, status, incoming["seq"])
        if attempt == 1:
            print(f"ФАКТ: эхо-конверт слит: seq={echo['seq']} hash={echo['hash'][:12]}…")
        new_content = ("\n".join(lines + [echo_line]) + "\n").encode("utf-8")
        st, resp = api("PUT", f"{API}/repos/{repo}/contents/{path}", token, {
            "message": f"blood: эхо клетки {cell} (пульс #{incoming['seq']}, {status})",
            "content": base64.b64encode(new_content).decode(),
            "sha": file_sha,
        })
        print(f"ФАКТ: эхо в летопись: HTTP {st} (200/201=дописано)")
        if st in (200, 201):
            return echo
        transient = (st == 409 or st >= 500
                     or (st == 422 and "sha" in json.dumps(resp).lower()))
        if not transient:
            sys.exit(f"ФАКТ: эхо не принято, HTTP {st} "
                     f"({(resp or {}).get('message', '')[:120]}) — постоянная рана, "
                     f"кровь не течёт вслепую")
        last = f"HTTP {st}"
        if attempt >= echo_retries:
            break
        # Лечение — свежий срез, не повтор вердикта по старым байтам (×6-канон).
        fresh_lines, fresh_sha, where = read_ledger(token)
        ok, reason, n = chain_verify(fresh_lines)
        print(f"ФАКТ: свежий срез {where}: цепь {'целая' if ok else 'СЛОМАНА'} "
              f"({reason}), конвертов {n}")
        if ok:
            for raw in fresh_lines:
                raw = raw.strip()
                if not raw:
                    continue
                e = json.loads(raw)
                if (e.get("src") == cell
                        and e.get("payload", {}).get("pulse") == incoming["seq"]):
                    print(f"ФАКТ: наше эхо уже в летописи (пульс #{incoming['seq']}) — "
                          f"идемпотентный повтор, дубля нет")
                    return e
            lines, file_sha = fresh_lines, fresh_sha
        elif reason in ("FORGED", "SEQ_STAGNANT"):
            sys.exit(f"ФАКТ: свежий срез летописи {reason} — подделка/дисциплина "
                     f"не лечатся повтором, эхо остановлено")
        else:  # STRUCTURE / CHAIN_BROKEN — переходящая гонка переписи
            last = reason
        print(f"ФАКТ: рана переходящая ({last}) — пауза {echo_pause}с до повторной попытки")
        pause(echo_pause)
    print(f"ФАКТ: ретрай-окно эха исчерпано ({echo_retries} попыток): {last} — "
          f"эхо не долито, кровь остановлена честно")
    sys.exit(3)


def manual_check() -> int:
    """Честный ноль ручного прогона (TH-KNOW-1).

    Конверт может прийти ТОЛЬКО от предыдущей клетки по repository_dispatch:
    в workflow_dispatch client_payload не существует, toJson даёт «null», и
    гарда честно отказывает — рана в том, что красный прогон стареет в
    инцидент по закону «красный > 24 ч». Ручной запуск обязан быть полезным
    и зелёным без лжи: клетка сверяет целостность летописи живьём (это и
    есть её кровная обязанность), не пишет эхо и не передаёт кровь дальше.
    """
    cell = os.environ.get("CELL_NAME", "")
    cell_sha = os.environ.get("CELL_SHA", "")
    token = os.environ.get("GH_TOKEN", "")
    if not cell or not cell_sha or not token:
        print("ФАКТ: ручная сверка без имени клетки/SHA/токена — нечего сверять, "
              "кровь не течёт вслепую")
        return 1
    lines, _file_sha, ledger_where = read_ledger(token)
    ok, reason, n = chain_verify(lines)
    print(f"ФАКТ: летопись {ledger_where}: цепь {'целая' if ok else 'СЛОМАНА'} "
          f"({reason}), конвертов {n}")
    print("ФАКТ: ручной запуск: конверт приходит только через repository_dispatch "
          "от предыдущей клетки — кровь не текла, эхо не писано (честный ноль)")
    return 0 if ok else 2


def verdict_for(incoming: dict, cell: str, cell_sha: str) -> dict:
    """Вердикт клетки над конвертом (чистая функция, ADR-0004 + ADR-0013 ядра).

    Есть явное ожидание для меня (payload.cells[cell]) — сверяю точно (eps=0):
    VERIFIED или DRIFT. Ожидания нет — клетка не сверяется вслепую и не врёт
    DRIFT, сравнивая чужое ожидание со своим телом: она честно OBSERVED
    (наблюдает чужой факт и несёт дальше свой наблюдаемый SHA).
    """
    expected = (incoming.get("payload", {}).get("cells") or {}).get(cell)
    if expected is None:
        return {"status": OBSERVED, "violation": None, "tol": {"eps": 0, "deadband": 0}}
    return {"status": VERIFIED if expected == cell_sha else DRIFT,
            "violation": 0 if expected == cell_sha else None,
            "tol": {"eps": 0, "deadband": 0}}


def main():
    dry = "--dry-run" in sys.argv
    if "--manual-check" in sys.argv:
        sys.exit(manual_check())
    stale_retries = _flag_int(sys.argv, "--stale-retries", 3, 1)
    stale_pause = _flag_int(sys.argv, "--stale-pause", 30, 0)
    echo_retries = _flag_int(sys.argv, "--echo-retries", 3, 1)
    echo_pause = _flag_int(sys.argv, "--echo-pause", 10, 0)
    env_json = os.environ.get("BLOOD_ENVELOPE", "").strip()
    cell = os.environ.get("CELL_NAME", "")
    cell_sha = os.environ.get("CELL_SHA", "")
    token = os.environ.get("GH_TOKEN", "")
    if not env_json or not cell or not cell_sha:
        sys.exit("ФАКТ: нет конверта/имени клетки/SHA — кровь не течёт вслепую")

    # Гарда конверта (issue #2.1): dispatch без конверта приходит как строка
    # «null» (toJson(github.event.client_payload.envelope) от пустого payload),
    # а не пустая строка — проверка на пустоту её пропускала, json.loads давал
    # None, и клетка взрывалась AttributeError на первом .get(). Честный отказ
    # (ФАКТ-exit) вместо traceback — гарда стоит ДО первого сетевого шага.
    try:
        incoming = json.loads(env_json)
    except json.JSONDecodeError as exc:
        sys.exit(f"ФАКТ: конверт не разбирается (JSON: {exc.msg}, позиция {exc.pos}) — кровь не течёт вслепую")
    if not isinstance(incoming, dict):
        sys.exit(f"ФАКТ: конверт не объект (получено: {json.dumps(incoming)}) — "
                 f"dispatch без конверта отклонён, кровь не течёт вслепую")

    # 1–2. Летопись + входящий конверт в ретрай-окне переходящих ран (×6):
    # каждая попытка читает летопись заново — гонка переписи лечится свежим срезом.
    pulse = reconcile_pulse(token, incoming, stale_retries, stale_pause)
    if pulse["state"] == "ledger_broken":
        sys.exit(2)
    if pulse["state"] == "stale_exhausted":
        sys.exit(0)  # честный ноль (TH-KNOW-1): кровь не текла без лжи
    lines, file_sha, ledger_where = pulse["lines"], pulse["file_sha"], pulse["ledger_where"]

    # 3. Сверка ЖЕЛАЕМОЕ↔НАБЛЮДАЕМОЕ: моё живое SHA против того, что несёт кровь
    verdict = verdict_for(incoming, cell, cell_sha)
    expected = (incoming.get("payload", {}).get("cells") or {}).get(cell)
    print(f"ФАКТ: сверка {cell}: желаемое={expected} наблюдаемое={cell_sha} "
          f"→ {verdict['status']}")

    # 4. Эхо-конверт: клетка возвращает в летопись свой факт (не нарратив).
    # Сборка против текущего хвоста; в гонке file_sha (HTTP 409 и др.) —
    # свежий срез и пересборка (ретрай-окно эха, TODO ×6 п.4).
    echo_preview, _ = build_echo(lines, cell, expected, verdict["status"],
                                 incoming["seq"])
    print(f"ФАКТ: эхо-конверт слит: seq={echo_preview['seq']} "
          f"hash={echo_preview['hash'][:12]}…")

    if dry:
        print("ФАКТ: dry-run — летопись не тронута")
    else:
        echo = append_echo(token, lines, file_sha, incoming, cell, expected,
                           verdict["status"], echo_retries, echo_pause)

    # 5. Кровь для следующей клетки (если цепь задана)
    if "--next-repo" in sys.argv:
        next_repo = sys.argv[sys.argv.index("--next-repo") + 1]
        out = sys.argv[sys.argv.index("--next-output") + 1] if "--next-output" in sys.argv \
            else "/tmp/next_dispatch.json"
        body = {"event_type": "blood-pulse", "client_payload": {"envelope": echo}}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        print(f"ФАКТ: dispatch-тело для {next_repo} записано в {out}")


if __name__ == "__main__":
    main()
