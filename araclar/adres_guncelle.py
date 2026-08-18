#!/usr/bin/env python3
"""
adres_veritabani.json'daki bir raf girisini gozle-dogrulama sonucuna gore
guncellemek icin kucuk komut satiri araci. Dogrudan araclar/ altindaki
KAYNAK dosyayi duzenler (colcon share kopyasini degil) - degisiklik
kalici olsun, git'e girsin diye.

Kullanim:
  python3 adres_guncelle.py A1 dogrulandi
  python3 adres_guncelle.py A1 dogrulandi --not "0.1m saga alindi"
  python3 adres_guncelle.py A1 dogrulandi --x -3.9 --y 2.05 --yaw 1.55
"""

import argparse
import json
from pathlib import Path

VERITABANI_YOLU = Path(__file__).parent / 'adres_veritabani.json'


def main():
    ayrıştırıcı = argparse.ArgumentParser(description=__doc__)
    ayrıştırıcı.add_argument('raf', help="Raf adi, orn. A1")
    ayrıştırıcı.add_argument('durum', choices=['dogrulandi', 'dogrulanmadi'])
    ayrıştırıcı.add_argument('--not', dest='not_metni', default=None,
                              help='Gozle kontrolde gorulen sapma/duzeltme notu')
    ayrıştırıcı.add_argument('--x', type=float, default=None)
    ayrıştırıcı.add_argument('--y', type=float, default=None)
    ayrıştırıcı.add_argument('--yaw', type=float, default=None,
                              help='radyan cinsinden duzeltilmis yaw')
    args = ayrıştırıcı.parse_args()

    with open(VERITABANI_YOLU) as f:
        veritabani = json.load(f)

    raflar = veritabani['raf_konumlari']
    if args.raf not in raflar:
        raise SystemExit(f"'{args.raf}' adres_veritabani.json'da yok. "
                          f"Gecerli rafler: {list(raflar.keys())}")

    girdi = raflar[args.raf]
    girdi['durum'] = args.durum
    if args.not_metni is not None:
        girdi['not'] = args.not_metni
    if args.x is not None:
        girdi['x'] = args.x
    if args.y is not None:
        girdi['y'] = args.y
    if args.yaw is not None:
        girdi['yaw_rad'] = args.yaw

    with open(VERITABANI_YOLU, 'w') as f:
        json.dump(veritabani, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f"'{args.raf}' guncellendi: {girdi}")


if __name__ == '__main__':
    main()
