#!/usr/bin/env python3
"""
dogruluk_olcum.py -- Sprint 6 "sorgu ayristirma dogrulugu" ve "LLM'in
kazanci" olcumu.

Ayni etiketli komut setini (dogruluk_seti.json) hem gercek Gemini API
(komut_cozumleyici.sorgu_ayristir) hem de basit bir anahtar-kelime
ayristiricisi (anahtar_kelime_cozumleyici.anahtar_kelime_coz) ile
kosturup elle etiketlenmis referansla karsilastirir, yan yana bir
tablo uretir.

LLM yolunda envanter.json'a HIC BAKILMAZ (sorgu_ayristir kullanilir,
komut_coz DEGIL) -- olculen sey NIYET cikarma basarisi, envanterdeki
gercek kutu sayisi degil (ayni komut farkli envanterlerde farkli
eslesme sayisi verir, ama dogru sorgu ayni kalmali).

Rate limit onlemi: --bekleme (varsayilan 5s) her LLM cagrisi arasinda
bekler; LLMKotaHatasi/gecici sunucu hatasi (basarili=False, hata mesaji
"yogun"/"gecici" iceriyor) durumunda otomatik backoff ile (15s, 30s,
60s) 3 kez tekrar dener, hepsi tukenirse o soruyu HATA olarak isaretler
(YANLIS degil -- orani carpitmasin diye ayri sayilir).

Kullanim:
    python3 dogruluk_olcum.py                  # her iki yontem, varsayilan 5s bekleme
    python3 dogruluk_olcum.py --sadece anahtar_kelime   # hizli, API gerektirmez
    python3 dogruluk_olcum.py --bekleme 8
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # main.py disinda tek basina calistirildiginda GOOGLE_API_KEY icin sart

from anahtar_kelime_cozumleyici import anahtar_kelime_coz
from komut_cozumleyici import ham_dogrula, sorgu_ayristir

VERI_SETI_YOLU = Path(__file__).parent / "dogruluk_seti.json"
SONUC_YOLU = Path(__file__).parent / "dogruluk_sonuclari.json"

ALAN_ADLARI = ["tip", "raf", "kat", "eylem", "katlar", "en_yakin"]
FILTRE_ALANLARI = ["renk", "boyut", "raf"]
TUM_ALANLAR = ALAN_ADLARI + [f"filtre.{a}" for a in FILTRE_ALANLARI]

GECICI_HATA_ANAHTAR_KELIMELERI = ("yogun", "gecici")


def _sorgu_sozluge_cevir(sorgu) -> dict:
    if sorgu is None:
        return {"tip": None}
    return sorgu.model_dump()


def karsilastir(beklenen: dict, gercek: dict) -> tuple[bool, dict]:
    """Alan alan karsilastirir. Donen: (tam_eslesme, alan_sonuclari)."""
    sonuclar = {}
    for alan in ALAN_ADLARI:
        b, g = beklenen.get(alan), gercek.get(alan)
        if alan == "katlar" and b is not None and g is not None:
            sonuclar[alan] = sorted(b) == sorted(g)
        else:
            sonuclar[alan] = b == g

    beklenen_filtre = beklenen.get("filtre") or {}
    gercek_filtre = gercek.get("filtre") or {}
    for alan in FILTRE_ALANLARI:
        sonuclar[f"filtre.{alan}"] = beklenen_filtre.get(alan) == gercek_filtre.get(alan)

    return all(sonuclar.values()), sonuclar


def _gecici_hata_mi(sonuc) -> bool:
    return (not sonuc.basarili) and bool(sonuc.hata) and any(
        anahtar in sonuc.hata for anahtar in GECICI_HATA_ANAHTAR_KELIMELERI)


def _llm_ile_coz_backoff(metin: str, max_deneme: int = 3):
    backoff = [15, 30, 60]
    for deneme in range(max_deneme + 1):
        sonuc = sorgu_ayristir(metin)
        if not _gecici_hata_mi(sonuc):
            return sonuc
        if deneme < max_deneme:
            print(f"    (rate-limit/gecici hata, {backoff[deneme]}s bekleyip tekrar denenecek)")
            time.sleep(backoff[deneme])
    return sonuc


def yontem_kos(veri_seti: list[dict], yontem: str, bekleme: float) -> list[dict]:
    sonuclar = []
    for i, ornek in enumerate(veri_seti):
        metin, beklenen = ornek["komut"], ornek["beklenen"]

        if yontem == "llm":
            sonuc = _llm_ile_coz_backoff(metin)
            time.sleep(bekleme)
            if _gecici_hata_mi(sonuc):
                sonuclar.append({"durum": "HATA", "gercek": None, "alan_sonuclari": {}})
                print(f"  [{i + 1}/{len(veri_seti)}] HATA (rate-limit/gecici, atlandi): {metin!r}")
                continue
        else:
            ham = anahtar_kelime_coz(metin)
            sonuc = ham_dogrula(ham)

        gercek = _sorgu_sozluge_cevir(sonuc.sorgu) if sonuc.basarili else {"tip": None}
        tam_eslesme, alan_sonuclari = karsilastir(beklenen, gercek)
        durum = "DOGRU" if tam_eslesme else "YANLIS"
        sonuclar.append({"durum": durum, "gercek": gercek, "alan_sonuclari": alan_sonuclari})
        print(f"  [{i + 1}/{len(veri_seti)}] {durum}: {metin!r}")
        if not tam_eslesme:
            print(f"      beklenen: {beklenen}")
            print(f"      gercek  : {gercek}")

    return sonuclar


def _dogruluk(sonuclar: list[dict]) -> tuple[int, int]:
    gecerli = [s for s in sonuclar if s["durum"] != "HATA"]
    dogru = sum(1 for s in gecerli if s["durum"] == "DOGRU")
    return dogru, len(gecerli)


def _alan_dogrulugu(sonuclar: list[dict], alan: str) -> tuple[int, int]:
    ilgili = [s for s in sonuclar if s["durum"] != "HATA" and alan in s["alan_sonuclari"]]
    dogru = sum(1 for s in ilgili if s["alan_sonuclari"][alan])
    return dogru, len(ilgili)


def _tip_dogrulugu(veri_seti: list[dict], sonuclar: list[dict], tip: str) -> tuple[int, int]:
    ilgili = [(o, s) for o, s in zip(veri_seti, sonuclar)
              if o["beklenen"].get("tip") == tip and s["durum"] != "HATA"]
    dogru = sum(1 for _, s in ilgili if s["durum"] == "DOGRU")
    return dogru, len(ilgili)


def ozet_yazdir(veri_seti: list[dict], sonuc_seti: dict[str, list[dict]]) -> None:
    yontemler = list(sonuc_seti.keys())
    print("\n=== KARSILASTIRMA TABLOSU ===\n")

    baslik = f"{'Metrik':<28}" + "".join(f"{y:>18}" for y in yontemler)
    print(baslik)
    print("-" * len(baslik))

    for yontem in yontemler:
        hata = sum(1 for s in sonuc_seti[yontem] if s["durum"] == "HATA")
        if hata:
            print(f"({yontem}: {hata} ornek rate-limit/gecici hata nedeniyle atlandi)")

    dogru_satiri = f"{'TAM ESLESME DOGRULUGU':<28}"
    for yontem in yontemler:
        dogru, toplam = _dogruluk(sonuc_seti[yontem])
        dogru_satiri += f"{f'{dogru}/{toplam} (%{100 * dogru / toplam:.1f})':>18}"
    print(dogru_satiri)
    print()

    for tip in ["adres", "arama", "sayim"]:
        satir = f"{f'  tip={tip}':<28}"
        for yontem in yontemler:
            dogru, toplam = _tip_dogrulugu(veri_seti, sonuc_seti[yontem], tip)
            satir += f"{f'{dogru}/{toplam} (%{100 * dogru / toplam:.1f})' if toplam else 'n/a':>18}"
        print(satir)
    print()

    for alan in TUM_ALANLAR:
        satir = f"{f'  alan={alan}':<28}"
        for yontem in yontemler:
            dogru, toplam = _alan_dogrulugu(sonuc_seti[yontem], alan)
            satir += f"{f'{dogru}/{toplam} (%{100 * dogru / toplam:.1f})' if toplam else 'n/a':>18}"
        print(satir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sadece", choices=["llm", "anahtar_kelime"], default=None,
                     help="Sadece tek yontemi kostur (varsayilan: ikisi de)")
    ap.add_argument("--bekleme", type=float, default=5.0,
                     help="LLM cagrilari arasi bekleme, saniye (varsayilan 5)")
    args = ap.parse_args()

    with open(VERI_SETI_YOLU, encoding="utf-8") as f:
        veri_seti = json.load(f)

    yontemler = [args.sadece] if args.sadece else ["anahtar_kelime", "llm"]

    sonuc_seti = {}
    for yontem in yontemler:
        print(f"\n--- Yontem: {yontem} ({len(veri_seti)} komut) ---")
        sonuc_seti[yontem] = yontem_kos(veri_seti, yontem, args.bekleme)

    ozet_yazdir(veri_seti, sonuc_seti)

    with open(SONUC_YOLU, "w", encoding="utf-8") as f:
        json.dump({
            "veri_seti": veri_seti,
            "sonuclar": {
                yontem: [
                    {**o, **s} for o, s in zip(veri_seti, sonuc_seti[yontem])
                ]
                for yontem in yontemler
            },
        }, f, ensure_ascii=False, indent=2)
    print(f"\nDetayli sonuclar: {SONUC_YOLU}")


if __name__ == "__main__":
    main()
