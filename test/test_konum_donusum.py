"""
test_konum_donusum.py -- Sprint 6 teleport turu icin izole (ROS'suz)
geometri dogrulamasi. depo_robotu.konum_donusum'daki tahmini_dunya_konumu
rotasyonunun dogru isaret/yon kurallarini uyguladigini kanitlar.
"""

import math

from depo_robotu.konum_donusum import KAT_YUKSEKLIKLERI, oklid_hatasi, tahmini_dunya_konumu


def test_guney_bakan_yon_ornegi():
    """yaw=+90 derece (guney-bakan raf standoff'u, orn. A1/A2/A3/B1/B2/B3):
    local +y (yanal_konum) dunya -x'e, local +x (mesafe) dunya +y'ye gider.

    math.cos(pi/2) tam sifir olmadigi (kayan nokta) icin math.isclose
    kullanildi -- rotasyon matematiginin kendisi tam (bkz. capraz kontrol
    testi), bu sadece kayan nokta hassasiyeti.
    """
    x, y, z = tahmini_dunya_konumu(
        robot_x=0.0, robot_y=0.0, yaw=math.pi / 2,
        mesafe=2.0, yanal_konum=0.5, kat=2)
    assert math.isclose(x, -0.5, abs_tol=1e-9)
    assert math.isclose(y, 2.0, abs_tol=1e-9)
    assert z == KAT_YUKSEKLIKLERI[2]


def test_kuzey_bakan_yon_ornegi():
    """yaw=-90 derece (kuzey-bakan raf standoff'u, orn. C1/C2/C3):
    isaretler guney ornegine gore ters cevrilir (ayna simetrisi)."""
    x, y, z = tahmini_dunya_konumu(
        robot_x=5.0, robot_y=5.0, yaw=-math.pi / 2,
        mesafe=1.6, yanal_konum=-0.3, kat=1)
    assert math.isclose(x, 4.7, abs_tol=1e-9)
    assert math.isclose(y, 3.4, abs_tol=1e-9)
    assert z == KAT_YUKSEKLIKLERI[1]


def test_gercek_envanter_kutusuyla_capraz_kontrol():
    """A1 rafinin standart tarama duruşundan, gercek bir envanter kutusunun
    (kutu_A1_k1_p1: raf_konumlari A1={x:-4.0,y:4.0,yon:guney},
    kutu konum={x:-5.075,y:3.9,z:0.69}) yanal_konum'unu GERIYE DOGRU
    turetip fonksiyona verirsek, x tahmini GERCEK kutu x'iyle TAM
    eslesmeli (rotasyon matematiginin dogrulugunun kaniti) -- y ve z'de
    kucuk, BEKLENEN bir sapma olur (bkz. modul docstring'i, 'x=mesafe
    duzlemi' ve 'nominal kat yuksekligi' varsayimlari, YENI bir hata
    degil, zaten belgelenmis bir yaklasimin sayisallasmasi)."""
    raf_x, raf_y, yon = -4.0, 4.0, 'guney'
    raf_yari_derinlik, koridor_payi = 0.4, 1.6
    geri_cekme = raf_yari_derinlik + koridor_payi
    robot_x, robot_y, yaw = raf_x, raf_y - geri_cekme, math.pi / 2
    mesafe = raf_yari_derinlik + koridor_payi  # standoff'tan cepheye mesafe

    gercek_kutu = (-5.075, 3.9, 0.69)
    yanal_konum = robot_x - gercek_kutu[0]  # yaw=+90 icin x = robot_x - yanal_konum

    tahmini = tahmini_dunya_konumu(robot_x, robot_y, yaw, mesafe, yanal_konum, kat=1)

    assert math.isclose(tahmini[0], gercek_kutu[0], abs_tol=1e-9)  # x ekseni: rotasyon TAM dogru
    # y ekseni: cephe duzlemi (3.6) ile kutunun gercek derinligi (3.9) arasi
    # fark ~0.3 m, RAF_DERINLIK=0.8'in yarisindan kucuk olmali (mantik kontrolu).
    assert 0.0 < abs(tahmini[1] - gercek_kutu[1]) < 0.4
    # z ekseni: nominal kat yuksekligi (0.63) ile kutu merkezi (0.69) arasi
    # fark KAT_TOLERANS (0.35) icinde kalmali.
    assert abs(tahmini[2] - gercek_kutu[2]) < 0.35


def test_oklid_hatasi():
    assert oklid_hatasi((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) == 5.0
