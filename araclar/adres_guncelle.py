#!/usr/bin/env python3
"""
adres_veritabani.json'daki bir raf girisini gozle-dogrulama sonucuna gore
guncellemek icin kucuk komut satiri araci. Dogrudan araclar/ altindaki
KAYNAK dosyayi duzenler (colcon share kopyasini degil) - degisiklik
kalici olsun, git'e girsin diye.

Guncelleme mantigi depo_robotu/adres_veritabani_araclari.py'de - bu script
sadece argparse sarmalayicisi (konum_yakala.py ile ayni fonksiyonu paylasir).

Kullanim:
  python3 adres_guncelle.py A1 dogrulandi
  python3 adres_guncelle.py A1 dogrulandi --not "0.1m saga alindi"
  python3 adres_guncelle.py A1 dogrulandi --x -3.9 --y 2.05 --yaw 1.55
"""

import argparse

from depo_robotu.adres_veritabani_araclari import girdi_guncelle


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

    girdi = girdi_guncelle(args.raf, args.durum, args.not_metni,
                            args.x, args.y, args.yaw)

    print(f"'{args.raf}' guncellendi: {girdi}")


if __name__ == '__main__':
    main()
