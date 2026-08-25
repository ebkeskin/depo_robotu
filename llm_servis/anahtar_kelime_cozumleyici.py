"""
anahtar_kelime_cozumleyici.py -- Sprint 6 "LLM'in kazanci" karsilastirmasi
icin BASIT bir kural/anahtar-kelime tabanli ayristirici.

LLM'e (komut_cozumleyici.py) alternatif olarak degil, ona KARSI OLCUM
YAPMAK icin yazildi -- ayni dogruluk_seti.json'a karsi kosturulup
dogruluk_olcum.py ile karsilastiriliyor. Bilerek "basit" tutuldu (duz
alt-dizi arama + birkac regex, es anlamli kelime sozlugu yok, sozdizimi
analizi yok) -- amac gercekci bir taban cizgisi olusturmak, LLM'i
yenebilecek kadar gelismis bir sistem yazmak degil.

Cikti bicimi komut_cozumleyici.py'nin LLM'den bekledigi "ham" JSON/dict
ile AYNI (tip/raf/kat/eylem/katlar/filtre/en_yakin) -- boylece
ham_dogrula() ile ayni sekilde Sorgu semasina dogrulanabiliyor.
"""

from __future__ import annotations

import re

RENK_KELIMELERI = {
    "kırmızı": "kirmizi",
    "yeşil": "yesil",
    "mavi": "mavi",
    "sarı": "sari",
    "karton": "karton",
}

BOYUT_KELIMELERI = {
    "büyük": "buyuk",
    "küçük": "kucuk",
    "orta": "orta",
}

# Sirali onemli: "tara" ailesi "git" ailesinden ONCE kontrol edilir --
# "B1'e git ve tara" gibi komutlarda tarama niyeti baskin olsun diye
# (komut_cozumleyici.py SISTEM_TALIMATI'ndaki ayni oncelik kuralinin
# BASIT bir taklidi -- gercek bir NIYET anlama degil, sabit kelime
# onceligi).
TARA_FIILLERI = ["tara", "incele", "bak"]
GIT_FIILLERI = ["git", "ilerle", "doğru", "yönel"]
ARAMA_FIILLERI = ["bul", "göster", "nerede"]

RAF_DESENI = re.compile(r"\b([ABCabc][123])\b")
KAT_BASAMAK_DESENI = re.compile(r"(\d)\s*\.")


def _renk_bul(metin_lower: str) -> str | None:
    for kelime, deger in RENK_KELIMELERI.items():
        if kelime in metin_lower:
            return deger
    return None


def _boyut_bul(metin_lower: str) -> str | None:
    for kelime, deger in BOYUT_KELIMELERI.items():
        if kelime in metin_lower:
            return deger
    return None


def anahtar_kelime_coz(komut_metni: str) -> dict:
    """Dogal dil komutunu basit anahtar-kelime kurallariyla 'ham' bir
    sozluge cevirir. Ayristiramazsa LLM'in kendi basarisizlik formatini
    taklit eder: {"tip": None, "hata": "..."}."""
    metin_lower = komut_metni.lower()
    raf_eslesme = RAF_DESENI.search(komut_metni)
    en_yakin = "en yakın" in metin_lower

    # 1) SAYIM: "kaç" kelimesi tek tetikleyici (bu kelime baska hicbir
    # sorgu tipinde beklenmiyor).
    if "kaç" in metin_lower:
        renk = _renk_bul(metin_lower)
        boyut = _boyut_bul(metin_lower)
        raf = raf_eslesme.group(1).upper() if raf_eslesme else None
        if renk is None and boyut is None and raf is None:
            return {"tip": None, "hata": "Sayim icin renk/boyut/raf filtresi bulunamadi."}
        return {
            "tip": "sayim",
            "filtre": {"renk": renk, "boyut": boyut, "raf": raf},
        }

    # 2) ADRES: raf kodu VE (tara/incele/bak veya git/ilerle/dogru/yonel)
    # fiillerinden biri birlikte gecmeli.
    if raf_eslesme:
        raf = raf_eslesme.group(1).upper()
        tara_var = any(kelime in metin_lower for kelime in TARA_FIILLERI)
        git_var = any(kelime in metin_lower for kelime in GIT_FIILLERI)
        if tara_var or git_var:
            basamaklar = [int(d) for d in KAT_BASAMAK_DESENI.findall(komut_metni)]
            basamaklar = [d for d in basamaklar if 1 <= d <= 3]
            if tara_var:
                return {
                    "tip": "adres",
                    "raf": raf,
                    "eylem": "tara",
                    "katlar": sorted(set(basamaklar)) or None,
                }
            return {
                "tip": "adres",
                "raf": raf,
                "eylem": "git",
                "kat": basamaklar[0] if basamaklar else None,
            }

    # 3) ARAMA: bul/goster/nerede fiillerinden biri gecmeli.
    if any(kelime in metin_lower for kelime in ARAMA_FIILLERI):
        renk = _renk_bul(metin_lower)
        boyut = _boyut_bul(metin_lower)
        raf = raf_eslesme.group(1).upper() if raf_eslesme else None
        if renk is None and boyut is None and raf is None:
            return {"tip": None, "hata": "Arama icin renk/boyut/raf filtresi bulunamadi."}
        return {
            "tip": "arama",
            "filtre": {"renk": renk, "boyut": boyut, "raf": raf},
            "en_yakin": en_yakin,
        }

    return {"tip": None, "hata": "Komut hicbir bilinen kalıba uymadi (anahtar-kelime ayristirici)."}
