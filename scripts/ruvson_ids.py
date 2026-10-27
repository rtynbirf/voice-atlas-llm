#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Извлечение (file_id, имя) из HTML-страницы публичной папки Google Drive.
ID и имена лежат в рядом стоящих строках встроенного JSON; парсим по позициям:
каждому имени файла ставим ближайший ID СЛЕВА."""
import json
import re
import sys
import urllib.request
from pathlib import Path

FOLDER_URL = ("https://drive.google.com/drive/folders/"
              "1OOmSuhm82Xkk-CllRnB1D5Lhcl6pazRN?usp=sharing")
OUT = "/home/z/my-project/voice_data_raw/ruvson_files.json"

ID_RE = re.compile(r'"([A-Za-z0-9_-]{25,44})"')
NAME_RE = re.compile(r'"(\d{2}\. [^"\n]{0,200}?\.(?:mp3|mp4))"')


def main() -> int:
    req = urllib.request.Request(FOLDER_URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    print(f"html: {len(html)} байт")

    ids = [(m.start(), m.group(1)) for m in ID_RE.finditer(html)]
    names = [(m.start(), m.group(1)) for m in NAME_RE.finditer(html)]
    print(f"кандидатов id: {len(ids)}, имён: {len(names)}")

    files = {}
    for pos, name in names:
        left = [i for p, i in ids if p < pos]
        if not left:
            continue
        fid = left[-1]
        files[fid] = name  # последний ID перед именем

    print(f"уникальных файлов с ID: {len(files)}")
    Path(OUT).write_text(json.dumps(files, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    for fid, name in sorted(files.items(), key=lambda kv: kv[1]):
        print(f"  {fid}  {name}")
    return 0 if files else 1


if __name__ == "__main__":
    sys.exit(main())
