"""
komut_cozumleyici.py -- Dogal dil komutu alir, LLM'e gonderir, donen
JSON'u dogrular ve GEREKIRSE envanter.json'a karsi belirsizlik kontrolu
yapar.

Tasarim ilkesi (PROJE_DOSYASI.md 1.4): Belirsizligi LLM cozer, kesinligi
veritabani saglar. Burada "kesinlik" adimi: LLM'in urettigi filtreyi
GERCEK envanter.json'daki kutularla eslestirip kac tane bulundugunu
SAYMAK. LLM'e "kac tane oldugunu tahmin et" dedirtilmiyor -- LLM sadece
niyeti (renk=kirmizi) cikariyor, sayma islemi kod tarafinda, veriye
bakarak yapiliyor.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from llm_saglayici import LLMHatasi, LLMKotaHatasi, LLMYanitHatasi, llm_cagir
from sorgu_semasi import Filtre, Sorgu, SorguSonucu, SorguTipi

logger = logging.getLogger("komut_cozumleyici")

SISTEM_TALIMATI = """\
Sen bir depo robotu icin dogal dil komutlarini yapilandirilmis JSON'a
ceviren bir ayristiricisin. SADECE JSON dondur, baska hicbir metin ekleme.

JSON semasi (alanlar arasinda TAM OLARAK bu adlari kullan):
{
  "tip": "adres" | "arama" | "sayim",
  "raf": "A1".."C3" (sadece tip=adres ise, yoksa null),
  "kat": 1 | 2 | 3 (tip=adres ve komutta belirli bir kat geciyorsa, yoksa null),
  "eylem": "git" | "tara" (SADECE tip=adres ise zorunlu, yoksa null),
  "katlar": [1,2] gibi bir liste (SADECE eylem=tara VE komutta belirli
             katlar sayiliyorsa, orn. "1. ve 2. katini tara"; komut tum
             rafi taramayi istiyorsa (orn. "tara", "ne var") null birak
             -- null, "her 3 kati da tara" demektir),
  "filtre": {"renk": "...", "boyut": "...", "raf": "..."} (tip=arama
             veya sayim ise, yoksa null. renk, boyut, raf'tan en az biri
             dolu olmali -- ucu de bos olamaz.)
}

eylem ayrimi (SADECE tip=adres icin gecerli, cok onemli):
- "git" -> komut SADECE robotu bir yere goturmek istiyor, kamerayi
  DONDURME, tarama YAPMA. Ornek: "A2'ye git", "B1'in 2. katina git".
- "tara" -> komut rafi/kati INCELEMEK istiyor (kutulari gormek/saymak
  icin). Ornek: "A2'yi tara", "A2'de ne var", "B1'in 1. ve 2. katina bak".
  "git" fiili gecse bile, "git ve bak/tara/incele/goster" gibi INCELEME
  niyeti varsa eylem="tara" olmali.

Gecerli renkler: kirmizi, yesil, mavi, sari, karton
Gecerli boyutlar: buyuk, orta, kucuk
Gecerli raflar: A1, A2, A3, B1, B2, B3, C1, C2, C3

Ornekler:
"A1'in 3. katina git" -> {"tip":"adres","raf":"A1","kat":3,"eylem":"git","katlar":null,"filtre":null}
"A2'ye git" -> {"tip":"adres","raf":"A2","kat":null,"eylem":"git","katlar":null,"filtre":null}
"A2'yi tara" -> {"tip":"adres","raf":"A2","kat":null,"eylem":"tara","katlar":null,"filtre":null}
"B1'in 1. ve 2. katini tara" -> {"tip":"adres","raf":"B1","kat":null,"eylem":"tara","katlar":[1,2],"filtre":null}
"Kirmizi kutuyu bul" -> {"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"kirmizi","boyut":null,"raf":null}}
"B2'deki kirmizi kutuyu bul" -> {"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"kirmizi","boyut":null,"raf":"B2"}}
"Kac yesil kutu var?" -> {"tip":"sayim","raf":null,"kat":null,"filtre":{"renk":"yesil","boyut":null,"raf":null}}
"Buyuk mavi kutu neredeydi?" -> {"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"mavi","boyut":"buyuk","raf":null}}

ONEMLI: Sen sadece NIYETI cikar (renk/boyut/raf/eylem/adres). Kac kutu
bulundugunu veya koordinat HESAPLAMA -- bu senin isin degil, sonradan
veritabaninda yapilacak. Komut semaya uymuyorsa veya depo robotuyla
ilgisizse su JSON'u don: {"tip": null, "hata": "kisa aciklama"}
"""

# Sprint 1'deki API anahtari sizinti olayindan sonra: bu dosya envanter
# yolunu sabit kodlamiyor, cagiran taraf (main.py) veriyor -- boylece
# test ortaminda farkli bir envanter.json ile kolayca test edilebilir.


def _envanter_yukle(envanter_yolu: Path) -> list[dict]:
    """envanter.json duz bir kutu listesi DEGIL -- ust seviyede
    raf_konumlari / kat_yuzeyleri / kutular anahtarlari var (bkz.
    kutu_uret.py ciktisi). Bize gereken sadece 'kutular' listesi."""
    with open(envanter_yolu, "r", encoding="utf-8") as f:
        veri = json.load(f)
    if isinstance(veri, list):
        return veri  # geriye donuk uyumluluk (eski/duz format icin)
    return veri.get("kutular", [])


def _filtreye_uyanlar(envanter: list[dict], filtre: Filtre) -> list[dict]:
    sonuc = []
    for kutu in envanter:
        if filtre.renk is not None and kutu.get("renk") != filtre.renk.value:
            continue
        if filtre.boyut is not None and kutu.get("boyut") != filtre.boyut.value:
            continue
        if filtre.raf is not None and kutu.get("raf") != filtre.raf:
            continue
        sonuc.append(kutu)
    return sonuc


def _llm_json_ayikla(ham_metin: str) -> dict:
    """Gemini response_mime_type=application/json ile cagrildigi icin
    normalde temiz JSON doner, ama saglayici degisirse (orn. markdown
    kod bloguyla saran bir model) diye savunmaci temizlik yapiyoruz."""
    metin = ham_metin.strip()
    if metin.startswith("```"):
        metin = metin.strip("`")
        if metin.startswith("json"):
            metin = metin[4:]
        metin = metin.strip()
    try:
        return json.loads(metin)
    except json.JSONDecodeError as e:
        raise LLMYanitHatasi(f"LLM gecerli JSON dondurmedi: {e}. Ham metin: {ham_metin[:200]!r}") from e


def komut_coz(komut_metni: str, envanter_yolu: Optional[Path] = None) -> SorguSonucu:
    """Ana giris noktasi. FastAPI endpoint'i bunu cagirir.

    Hata yonetimi burada tek yerde toplanir (Sprint 4 madde 6):
    - LLM ulasilamiyor / kota doldu -> basarili=False, hata dolu
    - LLM bozuk/anlamsiz JSON dondu -> basarili=False, hata dolu
    - Komut semaya uymuyor (LLM'in kendi "tip": null cikisi) -> basarili=False
    - Sorgu semaya uyuyor ama zorunlu alan eksik (orn. adres icin raf yok)
      -> basarili=False, pydantic/dogrula() mesaji hataya yazilir
    - arama/sayim + birden fazla eslesme -> belirsiz=True, kullaniciya sorulmali
    - arama + sifir eslesme -> basarili=False, "boyle bir kutu yok"
    """
    try:
        yanit = llm_cagir(SISTEM_TALIMATI, komut_metni)
    except LLMKotaHatasi as e:
        logger.warning("LLM kota hatasi: %s", e)
        return SorguSonucu(basarili=False, hata="Sistem su an yogun, birazdan tekrar deneyin.")
    except LLMHatasi as e:
        logger.error("LLM cagri hatasi: %s", e)
        return SorguSonucu(basarili=False, hata=f"Komut anlasilamadi (sistem hatasi): {e}")

    try:
        ham = _llm_json_ayikla(yanit.metin)
    except LLMYanitHatasi as e:
        logger.error("JSON ayiklama hatasi: %s", e)
        return SorguSonucu(basarili=False, hata="Komut anlasilamadi, lutfen farkli ifade edin.")

    if ham.get("tip") is None:
        return SorguSonucu(
            basarili=False,
            hata=ham.get("hata", "Komut depo robotu gorevleriyle eslesmedi."),
        )

    try:
        sorgu = Sorgu.model_validate(ham)
        sorgu.dogrula()
    except (ValidationError, ValueError) as e:
        logger.info("Sorgu dogrulama hatasi: %s (ham=%s)", e, ham)
        return SorguSonucu(basarili=False, hata=f"Komut eksik/tutarsiz: {e}")

    if sorgu.tip == SorguTipi.ADRES:
        # Koordinata cevirme burada YAPILMAZ -- adres_veritabani.json /
        # tarama_pozisyonlari.json okuma islemi navigasyon katmaninin isi.
        return SorguSonucu(basarili=True, sorgu=sorgu)

    # arama / sayim: envanter.json'a karsi GERCEK sayim yapiliyor
    if envanter_yolu is None:
        return SorguSonucu(basarili=False, hata="Envanter yolu belirtilmedi.")
    try:
        envanter = _envanter_yukle(envanter_yolu)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Envanter okunamadi: %s", e)
        return SorguSonucu(basarili=False, hata="Envanter verisi okunamadi.")

    eslesenler = _filtreye_uyanlar(envanter, sorgu.filtre)

    if sorgu.tip == SorguTipi.SAYIM:
        return SorguSonucu(basarili=True, sorgu=sorgu, eslesme_sayisi=len(eslesenler))

    # sorgu.tip == ARAMA
    if len(eslesenler) == 0:
        return SorguSonucu(basarili=False, hata="Bu ozelliklerde bir kutu bulunamadi.")
    if len(eslesenler) == 1:
        return SorguSonucu(
            basarili=True, sorgu=sorgu, eslesme_sayisi=1, eslesmeler=eslesenler
        )
    # Birden fazla eslesme: LLM'e degil kullaniciya soruluyor (tasarim ilkesi)
    return SorguSonucu(
        basarili=True,
        sorgu=sorgu,
        belirsiz=True,
        eslesme_sayisi=len(eslesenler),
        eslesmeler=eslesenler,
    )
