#!/usr/bin/env python3
"""
adres_veritabani.json'daki tek bir raf girisini guncelleyen ortak fonksiyon.

adres_guncelle.py (CLI, elle deger girme) ve konum_yakala.py (TF'ten olcup
otomatik yazma) ayni guncelleme mantigini burada paylasir - kod tekrarindan
kacinmak icin.
"""

import json
from pathlib import Path

# Bu dosya depo_robotu/depo_robotu/ altinda; araclar/ bir ust dizinin
# kardesi. symlink-install ile de calisir cunku kurulan dosya kaynaga
# symlink'lenir, boylece __file__ yine src/ agacindaki gercek konumu verir.
VERITABANI_YOLU = Path(__file__).resolve().parent.parent / 'araclar' / 'adres_veritabani.json'


def veritabani_oku(veritabani_yolu=VERITABANI_YOLU):
    with open(veritabani_yolu) as f:
        return json.load(f)


def girdi_guncelle(raf, durum, not_metni=None, x=None, y=None, yaw=None,
                    veritabani_yolu=VERITABANI_YOLU):
    veritabani = veritabani_oku(veritabani_yolu)

    raflar = veritabani['raf_konumlari']
    if raf not in raflar:
        raise KeyError(f"'{raf}' adres_veritabani.json'da yok. "
                        f"Gecerli rafler: {list(raflar.keys())}")

    girdi = raflar[raf]
    girdi['durum'] = durum
    if not_metni is not None:
        girdi['not'] = not_metni
    if x is not None:
        girdi['x'] = x
    if y is not None:
        girdi['y'] = y
    if yaw is not None:
        girdi['yaw_rad'] = yaw

    with open(veritabani_yolu, 'w') as f:
        json.dump(veritabani, f, ensure_ascii=False, indent=2)
        f.write('\n')

    return girdi
