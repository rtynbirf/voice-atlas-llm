RUVSON voice — 20 языков (тембр × топ-20 языков мира)
============================================================

Пайплайн: нейтральный TTS -> OpenVoice V2 ToneColorConverter
Референс тембра: вокал трека 01 «Куда летят года» (htdemucs stem).
Первый (русский) образец: релиз voice-result-20261027.

Файлы 01–20 — клипы 10–15 c в тембре RUVSON.
raw/ — речь ДО конверсии тембра (нейтральный TTS) для сравнения A/B.
mp3/ — сжатые версии для телефона.
preview_all_languages.mp3 — всё подряд с русскими анонсами («Первый язык — английский»).
report_20langs.json — движок, длительности, SE-cosine, sha256 каждого файла.

Движки по языкам:
  01. английский — piper (en_US-lessac-medium), 13.01 c, SE-cosine к референсу 0.6432
  02. китайский (мандарин) — piper (zh_CN-huayan-medium), 13.84 c, SE-cosine к референсу 0.6796
  03. хинди — edge (hi-IN-SwaraNeural), 15.0 c, SE-cosine к референсу 0.7674
  04. испанский — piper (es_MX-ald-medium), 15.13 c, SE-cosine к референсу 0.623
  05. французский — piper (fr_FR-siwis-medium), 13.62 c, SE-cosine к референсу 0.7154
  06. арабский — piper (ar_JO-kareem-medium), 15.0 c, SE-cosine к референсу 0.7528
  07. бенгальский — edge (bn-BD-NabanitaNeural), 14.98 c, SE-cosine к референсу 0.8051
  08. португальский — edge (pt-BR-AntonioNeural), 13.97 c, SE-cosine к референсу 0.78
  09. русский — piper (ru_RU-irina-medium), 14.93 c, SE-cosine к референсу 0.7973
  10. урду — edge (ur-PK-AsadNeural), 15.07 c, SE-cosine к референсу 0.803
  11. индонезийский — edge (id-ID-ArdiNeural), 14.06 c, SE-cosine к референсу 0.8292
  12. немецкий — piper (de_DE-thorsten-medium), 12.57 c, SE-cosine к референсу 0.7297
  13. японский — edge (ja-JP-KeitaNeural), 15.0 c, SE-cosine к референсу 0.8265
  14. маратхи — edge (mr-IN-ManoharNeural), 15.0 c, SE-cosine к референсу 0.7529
  15. телугу — edge (te-IN-MohanNeural), 15.0 c, SE-cosine к референсу 0.8019
  16. турецкий — piper (tr_TR-dfki-medium), 14.15 c, SE-cosine к референсу 0.739
  17. тамильский — edge (ta-IN-ValluvarNeural), 15.0 c, SE-cosine к референсу 0.8631
  18. вьетнамский — piper (vi_VN-vais1000-medium), 10.43 c, SE-cosine к референсу 0.6623
  19. корейский — edge (ko-KR-InJoonNeural), 15.0 c, SE-cosine к референсу 0.9026
  20. суахили — piper (sw_CD-lanfrica-medium), 15.0 c, SE-cosine к референсу 0.7248

Честные оговорки:
  переносится ТОЛЬКО тембр (спектральная огибающая); высота тона и интонация наследуются от базового TTS-голоса каждого языка; арабский — модель kareem (иорданский арабский), текст — MSA; испанский — латиноамериканский (es_MX); суахили включён по прямому запросу владельца (в Ethnologue top-20 вместо него кантонский юэ); демо-тексты написаны ассистентом, не носителем (возможны шероховатости в ta/te/mr/bn/ur); прослушивание в песочнице невозможно — вердикт по уху за владельцем; метрики — прокси (SE-энкодер OpenVoice), WER по 20 языкам не считался: whisper-small для te/ta/sw/bn ненадёжен.
