#!/usr/bin/env python3
"""
Her raf icin Nav2'nin gidecegi tarama (durma) pozunu (x, y, yaw + quaternion)
adres_veritabani.json'dan tarama_pozisyonlari.json'a formatlar.

NEDEN YENIDEN HESAPLAMA YOK: adres_veritabani.json'daki raf_konumlari
zaten map-frame'de OLCULMUS/HESAPLANMIS tarama durma noktalari (bkz. o
dosyanin kendi 'aciklama'/'hesap_yontemi' alanlari ve haritadan_adres_cikar.py)
- raf MERKEZI degil. Map-frame'de raf merkezi hicbir dosyada mevcut degil;
envanter.json'daki raf_konumlari/kutu 'konum' alanlari ise Gazebo WORLD
frame tasarim koordinatlaridir (depo.sdf ile birebir). Bunlari map-frame
raf merkezi gibi kullanip x_r,y_r + d_raf/2 + d_tarama formulunu tekrar
uygulamak, PROJE_DOSYASI.md SS12'deki world/map frame karisikligi hatasini
tekrarlar. Bu yuzden bu script sadece FORMAT donusumu yapar; geometrik
offset hesaplamasi zaten haritadan_adres_cikar.py'de (RAF_YARI_DERINLIK +
KORIDOR_PAYI, olculen normal yonuyle) dogru sekilde yapilmis durumda.

D_TARAMA burada sadece belgeleme/gelecekteki parametre degisikligi icin
tanimli - haritadan_adres_cikar.py'deki KORIDOR_PAYI ile ayni deger.

Kullanim:
  python3 tarama_pozisyonu_hesapla.py
"""

import json
import math
from pathlib import Path

from depo_robotu.adres_veritabani_araclari import VERITABANI_YOLU, veritabani_oku

BU_DIZIN = Path(__file__).resolve().parent
ENVANTER_YOLU = VERITABANI_YOLU.parent / 'envanter.json'
CIKTI_YOLU = VERITABANI_YOLU.parent / 'tarama_pozisyonlari.json'

# PROJE_DOSYASI.md SS8.6: kamera tilt siniri (1.2 rad) bu mesafenin altinda
# doyuma ugrayip ust kat gorulemez hale geliyor.
D_TARAMA_MIN = 0.65
D_TARAMA = 1.6  # haritadan_adres_cikar.py KORIDOR_PAYI ile ayni
assert D_TARAMA >= D_TARAMA_MIN, (
    f"D_TARAMA ({D_TARAMA} m) alt sinirin ({D_TARAMA_MIN} m) altinda - "
    f"ust kat kamera tilt doygunlugu riski (bkz. PROJE_DOSYASI.md SS8.6)"
)

GECERLI_DURUMLAR = {'dogrulandi', 'haritadan_cikarildi'}
YAW_SAPMA_ESIGI = 0.05  # rad - bunun uzerindeki ideal-vs-olculen fark ayrica raporlanir


def ideal_yaw(yon):
    if yon == 'guney':
        return math.pi / 2
    if yon == 'kuzey':
        return -math.pi / 2
    return None


def envanter_yon_tablosu_oku(envanter_yolu):
    if not envanter_yolu.exists():
        print(f"UYARI: {envanter_yolu} bulunamadi, yon capraz dogrulamasi atlaniyor.")
        return {}
    with open(envanter_yolu) as f:
        envanter = json.load(f)
    return {raf: bilgi.get('yon') for raf, bilgi in envanter.get('raf_konumlari', {}).items()}


def tarama_pozlarini_hesapla(veritabani, envanter_yon_tablosu):
    pozlar = {}
    for raf, girdi in veritabani['raf_konumlari'].items():
        durum = girdi.get('durum')
        if durum not in GECERLI_DURUMLAR:
            print(f"ATLANDI: '{raf}' - durum '{durum}' gecerli degil "
                  f"(beklenen: {sorted(GECERLI_DURUMLAR)})")
            continue

        yon = girdi.get('yon')
        if not yon:
            print(f"ATLANDI: '{raf}' - 'yon' alani bulunamadi")
            continue

        envanter_yon = envanter_yon_tablosu.get(raf)
        if envanter_yon is not None and envanter_yon != yon:
            print(f"UYARI: '{raf}' icin yon uyusmuyor - "
                  f"adres_veritabani.json='{yon}' vs envanter.json='{envanter_yon}'")

        x = girdi['x']
        y = girdi['y']
        yaw = girdi['yaw_rad']

        beklenen_yaw = ideal_yaw(yon)
        if beklenen_yaw is not None:
            sapma = abs(yaw - beklenen_yaw)
            if sapma > YAW_SAPMA_ESIGI:
                print(f"RAPOR: '{raf}' olculen yaw ({yaw:.4f} rad) ideal "
                      f"{yon} yawindan ({beklenen_yaw:.4f} rad) {sapma:.4f} rad "
                      f"sapiyor (esik: {YAW_SAPMA_ESIGI} rad)")

        pozlar[raf] = {
            'x': x,
            'y': y,
            'yaw': yaw,
            'quat_z': math.sin(yaw / 2),
            'quat_w': math.cos(yaw / 2),
            'yon': yon,
        }

    return pozlar


def main():
    veritabani = veritabani_oku()
    envanter_yon_tablosu = envanter_yon_tablosu_oku(ENVANTER_YOLU)

    pozlar = tarama_pozlarini_hesapla(veritabani, envanter_yon_tablosu)

    with open(CIKTI_YOLU, 'w') as f:
        json.dump(pozlar, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f"\n{len(pozlar)} raf icin tarama pozu yazildi: {CIKTI_YOLU}")
    for raf, poz in pozlar.items():
        print(f"  {raf}: x={poz['x']:.4f} y={poz['y']:.4f} yaw={poz['yaw']:.4f} "
              f"({poz['yon']})")


if __name__ == '__main__':
    main()
