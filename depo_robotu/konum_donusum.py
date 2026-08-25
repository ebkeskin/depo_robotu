"""
konum_donusum.py -- Sprint 6 teleport turu ("coklu_raf_tarama_testi.py")
icin ROS'suz saf geometri: bir tespitin YEREL bilgisinden (mesafe,
yanal_konum, kat) tahmini DUNYA-cercevesi (x, y, z) konumunu hesaplar.

NEDEN WORLD/MAP KARISIKLIGI YOK (PROJE_DOSYASI.md SS12 KOK SEBEP'teki
hatanin tekrari degil): kutu_tespit.py'nin piksel_kat_hesapla'si
yanal_konum'u TF ile 'base_footprint' -> 'camera_rgb_optical_frame'
(yerel, map/odom'dan tamamen bagimsiz bir zincir) uzerinden hesaplar.
Robotun DUNYA-cercevesi pozu da olculmez, teleport ile zaten BILINIR
(Sprint 5 Madde 5 oracle_algi_karsilastirma.py ile ayni ilke). Yani
buradaki tek "donusum", bilinen bir dunya pozuna bilinen bir yerel
vektorun standart 2D rotasyonla eklenmesi -- ne AMCL ne SLAM haritasi
hicbir asamada devreye girmiyor.

BILINEN SINIR (mesafe icin): 'mesafe' burada canli LIDAR olcumu DEGIL,
Sprint 5 Madde 5'teki gibi standart tarama duruşu mesafesi (RAF_YARI_DERINLIK
+ KORIDOR_PAYI = 1.6 m) kullanilir -- bu, kutu_tespit.py'nin kendisinin de
tasidigi "x=mesafe duzlemi" varsayimiyla (PROJE_DOSYASI.md SS12 ACIK MADDE 2)
AYNI kisitlamayi tasir: gercek kutular rafin icinde CEPHE DUZLEMINDEN
daha derinde durabilir (kutu_uret.py RAF_DERINLIK=0.8 m), bu da y-ekseninde
birkac on cm'lik bir SISTEMATIK sapmaya yol acar. Bu YENI bir hata degil --
zaten var olan bir yaklasimin, kutu bazinda Oklid mesafesiyle ilk kez
SAYISALLASTIRILMASI.
"""

from __future__ import annotations

import math

# kamera_kontrol.py / kutu_tespit.py ile AYNI (kat -> nominal yukseklik).
KAT_YUKSEKLIKLERI = {1: 0.63, 2: 1.18, 3: 1.68}


def tahmini_dunya_konumu(
    robot_x: float, robot_y: float, yaw: float,
    mesafe: float, yanal_konum: float, kat: int,
) -> tuple[float, float, float]:
    """Robotun bilinen dunya pozu (robot_x, robot_y, yaw) + bir tespitin
    yerel bilgisinden (mesafe = robotun onune local +x mesafe, yanal_konum
    = robotun soluna local +y kayma, ROS REP103) tahmini dunya-cercevesi
    (x, y, z) konumunu doner. z, kat'in NOMINAL yuksekligidir (gercek kutu
    merkezinden birkac cm sapabilir, bkz. KAT_TOLERANS/fark_m -- ayri bir
    "kat-bazli dogruluk" metrigiyle zaten ele aliniyor, burada tekrar
    edilmiyor).
    """
    x = robot_x + mesafe * math.cos(yaw) - yanal_konum * math.sin(yaw)
    y = robot_y + mesafe * math.sin(yaw) + yanal_konum * math.cos(yaw)
    z = KAT_YUKSEKLIKLERI[kat]
    return x, y, z


def oklid_hatasi(
    tahmini: tuple[float, float, float], gercek: tuple[float, float, float],
) -> float:
    return math.dist(tahmini, gercek)
