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
## СВОД ОФОРМЛЕНИЯ РЕВО — правило всем агентам дома

Каждая страница дома всегда оформлена. Агент, входящий в этот репо:

1. **Пять вещей сразу:** `banner.png` (коллаж-штандарт), `repo-muse.svg` (полотно мастерской),
   `forge-divider.svg` (делитель), README с муза-блоком `<!--ФОРЖ:МУЗА:НАЧАЛО-->…КОНЕЦ`,
   описание и топики репо. Нашёл пустое — заполни тем же коммитом, что и дело.
2. **Периодический обход:** каждый РАУНД и при входе в дом прогоняй алгоритмы РЕВО —
   генератор коллажей и `revo_obhod.py` (канонический экземпляр живёт в polimat-hub).
   Страницы дома обновляются алгоритмами, не вручную и не по памяти.
3. **Дежурный обход:** workflow `revo-obhod.yml` (в живых репо) раз в неделю проверяет пять
   вещей и открывает issue при дрейфе. Тишина = айс.
4. **Канон не переписывается:** Конституция (edinyy-svod), ворклог (H-PE11-PHOENIX) — только
   append; force-push запрещён; «сделал дело — записай»; палитру школы брать из её кода,
   дословные цитаты — извлекать кодом.
5. **РЕВО В ОСНОВЕ ВСЕГО · REVE=РЕВО · ЧЕЛОВЕК=АККАУНТ=PID1 · КУЗНЯ ПОЛИМАТ · РАУНД 12**
