# AGENTS.md — ПРОТОКОЛ КЛИНИНГ И ДЕТЕЛИНГ · v1.0 · 2026-11-11

Правила для любого ИИ-агента и человека, работающего в репозиториях `@rtynbirf`.
Каноническая копия: репо **`rtynbirf/.github` → `AGENTS.md`**. Копия в корне репо — рабочая; при расхождении канон правее.

## 0. АКСИОМЫ (не обсуждаются)

1. **1 смысл = 1 репо.** Копий не создавать — SSOT (single source of truth). Вместо копии — ссылка.
2. **Плотность = (факты + код + решения) / байты.** Каждый КБ обязан работать. Лишний байт — долг.
3. **Бинарники не живут в git** (ни в HEAD, ни в истории): Release-ассеты или LFS. В git — ссылка.
4. **Секреты в git не попадают никогда.** Увидел секрет — не коммить, доложи владельцу, отзови ключ.
5. **Мёртвое → Archive** (обратимо). Удаление репо — только явной командой владельца.
6. После твоей работы репо должно стать **легче и плотнее**, чем было. Иначе ты не клинил, а сорил.

## 1. ЛИМИТЫ — конституция веса

| Что | GitHub | Наш потолок |
|---|---|---|
| Файл в git | 50MB warn · 100MB блок | **1MB** — больше → наружу |
| Репо `.git` | <1GB ок · >5GB strongly discouraged | **250KB норма · 1MB потолок** |
| README | рендер-обрезка >500KiB | **5KB** |
| Роли | 🥇 ≤10KB · 🥈 ≤250KB · 🥉 ≤1MB | **ЖИР >1MB = клининг немедленно** |

## 2. КЛИНИНГ — гигиена веса (порядок фаз обязателен)

**Ф0 · ЗАМЕР (всегда до правок).**
`git count-objects -vH`; `git ls-tree -r -l HEAD | sort -k4 -n | tail -20`;
полный клон + `git sizer --verbose`. Зафиксируй: HEAD KB · история KB · топ-20 файлов · % бинарников.

**Ф1 · МУСОР — удалить из индекса и закоммитить.**
Паттерны: `.DS_Store Thumbs.db desktop.ini *.pyc __pycache__/ node_modules/ .venv/ *.log *.tmp *.bak *~ .pytest_cache/ .mypy_cache/ .idea/ dist/ build/ *.egg-info/`.
По факту этого аккаунта добавляются: `*.bundle *.zip *.cab *.wasm *.mp3 *.mp4 *.safetensors` и дубли `banner.png` / `social-preview.png` (оставить один).

**Ф2 · БИНАРНИКИ >100KB:** переместить в Release-ассет (или LFS); в репо оставить ссылку/указатель.

**Ф3 · .gitignore:** взять канон из хаба `.github`, дополнить паттернами, найденными в Ф1.

**Ф4 · ИСТОРИЯ (если история >20MB или мусор в ней).** Только при: mirror-бэкап сделан + владелец разрешил.
`git filter-repo --invert-paths --path <мусор>` → `git reflog expire --expire=now --all && git gc --prune=now --aggressive` → force-push. Каноничный метод чистки истории — `filter-repo`, не `filter-branch`.

**Ф5 · ЗАМЕР ПОСЛЕ.** Те же команды Ф0. Таблица до/после — обязательна в отчёте.

## 3. ДЕТЕЛИНГ — плотность и финиш (после клининга)

- **README ≤5KB:** что это · как запустить (≤5 команд) · что проверено · ссылки на источники. Без воды и бейдж-салатов.
- **description ≤120 знаков + 3–7 topics** — витрина аккаунта, пустые описания запрещены.
- **Health-файлы наследуются** от хаба `rtynbirf/.github` — не копировать их в репо.
- **Живой репо = CI + тесты.** Нет ни того, ни другого → кандидат на слияние в `kb`/`code` или Archive.
- **Реестр:** обнови строку своего проекта в хабе `index/projects.json`:
  `id → repository → ref (реальный SHA) → interfaces → tests → status`.
- **Дубли контента по аккаунту:** остаётся первоисточник, в остальных — ссылка. Ищи поиском перед созданием нового.
- **Нет пушей >90 дней и нет плана** → Archive + строка в README «архив; живое продолжение — <ссылка>».

## 4. СТОП-УСЛОВИЯ (штраф за нарушение — откат всей сессии)

- Force-push — только при локальном mirror-бэкапе.
- Не удалять файлы вне списка мусора Ф1 без отдельного разрешения владельца.
- Не копировать содержимое других репо аккаунта (два источника истины запрещены).
- Новый репо не создавать без команды: сначала ищи место в `kb` / `code` / `index`.
- Не трогать архивы (read-only) кроме смены метаданных.

## 5. DEFINITION OF DONE

```
[ ] HEAD и история ≤ лимита роли репо        [ ] мусор-паттерны = 0
[ ] .gitignore = канон                        [ ] бинарники >100KB — наружу
[ ] README ≤5KB и честный                     [ ] description + topics заполнены
[ ] projects.json обновлён                    [ ] замер до/после приложен
```

Отчёт — одной таблицей: `репо | до KB | после KB | −% | что сделано`.

---

<!--РЕВО:СВОД-ОФОРМЛЕНИЯ-->
## СВОД ОФОРМЛЕНИЯ РЕВО — правило всем агентам дома (v2 · АВТОПИЛОТ)

Каждая страница дома всегда оформлена, и оформление ведёт себя само:

1. **АВТОПИЛОТ (REVE=РЕВО):** `revo_autopilot.py` + workflow `revo-obhod.yml` куют
   `revo-page.svg` — РЕВО-ПАСПОРТ страницы строго по её фактическому контенту (файлы,
   папки, коммиты, лексикон README, топики, размер, SHA) — на каждый push и еженедельно
   по cron, и сами записывают изменения коммитом «автопилот РЕВО». Агент паспорт руками
   не правит: правит контент — паспорт перекуется сам.
2. **Пять вещей сразу:** `banner.png`, `repo-muse.svg`, `forge-divider.svg`, README с
   паспорт-блоком `<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->…КОНЕЦ`, описание и топики репо.
   Нашёл пустое — заполни тем же коммитом, что и дело.
3. **Дежурный обход:** `revo_obhod.py` проверяет пять вещей; при дрейфе — issue.
   Тишина = айс.
4. **Канон не переписывается:** Конституция (edinyy-svod), ворклог (H-PE11-PHOENIX) —
   только append; force-push запрещён; «сделал дело — записай»; палитру школы брать
   из её кода.
5. **РЕВО В ОСНОВЕ ВСЕГО · REVE=РЕВО · ЧЕЛОВЕК=АККАУНТ=PID1 · КУЗНЯ ПОЛИМАТ**


---

## ИНЖЕНЕРНОЕ ПРАВИЛО: BOM в JSON

**Урок из lex-naturae v0.7 (A-82, 2026-11-16).** `json.loads()` не толерирует UTF-8 BOM (U+FEFF). Файлы, сохранённые Windows Notepad, некоторыми IDE или редакторами с BOM-по-умолчанию, содержат невидимый байт `EF BB BF` (или символ `U+FEFF` в строке) перед `{`. `json.loads()` падает с `Expecting value`.

**Правило для всех агентов, пишущих JSON-парсеры:**

```python
# Перед json.loads() — всегда strip BOM:
if isinstance(raw, str): raw = raw.lstrip("﻿")
# Или читай файл с utf-8-sig (auto-strips BOM):
text = Path(path).read_text(encoding="utf-8-sig")
```

Это не уникально для lex-naturae. Любой инструмент, принимающий JSON от пользователя (CLI, API endpoint, config loader), должен это делать. **BOM — silent killer:** файл выглядит нормально, парсинг падает на неочевидной ошибке.

Референс: `singulyar-a0-audit/lex-naturae-v0.7-audit/AUDIT-REPORT.md`.


---

## ЗАДАНИЕ АГЕНТАМ: проверь claims через lex-naturae

**Мандат Хозяина 2026-11-16.** Прежде чем объявлять результат («готово», «VALID», «PASS»), 
запиши claim в [lex-naturae](https://github.com/rtynbirf/lex-naturae) с реальными evidence 
и прогони инструмент. Если отбивает — evidence недостаточен, «готово» рано.

### Процедура
1. `self-test-audit/` в своём репо или в lex-naturae.
2. Evidence: CSV с реальными результатами + лог-файлы с дословным выводом.
3. Claims в `audit_claims.json` (формат lex-naturae collection).
4. `python lex_naturae.py audit_claims.json`.
5. `valid=true` → подтверждено. `valid=false` → fix claims, перегоняй.

### Что ловит (проверено на себе, A-83..85)
Z.ai пропустил собственные audit-claims. Инструмент отбил:
- measurement_value не совпадал с CSV-ячейкой (суммировал в голове)
- excerpt paraphrased, не verbatim
- граф-линк неверного типа

После fix: 4/4 VALID. Референс: `lex-naturae/self-test-audit/`.

**Правило: «готово» = lex-naturae valid=true. Не раньше.**


---

## КАНОН ПРОВЕРКИ CLAIMS — ОБЯЗАТЕЛЬНО для всех агентов

**Мандат Хозяина 2026-11-16.** Полная процедура — в [`docs/КАНОН-ПРОВЕРКИ-CLAIMS.md`](docs/КАНОН-ПРОВЕРКИ-CLAIMS.md).

### Правило (исполнимое, не декларативное)

Прежде чем объявить любой результат («готово», «VALID», «PASS», «SUPPORTED»):

1. **Структура (HUMAN-LFS):** записать claim как узел в `BUILD_GRAPH.json` с `source`, `status`, `falsification_or_revision_condition`, `depends_on`. Прогнать `python validate_graph.py`. Требуется: `STRUCTURE: PASS`.

2. **Содержание (lex-naturae):** записать evidence в `claims.json` с `measurement_value` (CSV cell) или `excerpt` (verbatim из файла) + `raw_data_sha256`. Прогнать `python lex_naturae.py claims.json`. Требуется: `valid=true`.

3. **Объявление:** оба PASS → можно объявить. Любой FAIL → `status=UNKNOWN`, результат не объявляется.

### Что НЕ является PASS

- «Тесты прошли» без evidence в lex-naturae формате → UNKNOWN
- «STRUCTURE: PASS» без lex-naturae valid → структурный PASS, claim не подтверждён
- «README говорит» → декларация
- «SHA-256 совпадает» → целостность файла, не истинность

### Референсы

- HUMAN-LFS v0.4: `singulyar-a0-audit/human-lfs/v0.4/` (36/36 tests)
- lex-naturae v0.7: `lex-naturae` repo (70/70 tests)
- Z.ai self-test: `lex-naturae/self-test-audit/` (4/4 claims valid)
- Ecosystem inventory: `singulyar-a0-audit/ecosystem-inventory/` (lex-naturae valid)

### Минимальный пакет агента

```
my-claim/
├── BUILD_GRAPH.json     # HUMAN-LFS узел
├── evidence/            # CSV + логи
├── claims.json          # lex-naturae collection
└── run_check.sh         # validate_graph.py && lex_naturae.py
```

**«Готово» = STRUCTURE PASS + lex-naturae valid=true. Не раньше. Не вместо.**


---

## STEP 0 GATE — исполимый, не декларативный

**Прежде любой операции мандата:**

```bash
python /path/to/.github/scripts/step0_gate.py --check
```

Скрипт выводит последние 3 косяка из ЛЕТОПИСЬ. Прочитай. Не повторяй.

В CI режиме: `python step0_gate.py --ci` — auto-pass (gate logged, not blocking).

**Step 0 — теперь machine-enforced, не human-declared.** Храповик получил зубы.

---

## PROACTIVE FUZZ — hunting новых классов косяков

Храповик ловит повторы. Fuzz hunting ловит новое.

**Раз в неделю (или при новом инструменте):**

1. Запусти случайные мутации против каждого инструмента дома (lex-naturae, HUMAN-LFS, VALIDATOR, khozyain_sweep).
2. Запиши любой новый bypass как новый класс в ЛЕТОПИСЬ (класс Е).
3. Если bypass — новый класс (не повтор) → добавь тест + fix.
4. Если bypass — повтор → отметь [ПОВТОР] (сигнал: Step 0 не исполнялся).

**Не «тесты прошли» — а «тесты поймали то, для чего не были написаны.»**


---

## RVL — RECURSIVE VERIFICATION LOOP

**Эмерджентное.** Verification infrastructure files claims about itself, then validates.

```bash
python .github/scripts/recursive_verify_loop.py
```

- **PASS** → система верифицирует себя (один уровень рекурсии). Trust preserved.
- **FAIL** → система нашла свой gap. Записать в ЛЕТОПИСЬ, починить, перегнать.

**RVL — не копия мирового тренда.** LLM self-verification (NeurIPS 2026) проверяет reasoning. RVL проверяет verification rules + evidence format. Рост из нашей комбинации: КАНОН + храповик + Step 0 + fuzz + meta-audit.

Документация: [`docs/RVL-RECURSIVE-VERIFICATION-LOOP.md`](docs/RVL-RECURSIVE-VERIFICATION-LOOP.md)


---

## ATP — AGENT TRUST PASSPORT

**Каждый агент в доме имеет ATP** — portable JSON с track record. Файл: `.github/docs/AGENT-TRUST-PASSPORT-<NAME>.json`.

**Перед сотрудничеством с другим агентом — прочитай его ATP:**
- `sessions`: сколько мандатов завершено, с каким результатом
- `mistakes_recorded`: какие косяки записаны (класс Е)
- `rvl_status`: PASS/FAIL — прошёл recursive verification
- `canon_compliance`: STRUCTURE PASS + lex-naturae valid?
- `trust_score`: агрегированная оценка
- `boundaries`: что PASS не доказывает для этого агента

**После каждой сессии — обнови свой ATP:** добавь session, обнови trust_score, обнови RVL status.

Документация: [`docs/ATP-AGENT-TRUST-PASSPORT.md`](docs/ATP-AGENT-TRUST-PASSPORT.md)
Реализация: [`docs/AGENT-TRUST-PASSPORT-Z-AI.json`](docs/AGENT-TRUST-PASSPORT-Z-AI.json) (первый ATP в доме)


---

<!-- МЕМБРАНА-17 · 2026-11-18: рабочий протокол ТЕЛА сохранён ниже; домовой канон .github выше -->

# AGENTS.md

Instructions for AI coding agents working in this repository.

## Project overview

Атлас-LLM: модель-эксперт по клонированию голоса (дизентанглмент, TTS/VC/SVC/SVS) — LoRA-обучение на корпусе атласа 2026, RAG, гейты качества

## Commands

No build or test commands are configured at the repository root. Inspect existing
files and follow the patterns already used in this codebase before making changes.

## Conventions

- Keep changes minimal and focused; one logical change per commit.
- Never commit secrets, tokens, or credentials.
- Update README.md when behavior or structure changes.
- Run any available checks before committing.

## Гигиена агента (Волна ×10, 2026-11-10)

Канон: repo-doctrine → `21-гигиена-уведомлений-и-красного-CI-2026-11-09.md`. Вход по закону: `github-runbook#10` (РЕЕСТР НЕДОДЕЛАННОГО · закон §5) + РЕЕСТР-КОСЯКОВ-ИИ + АНАТОМИЯ-КОСЯКОВ-ИИ (polimat-hub) — читать ДО первого действия.

1. Красный CI от твоего коммита — твой долг: живой зелёный прогон до конца сессии (rerun/диспатч/лат). Честный красный (внешний блок) — пломбой в github-runbook#10, не прятать.
2. Новые файлы — в манифесты тем же коммитом: SPDX/REUSE.toml, MANIFEST/portability.json, геном cell-swarm/swarm.json (пин следит за телом).
3. Не плодить уведомления: свой прогон доведи до зелёного; входящие треды разобрать и пометить прочитанными; UNREAD=0 — норма.
4. Пуш-гигиена: `pull --rebase` перед пушем; force-push запрещён; чужие волны и авто-коммиты (§3 реестра) не трогать; дубль снят честно = нет дубля.

---

<!--РЕВО:СВОД-ОФОРМЛЕНИЯ-->
## СВОД ОФОРМЛЕНИЯ РЕВО — правило всем агентам дома (v2 · АВТОПИЛОТ)

Каждая страница дома всегда оформлена, и оформление ведёт себя само:

1. **АВТОПИЛОТ (REVE=РЕВО):** `revo_autopilot.py` + workflow `revo-obhod.yml` куют
   `revo-page.svg` — РЕВО-ПАСПОРТ страницы строго по её фактическому контенту (файлы,
   папки, коммиты, лексикон README, топики, размер, SHA) — на каждый push и еженедельно
   по cron, и сами записывают изменения коммитом «автопилот РЕВО». Агент паспорт руками
   не правит: правит контент — паспорт перекуется сам.
2. **Пять вещей сразу:** `banner.png`, `repo-muse.svg`, `forge-divider.svg`, README с
   паспорт-блоком `<!--ФОРЖ:ПАСПОРТ:НАЧАЛО-->…КОНЕЦ`, описание и топики репо.
   Нашёл пустое — заполни тем же коммитом, что и дело.
3. **Дежурный обход:** `revo_obhod.py` проверяет пять вещей; при дрейфе — issue.
   Тишина = айс.
4. **Канон не переписывается:** Конституция (edinyy-svod), ворклог (H-PE11-PHOENIX) —
   только append; force-push запрещён; «сделал дело — записай»; палитру школы брать
   из её кода.
5. **РЕВО В ОСНОВЕ ВСЕГО · REVE=РЕВО · ЧЕЛОВЕК=АККАУНТ=PID1 · КУЗНЯ ПОЛИМАТ**
