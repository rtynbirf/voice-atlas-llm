#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Кровь роя: конверт состояния клетки с допуском, ttl и хеш-цепочкой.

Кровь — не карта и не расписание. Это конверт, который несёт ФАКТ
(что от клетки желают и что клетка наблюдает) от тела к телу ПО СОБЫТИЮ.
Три свойства, вшитые в структуру конверта:

1. ДОПУСК — конверт сам несёт tol (eps + deadband): что считать совпадением.
   Сверка без допуска — гадание о том, где кончается совпадение.
2. ЦЕПЬ — каждый конверт скреплён sha256 предыдущего в летописи
   (паттерн Rekor/Trillian: tamper-evident, подделка середины видна).
3. TTL — конверт протухает: скорость сверки должна быть больше скорости
   изменения территории. Просроченный факт не верифицируют — его выбрасывают.

Кровь не пишет историю заранее и не бежит по таймеру: она течёт только
по событию (repository_dispatch) и только там, где её вызвали.
"""
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

BLOOD_VERSION = 1
GENESIS_HASH = "0" * 64
DEFAULT_TTL_S = 900

# Статусы сверки: ЖЕЛАЕМОЕ↔НАБЛЮДАЕМОЕ
VERIFIED = "VERIFIED"    # наблюдаемое внутри допуска — кровь течёт дальше
DRIFT = "DRIFT"          # наблюдаемое вышло из допуска — факт о дрейфе течёт дальше
STALE = "STALE"          # конверт просрочен (ttl) — сверке не подлежит
FORGED = "FORGED"        # хеш не сходится — конверт подделан, кровь остановлена


def canonical_json(obj) -> str:
    """Канонический JSON: порядок ключей не имеет значения, байты — имеют.

    Любые два равных состояния обязаны давать равные байты — иначе хеш
    сверяет форму записи, а не состояние.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def envelope_hash(env: dict) -> str:
    """sha256 канонического JSON конверта БЕЗ поля hash (само на себя не ссылается)."""
    body = copy.deepcopy(env)
    body.pop("hash", None)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_envelope(src: str, dst: str, seq: int, payload: dict,
                  prev_hash: str, ttl_s: int = DEFAULT_TTL_S,
                  ts: str = None) -> dict:
    """Слить конверт: заполнить поля и запечатать хешем."""
    if seq <= 0:
        raise ValueError("seq должен расти с 1 (нумерация крови, не ядра)")
    env = {
        "v": BLOOD_VERSION,
        "src": src,
        "dst": dst,
        "seq": seq,
        "ts": ts or _now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl_s": ttl_s,
        "payload": payload,
        "prev_hash": prev_hash,
    }
    env["hash"] = envelope_hash(env)
    return env


def verify_envelope(env: dict, prev_hash: str, now_ts=None, check_ttl=True):
    """Проверка одного конверта против ожидаемого prev_hash и текущего времени.

    check_ttl=False — для ИСТОРИИ летописи: записи прошлого не сверяют со
    свежестью (они факты, запечатанные хеш-цепью); TTL обязан только
    входящему конверту при прививке.

    Возвращает (ok, reason). ok=True — конверт несёт живой факт;
    ok=False с reason=FORGED/CHAIN_BROKEN/STALE/STRUCTURE — не несёт ничего.
    """
    if now_ts is None:
        now_ts = _now()
    required = ["v", "src", "dst", "seq", "ts", "ttl_s", "payload", "prev_hash", "hash"]
    if not isinstance(env, dict) or any(k not in env for k in required):
        return False, "STRUCTURE"
    if env["v"] != BLOOD_VERSION:
        return False, "STRUCTURE"
    if not isinstance(env["seq"], int) or env["seq"] <= 0:
        return False, "STRUCTURE"
    if envelope_hash(env) != env["hash"]:
        return False, FORGED
    if env["prev_hash"] != prev_hash:
        return False, "CHAIN_BROKEN"
    if check_ttl:
        try:
            born = datetime.strptime(env["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return False, "STRUCTURE"
        ttl = env.get("ttl_s", DEFAULT_TTL_S)
        if not isinstance(ttl, int) or ttl <= 0:
            return False, "STRUCTURE"
        if now_ts > born + timedelta(seconds=ttl):
            return False, STALE
    return True, VERIFIED


def accept(env: dict, observed, now_ts=None) -> dict:
    """Сверка ЖЕЛАЕМОЕ (в конверте) ↔ НАБЛЮДАЕМОЕ (в клетке) с допуском из конверта.

    Допуск двухступенчатый (как в контуре ADR-0002):
      |нарушение| <= deadband — мёртвая зона, клетка не дёргается;
      deadband < |нарушение| <= eps — внутри допуска, VERIFIED;
      |нарушение| > eps — DRIFT (факт дрейфа, не ложь: кровь несёт и его).
    Дискретное (SHA, имя, флаг) сверяется точно: eps=0.
    """
    if now_ts is None:
        ok, reason = verify_envelope(env, env.get("prev_hash", GENESIS_HASH), now_ts)
        # здесь prev неизвестен — проверяем только хеш и ttl, цепь сверяет летопись
        if not ok and reason in (FORGED, STALE, "STRUCTURE"):
            return {"status": reason, "violation": None, "tol": None}
    payload = env.get("payload", {}) if isinstance(env, dict) else {}
    expected = payload.get("expected")
    tol = payload.get("tol") or {"eps": 0, "deadband": 0}
    eps = float(tol.get("eps", 0))
    deadband = float(tol.get("deadband", 0))
    violation = None
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        violation = abs(float(observed) - float(expected))
        if violation <= deadband:
            status = VERIFIED
        elif violation <= eps:
            status = VERIFIED
        else:
            status = DRIFT
    else:
        status = VERIFIED if expected == observed else DRIFT
        violation = 0 if expected == observed else None
    return {"status": status, "violation": violation, "tol": {"eps": eps, "deadband": deadband}}


# SDK-конверт пульса (blood_sdk, волна ×3, ПРЕДЛОЖЕНИЕ-21/24): тот же канон
# (sort_keys, компактные разделители, UTF-8) и та же хеш-сцепка prev_hash → hash,
# но своя схема записи: type/id/source/ttl_days вместо v/src/dst/seq/ts/ttl_s.
SDK_REQUIRED = ("id", "type", "payload", "source", "ttl_days", "prev_hash", "hash")


def is_sdk_envelope(env) -> bool:
    """SDK-конверт пульса: нет v (версия ядра), есть триада id/type/source.
    Пульс генома живёт в той же летописи blood/LEDGER.jsonl и цепляется
    к её хвосту — верификатор обязан читать обе схемы, иначе чужой факт
    читается как подделка (STRUCTURE) и кровь останавливается ложно."""
    return (isinstance(env, dict) and "v" not in env
            and {"id", "type", "source"}.issubset(env))


def verify_sdk_envelope(env: dict, prev_hash: str):
    """Проверка SDK-конверта пульса в летописи: структура, сцепка, hash и id.

    hash = sha256 канона записи без поля hash; id = первые 16 hex канона
    записи без полей id и hash (канон blood_sdk зафиксирован в selftest).
    TTL истории не сверяется — как у конвертов ядра: прошлое запечатано
    хеш-цепью, свежесть обязана только входящему конверту при прививке.
    Возвращает (ok, reason) в терминах ядра: STRUCTURE/FORGED/CHAIN_BROKEN.
    """
    if not isinstance(env, dict) or any(k not in env for k in SDK_REQUIRED):
        return False, "STRUCTURE"
    if not isinstance(env["ttl_days"], int) or env["ttl_days"] < 0:
        return False, "STRUCTURE"
    if env["prev_hash"] != prev_hash:
        return False, "CHAIN_BROKEN"
    if envelope_hash(env) != env["hash"]:
        return False, FORGED
    body = copy.deepcopy(env)
    body.pop("hash", None)
    body.pop("id", None)
    expect_id = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()[:16]
    if env["id"] != expect_id:
        return False, FORGED
    return True, VERIFIED


def chain_verify(lines, now_ts=None):
    """Сверить летопись целиком (JSONL): цепь хешей + монотонный seq по парам src→dst.
    История сверяется БЕЗ TTL — записи прошлого не протухают, они запечатаны
    хеш-цепью; свежесть (TTL) обязана только входящему конверту при прививке.

    Летопись одна — писем двое: конверты ядра (v/src/dst/seq) и SDK-конверты
    пульса генома (type/id/source, волна ×3). Оба запечатаны одним каноном и
    одной цепью prev_hash → hash; сверкер читает обе схемы, seq-дисциплина
    (монотонность по парам src→dst) обязана только конвертам ядра.

    Первый конверт ссылается на GENESIS_HASH. Подмена любой середины ломает
    все хеши после неё — летопись tamper-evident, как Rekor/Trillian.
    Возвращает (ok, reason, n): n — число проверенных конвертов (обеих схем).
    """
    prev = GENESIS_HASH
    last_seq = {}
    n = 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            env = json.loads(raw)
        except json.JSONDecodeError:
            return False, "STRUCTURE", n
        if is_sdk_envelope(env):
            ok, reason = verify_sdk_envelope(env, prev)
            if not ok:
                return False, reason, n
            prev = env["hash"]
            n += 1
            continue
        ok, reason = verify_envelope(env, prev, check_ttl=False)
        if not ok:
            return False, reason, n
        pair = (env["src"], env["dst"])
        if pair in last_seq and env["seq"] <= last_seq[pair]:
            return False, "SEQ_STAGNANT", n
        last_seq[pair] = env["seq"]
        prev = env["hash"]
        n += 1
    return True, VERIFIED, n


def tail_hash(lines) -> str:
    """Хеш последнего живого конверта летописи (точка прививки следующего)."""
    prev = GENESIS_HASH
    for raw in lines:
        raw = raw.strip()
        if raw:
            prev = json.loads(raw)["hash"]
    return prev
