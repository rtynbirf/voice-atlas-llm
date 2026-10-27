// Task 18: перевод строфы на 19 языков — ДОЗАПИСЬ с чекпоинтом, бэкофф на 429
// Запуск: node /home/z/my-project/scripts/sing_translate.mjs (можно перезапускать)
import ZAI from 'z-ai-web-dev-sdk';
import fs from 'fs';

const OUT = '/home/z/my-project/download/ruvson_singing_20langs/work/translations.json';
const SRC = { line1: 'И вот однажды в тишине,', line2: 'Поймёшь ты всё наедине' };
const LANGS = [
  ['en', 'English'], ['zh', 'Mandarin Chinese (Simplified, 普通话)'], ['hi', 'Hindi (हिन्दी)'],
  ['es', 'Spanish'], ['fr', 'French'], ['ar', 'Arabic (Modern Standard)'],
  ['bn', 'Bengali (বাংলা)'], ['pt', 'Portuguese (Brazilian)'], ['ur', 'Urdu (اردو)'],
  ['id', 'Indonesian (Bahasa Indonesia)'], ['ja', 'Japanese (日本語)'],
  ['de', 'German (Deutsch)'], ['mr', 'Marathi (मराठी)'], ['te', 'Telugu (తెలుగు)'],
  ['ta', 'Tamil (தமிழ்)'], ['tr', 'Turkish (Türkçe)'], ['vi', 'Vietnamese (Tiếng Việt)'],
  ['ko', 'Korean (한국어)'], ['sw', 'Swahili (Kiswahili)'],
];
const sleep = ms => new Promise(r => setTimeout(r, ms));

function loadDB() {
  try {
    const db = JSON.parse(fs.readFileSync(OUT, 'utf-8'));
    for (const k of Object.keys(db)) if (k.startsWith('_')) delete db[k];
    return db;
  } catch { return {}; }
}
function saveDB(db) {
  db._provenance = {
    source: SRC, method: 'z-ai-web-dev-sdk chat completions (LLM), машинный перевод, построчный',
    date: '2026-10-27', note: 'переводы не вычитаны носителями — честная пометка',
  };
  fs.writeFileSync(OUT, JSON.stringify(db, null, 1), 'utf-8');
  delete db._provenance;
}
function extractJSON(text) {
  const m = (text || '').match(/\{[\s\S]*\}/);
  if (!m) return null;
  try { const j = JSON.parse(m[0]); return (typeof j.line1 === 'string' && typeof j.line2 === 'string') ? j : null; }
  catch { return null; }
}

const zai = await ZAI.create();
const db = loadDB();

for (const [code, name] of LANGS) {
  if (db[code]?.line1 && db[code]?.line2) { console.log(`${code}: уже есть — скип`); continue; }
  let done = false;
  for (let attempt = 1; attempt <= 5 && !done; attempt++) {
    try {
      const completion = await zai.chat.completions.create({
        messages: [{
          role: 'user',
          content:
`You translate song lyrics so they can be SUNG. Translate this two-line verse into ${name}.

Verse (Russian):
"${SRC.line1}"
"${SRC.line2}"

Requirements:
1. Singable: short words, open vowels at line ends, natural stress.
2. Keep meaning and mood (silence, solitude, sudden realization).
3. About 8-11 syllables per line.
4. Write ONLY in ${name} script (no transliteration, no Russian, no Latin unless the script is Latin).
5. Respond with STRICT JSON only: {"line1":"...","line2":"..."} — no explanations, no markdown.`,
        }],
        thinking: { type: 'disabled' },
      });
      const j = extractJSON(completion.choices[0]?.message?.content);
      if (j && j.line1.trim() && j.line2.trim()) {
        db[code] = { line1: j.line1.trim(), line2: j.line2.trim(), attempts: attempt };
        saveDB(db);
        console.log(`${code}: OK (попытка ${attempt}) ${j.line1} / ${j.line2}`);
        done = true;
      } else {
        console.log(`${code}: попытка ${attempt} — JSON битый`);
        await sleep(3000);
      }
    } catch (e) {
      const is429 = /429|Too many/i.test(e.message);
      const wait = is429 ? 20000 * attempt : 4000 * attempt;
      console.log(`${code}: попытка ${attempt} — ${e.message.slice(0, 80)}; жду ${wait / 1000}с`);
      await sleep(wait);
    }
  }
  if (!done) console.log(`${code}: FAIL после 5 попыток`);
  await sleep(6000); // межъязыковая пауза против рейт-лимита
}
const ok = Object.keys(loadDB()).length;
console.log(`\nИтог: ${ok}/19 языков в ${OUT}`);
