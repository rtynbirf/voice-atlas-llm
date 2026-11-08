#!/bin/bash
# Task 18: загрузка singing-пакета в GitHub Release (канал Task 16).
set -e
REPO="rtynbirf/voice-atlas-llm"
TAG="singing-20langs-20261027"
ZIP="/home/z/my-project/download/RUVSON_singing_20langs.zip"
MP3="/home/z/my-project/download/ruvson_singing_20langs/preview_singing_all_languages.mp3"

cd /home/z/my-project/voice-atlas-llm
TOKEN=$(git remote get-url origin | sed -E 's#https://##; s#@github.com.*##; s#.*:##')
[ -n "$TOKEN" ] || { echo "NO_TOKEN"; exit 1; }

REL_JSON=$(curl -s -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/$REPO/releases/tags/$TAG")
REL_ID=$(echo "$REL_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
if [ -z "$REL_ID" ]; then
  echo "создаю release $TAG ..."
  BODY=$(python3 - <<'EOF'
import json
body = """RUVSON ПОЁТ СВОЮ СТРОФУ на 20 самых популярных языках мира.

Строфа из трека 01 «Where Do the Years Fly By» (103.8-112.2 c): «И вот однажды в тишине, / Поймёшь ты всё наедине» — текст подтверждён тремя независимыми транскрипциями (faster-whisper small: стем-окно, микс-окно, стем-контекст).

Как сделано: мелодия строфы снята (librosa.pyin + перекрёстная сверка Praat, медиана 246.8 Гц, с вибрато) -> переводы строфы на 19 языков (LLM, машинные, режим singable) -> TTS (piper 10 / edge-tts 9) -> растяжка до 8.4 с -> Praat PSOLA: высота тона заменена на ЕГО реальный F0-контур -> OpenVoice V2 (референс — вокал трека 01) -> аутро 2.5 с из реальной минусовки трека.

Измерено: перенос мелодии (Пирсон его контура и PSOLA-выхода) r=0.67..0.999, медиана 0.988; перенос тембра (SE-cosine к референсу) 0.73..0.89 (у Task 17 на речи 0.62..0.90); каждый клип 11.15 c = пение 8.4 c + аутро 2.5 c.

В архиве: 00_his_original_phrase_ru.wav (ЕГО настоящая строфа для A/B), клипы 01-20 (wav+mp3), preview_singing_all_languages.mp3 (все 20 с русскими анонсами), lyrics_translations.txt, README.txt, report_singing_20langs.json (все метрики и sha256).

Честно: артикуляция/ритм от TTS (мелодия ложится на слоги не 1-в-1); переводы машинные, не вычитаны носителями; PSOLA+конверсия — синтетика; вердикт по уху — за владельцем."""
print(json.dumps({"tag_name": "singing-20langs-20261027",
                  "target_commitish": "proven-recipes",
                  "name": "RUVSON поёт свою строфу на 20 языках (его мелодия, его тембр)",
                  "body": body}))
EOF
)
  REL_JSON=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$BODY" "https://api.github.com/repos/$REPO/releases")
  REL_ID=$(echo "$REL_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
fi
echo "release_id=$REL_ID"
[ -n "$REL_ID" ] || { echo "FAIL: нет id"; echo "$REL_JSON" | head -5; exit 1; }

UPLOADED=$(curl -s -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/$REPO/releases/$REL_ID/assets" | python3 -c "import json,sys; print(' '.join(a['name'] for a in json.load(sys.stdin)))")
echo "уже загружены: $UPLOADED"

upload () {
  local f="$1" ct="$2"
  local name; name=$(basename "$f")
  case " $UPLOADED " in *" $name "*) echo "$name уже есть, пропуск"; return;; esac
  echo "загрузка $name ..."
  curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: $ct" \
    --data-binary @"$f" \
    "https://uploads.github.com/repos/$REPO/releases/$REL_ID/assets?name=$name" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('->', d.get('name'), d.get('state'), d.get('size'))"
}
upload "$ZIP" "application/zip"
upload "$MP3" "audio/mpeg"
echo DONE
