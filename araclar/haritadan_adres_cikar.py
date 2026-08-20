#!/usr/bin/env python3
"""
adres_veritabani.json'daki raf durma noktalarini SLAM haritasindan
(maps/depo_haritasi.pgm) GORUNTU ISLEME ile dogrudan cikarir - elle
surup olcmeye (konum_yakala.py) veya 2 noktadan rijit donusum
kestirmeye (iki_nokta_kalibrasyon.py) gerek kalmadan.

NEDEN: iki_nokta_kalibrasyon.py tek bir rijit (rotasyon+oteleme)
donusum varsayiyordu, ama SLAM haritasi mukemmel rijit degil - raf
basina olculen donukluk 0deg-2.9deg arasinda degisiyor (bkz. gecmis
SLAM kalite analizi). Bu yuzden A1/C3'e yakin raflarda (orn. B2) iyi
sonuc verirken, uzak koselerde (A3) rota tamamen yanlis cikti (bkz.
NOTLAR.md/PROJE_DOSYASI.md ilgili teshis). Bu script her rafi KENDI
yerel SLAM verisinden okuyarak bu sorunu ortadan kaldirir.

YONTEM:
1. PGM'de dolu (siyah, deger<100) pikselleri bul, findContours ile
   9 raf-boyutlu blob'u disari (dis duvar - kapi bosluğundan dolayi
   kapanmayan bir dongu, cok buyuk bounding box ama kucuk shoelace
   alani) ayikla.
2. Her konturun minAreaRect kose noktalarini (px) dogrudan map-frame
   metreye cevir (bkz. asagidaki piksel_to_harita - PGM satiri TERS,
   ROS map_server konvansiyonu). Acinin isaretini/konvansiyonunu
   TAHMIN ETMEK yerine, donusturulmus GERCEK kose noktalarindan uzun
   kenar vektorunu hesaplayip normal yonunu oradan cikariyoruz - boylece
   OpenCV'nin minAreaRect aci konvansiyonu (surum bagimli, w/h yer
   degistirebilir) hicbir onem tasimiyor.
3. 9 merkezi y'ye gore 3 sira (A/B/C, en yuksek y = A - bkz. A1/C3
   fiziksel olcumuyle capraz dogrulama), her sirada x'e gore 3 sutuna
   (1/2/3) ayirir.
4. yon (guney/kuzey) tablosuna gore raf onunden 0.4m (yari derinlik) +
   1.6m (koridor payi) geri cekilerek durma noktasi hesaplanir; yaw
   raf normalinin GERCEK olculen yonune gore (kucuk donukluk dahil).

Kullanim:
  python3 haritadan_adres_cikar.py                 # onizle, yazma
  python3 haritadan_adres_cikar.py --uygula         # veritabanina yaz + PNG uret
"""

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
import yaml

from depo_robotu.adres_veritabani_araclari import girdi_guncelle, veritabani_oku

BU_DIZIN = Path(__file__).resolve().parent
HARITA_YAML = BU_DIZIN.parent / 'maps' / 'depo_haritasi.yaml'
PNG_CIKTI = BU_DIZIN / 'harita_analiz_sonucu.png'

ESIK = 100          # bu deger altindaki piksel = dolu (harita tamamen trinary: 0/205/254)
MIN_ALAN = 400       # px^2 - gurultu benek/kucuk artefaktlari ele
MAX_BBOX_PX = 100    # bundan buyuk bounding box = dis duvar artefakti, raf degil

RAF_YARI_DERINLIK = 0.4   # m - kutu_uret.py RAF_DERINLIK=0.8'in yarisi
KORIDOR_PAYI = 1.6        # m - onceki adres_veritabani.json hesap_yontemi ile ayni


def harita_meta_oku():
    with open(HARITA_YAML) as f:
        meta = yaml.safe_load(f)
    pgm_yolu = HARITA_YAML.parent / meta['image']
    return pgm_yolu, meta['resolution'], meta['origin']


def piksel_to_harita(px, py, res, origin, yukseklik_px):
    ox, oy = origin[0], origin[1]
    x = ox + px * res
    y = oy + (yukseklik_px - py) * res
    return x, y


def harita_to_piksel(x, y, res, origin, yukseklik_px):
    ox, oy = origin[0], origin[1]
    px = (x - ox) / res
    py = yukseklik_px - (y - oy) / res
    return px, py


def raf_konturlarini_bul(img, res, origin):
    yukseklik_px = img.shape[0]
    mask = (img < ESIK).astype(np.uint8) * 255
    konturlar, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    adaylar = []
    for k in konturlar:
        alan = cv2.contourArea(k)
        if alan < MIN_ALAN:
            continue
        _, _, bw, bh = cv2.boundingRect(k)
        if bw > MAX_BBOX_PX or bh > MAX_BBOX_PX:
            continue  # dis duvar artefakti

        koseler_px = cv2.boxPoints(cv2.minAreaRect(k))
        koseler_m = np.array([piksel_to_harita(px, py, res, origin, yukseklik_px)
                               for px, py in koseler_px])

        # 4 kenar uzunlugu, en uzunu "uzun eksen" (raf 2.8m yuzu)
        kenar_uzunluklari = [np.linalg.norm(koseler_m[(i + 1) % 4] - koseler_m[i])
                              for i in range(4)]
        uzun_idx = int(np.argmax(kenar_uzunluklari))
        uzun_vektor = koseler_m[(uzun_idx + 1) % 4] - koseler_m[uzun_idx]
        kisa_idx = (uzun_idx + 1) % 4
        kisa_vektor = koseler_m[(kisa_idx + 1) % 4] - koseler_m[kisa_idx]

        uzunluk_m = np.linalg.norm(uzun_vektor)
        derinlik_m = np.linalg.norm(kisa_vektor)
        merkez = koseler_m.mean(axis=0)

        # normal: uzun eksene dik, +y (kuzey) yonunu gosteren birim vektor
        n = np.array([-uzun_vektor[1], uzun_vektor[0]])
        n = n / np.linalg.norm(n)
        if n[1] < 0:
            n = -n

        adaylar.append({
            'merkez': merkez, 'normal_kuzey': n,
            'uzunluk_m': uzunluk_m, 'derinlik_m': derinlik_m, 'alan_px': alan,
        })

    return adaylar


def raf_adreslerini_esle(adaylar):
    # y'ye gore azalan sirala (en yuksek y = A sirasi - A1/C3 fiziksel
    # olcumle capraz dogrulandi), 3'erli gruplara ayir (A/B/C), her
    # grubu x'e gore artan sirala (1/2/3 sutunlari).
    sirali = sorted(adaylar, key=lambda a: -a['merkez'][1])
    esleme = {}
    for sira_idx, sira_harfi in enumerate('ABC'):
        grup = sorted(sirali[sira_idx * 3:sira_idx * 3 + 3], key=lambda a: a['merkez'][0])
        for sutun_idx, aday in enumerate(grup):
            esleme[f'{sira_harfi}{sutun_idx + 1}'] = aday
    return esleme


def durma_noktasi_hesapla(aday, yon):
    merkez = aday['merkez']
    n = aday['normal_kuzey']
    geri_cekme = RAF_YARI_DERINLIK + KORIDOR_PAYI

    if yon == 'guney':
        nokta = merkez - n * geri_cekme
        yaw = math.atan2(n[1], n[0])          # kuzeye (+n) bakar
    else:
        nokta = merkez + n * geri_cekme
        yaw = math.atan2(-n[1], -n[0])        # guneye (-n) bakar

    return float(nokta[0]), float(nokta[1]), float(yaw)


def gorsel_uret(img, res, origin, esleme, sonuclar):
    yukseklik_px = img.shape[0]
    renkli = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    # buyutup okunakli hale getir
    olcek = 3
    renkli = cv2.resize(renkli, (renkli.shape[1] * olcek, renkli.shape[0] * olcek),
                         interpolation=cv2.INTER_NEAREST)

    for raf_adi, aday in esleme.items():
        x, y, yaw = sonuclar[raf_adi]
        merkez_px = harita_to_piksel(aday['merkez'][0], aday['merkez'][1], res, origin, yukseklik_px)
        nokta_px = harita_to_piksel(x, y, res, origin, yukseklik_px)

        mx, my = int(merkez_px[0] * olcek), int(merkez_px[1] * olcek)
        nx, ny = int(nokta_px[0] * olcek), int(nokta_px[1] * olcek)

        cv2.circle(renkli, (mx, my), 4, (0, 165, 255), -1)          # turuncu: raf merkezi
        cv2.circle(renkli, (nx, ny), 4, (255, 0, 0), -1)            # mavi: durma noktasi
        cv2.arrowedLine(renkli, (nx, ny),
                         (int(nx + 20 * math.cos(yaw)), int(ny - 20 * math.sin(yaw))),
                         (0, 255, 0), 2, tipLength=0.4)              # yesil ok: bakis yonu
        cv2.putText(renkli, raf_adi, (nx + 8, ny - 8), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 255), 2)

    cv2.imwrite(str(PNG_CIKTI), renkli)


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__,
                                           formatter_class=argparse.RawDescriptionHelpFormatter)
    ayristirici.add_argument('--uygula', action='store_true',
                              help="adres_veritabani.json'a yaz + PNG uret (yoksa sadece onizleme)")
    args = ayristirici.parse_args()

    pgm_yolu, res, origin = harita_meta_oku()
    img = cv2.imread(str(pgm_yolu), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"PGM okunamadi: {pgm_yolu}")

    adaylar = raf_konturlarini_bul(img, res, origin)
    print(f"Bulunan raf-boyutlu kontur sayisi: {len(adaylar)}")
    if len(adaylar) != 9:
        print("UYARI: 9 DEGIL - kor devam edilmiyor. Kontur listesi:")
        for i, a in enumerate(adaylar):
            print(f"  #{i}: merkez={a['merkez']}, uzunluk={a['uzunluk_m']:.2f}m, "
                  f"derinlik={a['derinlik_m']:.2f}m, alan={a['alan_px']:.0f}px^2")
        raise SystemExit(1)

    esleme = raf_adreslerini_esle(adaylar)

    veritabani = veritabani_oku()
    raflar_db = veritabani['raf_konumlari']

    sonuclar = {}
    print(f"\n{'raf':4} {'x':>8} {'y':>8} {'yaw_deg':>9} {'raf_uzunluk':>12} {'raf_derinlik':>13}")
    for raf_adi, aday in esleme.items():
        yon = raflar_db[raf_adi]['yon']
        x, y, yaw = durma_noktasi_hesapla(aday, yon)
        sonuclar[raf_adi] = (x, y, yaw)
        print(f"{raf_adi:4} {x:8.3f} {y:8.3f} {math.degrees(yaw):9.2f} "
              f"{aday['uzunluk_m']:12.2f} {aday['derinlik_m']:13.2f}")

        onceki = raflar_db[raf_adi]
        if onceki['durum'] == 'dogrulandi' and onceki['x'] is not None:
            fark = math.hypot(x - onceki['x'], y - onceki['y'])
            print(f"     -> fiziksel olcumden (dogrulandi) fark: {fark:.3f} m")

    if not args.uygula:
        print("\n(Onizleme modu - veritabanina yazmak ve PNG uretmek icin --uygula ekle.)")
        return

    for raf_adi, (x, y, yaw) in sonuclar.items():
        if raflar_db[raf_adi]['durum'] == 'dogrulandi':
            print(f"{raf_adi}: fiziksel olcum (dogrulandi) zaten var, UZERINE YAZILMADI.")
            continue
        not_metni = "SLAM haritasindan (depo_haritasi.pgm) goruntu isleme ile cikarildi"
        girdi_guncelle(raf_adi, 'haritadan_cikarildi', not_metni=not_metni, x=x, y=y, yaw=yaw)

    gorsel_uret(img, res, origin, esleme, sonuclar)
    print(f"\n9 raf adres_veritabani.json'a yazildi (durum: haritadan_cikarildi).")
    print(f"Gorsel kontrol: {PNG_CIKTI}")


if __name__ == '__main__':
    main()
