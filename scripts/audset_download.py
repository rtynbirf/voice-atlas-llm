#!/usr/bin/env python3
# Скачивание mp3 с CDN audset.ru: URL берутся из сохранённых HTML страниц треков (честный провенанс).
import re, glob, urllib.parse, subprocess, os, hashlib, json

OUT = "/home/z/my-project/ruvson_audset"
os.makedirs(OUT, exist_ok=True)

# (track_id, локальное имя) — ключевые для верификации и новых треков
WANT = {
    "45934270": "03_Gde_nastoyashchee_audset45934270.mp3",       # полная версия нашей битой 03
    "46682880": "07x_Neigrayvlyubov_Remix_audset46682880.mp3",   # кандидат на наш 07 (Δ2с)
    "45283972": "krik_249_audset45283972.mp3",                    # «Крик в тишине» 2:49
    "46682881": "new_To_o_chyom_molchim_audset46682881.mp3",      # новый трек
    "46682882": "new_Eto_ne_sekret_audset46682882.mp3",           # новый трек
    "46344685": "01x_Kudaleyatgoda_audset46344685.mp3",           # кросс-проверка с нашим 01
    "46344684": "05x_Krik_342_audset46344684.mp3",                # кросс-проверка с нашим 05
}

results = []
for f in sorted(glob.glob("/home/z/my-project/scripts/audset_track_*.html")):
    tid = f.split("_")[-1].replace(".html", "")
    if tid not in WANT:
        continue
    h = open(f, encoding="utf-8", errors="replace").read()
    m = re.search(r"<title>(.*?)</title>", h, re.S)
    title = m.group(1).strip() if m else "?"
    urls = sorted(set(re.findall(r"https://wave\d\.audset\.ru/[^\"\\s<>]+", h)))
    if not urls:
        print(f"[SKIP] {tid}: нет CDN-ссылки"); continue
    url = urllib.parse.quote(urls[0], safe=":/")
    dst = os.path.join(OUT, WANT[tid])
    r = subprocess.run(["curl", "-s", "-m", "120", "-A", "Mozilla/5.0", "-o", dst, url])
    if r.returncode != 0 or not os.path.exists(dst) or os.path.getsize(dst) < 10000:
        print(f"[FAIL] {tid} {title[:50]}"); continue
    sha = hashlib.sha256(open(dst, "rb").read()).hexdigest()
    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,bit_rate",
                         "-show_entries", "stream=codec_name,sample_rate,channels",
                         "-of", "json", dst], capture_output=True, text=True)
    meta = json.loads(pr.stdout)
    fmt = meta.get("format", {})
    st = (meta.get("streams") or [{}])[0]
    dur = float(fmt.get("duration", 0))
    print(f"[OK] {WANT[tid]}")
    print(f"     title: {title[:80]}")
    print(f"     size={os.path.getsize(dst)} sha256={sha[:16]}… codec={st.get('codec_name')} "
          f"{st.get('sample_rate')}Hz {st.get('channels')}ch dur={dur:.2f}s br={fmt.get('bit_rate')}")
    results.append({"track_id": tid, "file": WANT[tid], "title": title, "url": url,
                    "size": os.path.getsize(dst), "sha256": sha, "duration_sec": round(dur, 2),
                    "codec": st.get("codec_name"), "sample_rate": st.get("sample_rate"),
                    "channels": st.get("channels"), "bit_rate": fmt.get("bit_rate")})

json.dump(results, open("/home/z/my-project/ruvson_audset/audset_download_manifest.json", "w"),
          ensure_ascii=False, indent=1)
print(f"\nитого: {len(results)} файлов, манифест audset_download_manifest.json")
