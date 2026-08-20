#!/usr/bin/env python3
"""
2 referans raf icin `konum_yakala.py` ile OLCULMUS map-frame pose'lardan
kati (rigid: rotasyon + oteleme) bir world->map donusumu cikarip, bu
donusumu geri kalan raflarin BILINEN world-frame (Gazebo/depo.sdf tasarim)
koordinatlarina uygulayarak adres_veritabani.json'un tamamini doldurur.

KOK SEBEP / BAGLAM: bkz. NOTLAR.md SORUN "adres veritabani kok sebep
duzeltmesi" (commit f97af94) ve PROJE_DOSYASI.md SS12. map frame'in
origini SLAM'in haritalamaya basladigi ana baglidir, gercek dunya
(world) origini ile CAKISMAZ - bu yuzden world koordinatlari dogrudan
Nav2'ye verilemez. `konum_yakala.py` her rafi TEK TEK elle surup olcerek
bu sorunu cozuyor ama 9 raf icin 9 ayri surus gerektiriyor.

Bu arac bunu 2 surus + hesaplamaya indirger: 2 referans noktasi (varsayilan
A1 ve C3 - birbirinden mumkun oldugunca uzak, capraz kose, boylece
rotasyon acisi hassas kestirilir) OLCULUR, kalan 7 raf HESAPLANIR. Bu,
PROJE_DOSYASI.md SS12'de reddedilen "(y+5) gibi tahmini sabit offset"
yaklasimindan FARKLI: burada offset tahmin edilmiyor, iki gercek olcumden
matematiksel olarak cikariliyor. Yine de hesaplanan degerler dogrudan
"dogrulandi" isaretlenmez - durum "hesaplandi_2nokta" olarak yazilir,
cunku fiziksel olarak o raflara gidilip gozle kontrol edilmedi. SLAM
haritasi mukemmel rijit olmayabilir (kucuk loop-closure distorsiyonu),
bu yuzden en az birkac hesaplanan rafa ornekleme ile gidilip
adres_dogrula.py ile kontrol edilmesi, tutarsa 'dogrulandi'ya
cevrilmesi onerilir.

Kullanim:
  # 1) Once iki referans rafi konum_yakala.py ile OLCUP veritabanina yaz:
  ros2 run depo_robotu konum_yakala --ros-args -p raf:=A1
  ros2 run depo_robotu konum_yakala --ros-args -p raf:=C3

  # 2) Sonra bu arac ile geri kalan 7 rafi HESAPLAYIP yaz:
  python3 iki_nokta_kalibrasyon.py                  # sadece onizleme (yazmaz)
  python3 iki_nokta_kalibrasyon.py --uygula          # veritabanina yazar
  python3 iki_nokta_kalibrasyon.py --ref1 A1 --ref2 C3 --uygula
"""

import argparse
import math

from depo_robotu.adres_veritabani_araclari import girdi_guncelle, veritabani_oku

# kutu_uret.py'deki RAFLAR sozlugunden + commit 1584ecf'teki durma noktasi
# formulunden turetilen SABIT world-frame (Gazebo gercek dunya) durma
# noktalari. Bunlar kaymaya ugrayan taraf DEGIL - depo.sdf tasarimindan
# degismeden gelir, yalnizca map frame'e tasima donusumu olculmesi gerekir.
DUNYA_KOORDINATLARI = {
    "A1": (-4.0,  2.0,  math.pi / 2),
    "A2": ( 0.0,  2.0,  math.pi / 2),
    "A3": ( 4.0,  2.0,  math.pi / 2),
    "B1": (-4.0, -2.0,  math.pi / 2),
    "B2": ( 0.0, -2.0,  math.pi / 2),
    "B3": ( 4.0, -2.0,  math.pi / 2),
    "C1": (-4.0, -2.0, -math.pi / 2),
    "C2": ( 0.0, -2.0, -math.pi / 2),
    "C3": ( 4.0, -2.0, -math.pi / 2),
}

# Iki referans noktasi arasindaki world-frame mesafe ile map-frame mesafesi
# bu orandan fazla sapiyorsa, SLAM haritasinin rijit olmayabilecegine
# (olcek distorsiyonu) dair uyari basilir - kesin bir fizik degil, kaba bir
# esik.
OLCEK_UYARI_ESIGI = 0.03


def yaw_normalize(aci):
    return math.atan2(math.sin(aci), math.cos(aci))


def kalibrasyon_hesapla(world_p, map_p, world_q, map_q):
    dwx, dwy = world_q[0] - world_p[0], world_q[1] - world_p[1]
    dmx, dmy = map_q[0] - map_p[0], map_q[1] - map_p[1]

    dunya_mesafe = math.hypot(dwx, dwy)
    harita_mesafe = math.hypot(dmx, dmy)
    if dunya_mesafe < 1e-6:
        raise ValueError("Referans noktalar cakisik/cok yakin, rotasyon hesaplanamaz.")

    theta = math.atan2(dmy, dmx) - math.atan2(dwy, dwx)
    olcek_orani = harita_mesafe / dunya_mesafe

    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rp_x = cos_t * world_p[0] - sin_t * world_p[1]
    rp_y = sin_t * world_p[0] + cos_t * world_p[1]
    tx = map_p[0] - rp_x
    ty = map_p[1] - rp_y

    return theta, tx, ty, olcek_orani


def donusum_uygula(theta, tx, ty, wx, wy, w_yaw):
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    mx = cos_t * wx - sin_t * wy + tx
    my = sin_t * wx + cos_t * wy + ty
    m_yaw = yaw_normalize(w_yaw + theta)
    return mx, my, m_yaw


def main():
    ayristirici = argparse.ArgumentParser(description=__doc__,
                                           formatter_class=argparse.RawDescriptionHelpFormatter)
    ayristirici.add_argument('--ref1', default='A1', help="1. referans raf (varsayilan A1)")
    ayristirici.add_argument('--ref2', default='C3', help="2. referans raf (varsayilan C3)")
    ayristirici.add_argument('--uygula', action='store_true',
                              help="Hesaplanan degerleri adres_veritabani.json'a yaz (yoksa sadece onizleme)")
    args = ayristirici.parse_args()

    veritabani = veritabani_oku()
    raflar = veritabani['raf_konumlari']

    for ref in (args.ref1, args.ref2):
        if ref not in raflar:
            raise SystemExit(f"'{ref}' adres_veritabani.json'da yok.")
        girdi = raflar[ref]
        if girdi['durum'] != 'dogrulandi' or girdi['x'] is None:
            raise SystemExit(
                f"'{ref}' henuz olculmedi (durum={girdi['durum']!r}). Once:\n"
                f"  ros2 run depo_robotu konum_yakala --ros-args -p raf:={ref}")
        if ref not in DUNYA_KOORDINATLARI:
            raise SystemExit(f"'{ref}' icin world-frame tasarim koordinati tanimli degil.")

    world_p = DUNYA_KOORDINATLARI[args.ref1][:2]
    map_p = (raflar[args.ref1]['x'], raflar[args.ref1]['y'])
    world_q = DUNYA_KOORDINATLARI[args.ref2][:2]
    map_q = (raflar[args.ref2]['x'], raflar[args.ref2]['y'])

    theta, tx, ty, olcek_orani = kalibrasyon_hesapla(world_p, map_p, world_q, map_q)

    print(f"Kalibrasyon: theta={math.degrees(theta):.2f} derece, "
          f"tx={tx:.3f}, ty={ty:.3f}, olcek_orani={olcek_orani:.4f}")
    if abs(olcek_orani - 1.0) > OLCEK_UYARI_ESIGI:
        print(f"UYARI: olcek orani 1.0'dan >{OLCEK_UYARI_ESIGI*100:.0f}% sapiyor - "
              "SLAM haritasi tam rijit olmayabilir (distorsiyon). Hesaplanan "
              "raflara guvenmeden once orneklem kontrolu SART.")

    print(f"\n{'raf':4} {'x':>8} {'y':>8} {'yaw_deg':>9}")
    for raf, (wx, wy, w_yaw) in DUNYA_KOORDINATLARI.items():
        if raf in (args.ref1, args.ref2):
            continue
        mx, my, m_yaw = donusum_uygula(theta, tx, ty, wx, wy, w_yaw)
        print(f"{raf:4} {mx:8.3f} {my:8.3f} {math.degrees(m_yaw):9.2f}")
        if args.uygula:
            not_metni = (f"iki-nokta kalibrasyon ile hesaplandi "
                         f"(referans: {args.ref1}+{args.ref2}), fiziksel dogrulama YOK")
            girdi_guncelle(raf, 'hesaplandi_2nokta', not_metni=not_metni,
                            x=mx, y=my, yaw=m_yaw)

    if not args.uygula:
        print("\n(Onizleme modu - veritabanina yazmak icin --uygula ekle.)")
    else:
        print(f"\n{len(DUNYA_KOORDINATLARI) - 2} raf adres_veritabani.json'a yazildi "
              "(durum: hesaplandi_2nokta). Orneklem kontrolu icin adres_dogrula.py "
              "ile birkacina gidip gozle dogrula.")


if __name__ == '__main__':
    main()
