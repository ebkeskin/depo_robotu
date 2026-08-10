#!/usr/bin/env python3
"""
Depo raflarina kutu yerlestiren betik.

Ne uretir:
  1) kutular.sdf  -> depo.sdf icine yapistirilacak model bloklari
  2) envanter.json -> her kutunun adresi ve ozellikleri (Sprint 3 icin)

Kullanim:
  python3 kutu_uret.py
"""

import json
import random

# ----------------------------------------------------------------------
# AYARLAR  (istedigin gibi degistir, betigi tekrar calistir)
# ----------------------------------------------------------------------

TOHUM = 42          # ayni sayi = ayni dizilim (tekrar uretilebilirlik)
RENKLI_ORAN = 0.35  # kutularin yuzde kaci renkli olsun

# Yerlesim: kutular iki uctan iceri dogru dizilir, orta kisim seyrek kalir
SOL_KUTU_ADEDI = (1, 3)        # sol uctan kac kutu (rastgele bu aralikta)
SAG_KUTU_ADEDI = (1, 3)        # sag uctan kac kutu
KUTU_ARASI_BOSLUK = (0.05, 0.25)  # yan yana kutular arasi bosluk araligi
ORTA_MIN_BOSLUK = 0.15         # sol ve sag gruplar arasi en az bosluk

# Raf olculeri (depo.sdf ile ayni olmali)
RAF_UZUNLUK = 2.8
RAF_DERINLIK = 0.8
KAT_YUZEYLERI = [0.48, 1.03, 1.53]   # raf tablalarinin ust yuzeyi
KAT_ARASI = 0.55                      # ust katin tabani ile arasindaki bosluk

# Raf konumlari: ad -> (x, y, robotun_baktigi_yon)
# "guney" = robot rafin guneyinden bakar, kutular guney kenara yaslanir
RAFLAR = {
    "A1": (-4.0,  4.0, "guney"),
    "A2": ( 0.0,  4.0, "guney"),
    "A3": ( 4.0,  4.0, "guney"),
    "B1": (-4.0,  0.0, "guney"),
    "B2": ( 0.0,  0.0, "guney"),
    "B3": ( 4.0,  0.0, "guney"),
    "C1": (-4.0, -4.0, "kuzey"),
    "C2": ( 0.0, -4.0, "kuzey"),
    "C3": ( 4.0, -4.0, "kuzey"),
}

# Kutu tipleri: ad -> (en_x, derinlik_y, yukseklik_z)
KUTU_TIPLERI = {
    "buyuk": (0.55, 0.60, 0.42),
    "orta":  (0.42, 0.50, 0.35),
    "kucuk": (0.30, 0.35, 0.28),
}

# Renkler: ad -> (ambient, diffuse)
RENKLER = {
    "kirmizi": ("0.6 0.02 0.02 1", "0.9 0.05 0.05 1"),
    "yesil":   ("0.05 0.5 0.05 1", "0.1 0.85 0.1 1"),
    "mavi":    ("0.05 0.1 0.6 1",  "0.1 0.2 0.9 1"),
    "sari":    ("0.7 0.6 0.05 1",  "0.95 0.85 0.1 1"),
    "karton":  ("0.4 0.28 0.15 1", "0.65 0.45 0.25 1"),
}

RENKLI_LISTE = ["kirmizi", "yesil", "mavi", "sari"]


# ----------------------------------------------------------------------
# SDF sablonu
# ----------------------------------------------------------------------

SDF_SABLON = """    <model name="{ad}">
      <static>true</static>
      <pose>{x:.3f} {y:.3f} {z:.3f} 0 0 0</pose>
      <link name="link">
        <collision name="c">
          <geometry><box><size>{ex:.2f} {dy:.2f} {yz:.2f}</size></box></geometry>
        </collision>
        <visual name="v">
          <geometry><box><size>{ex:.2f} {dy:.2f} {yz:.2f}</size></box></geometry>
          <material>
            <ambient>{amb}</ambient>
            <diffuse>{dif}</diffuse>
            <specular>0.1 0.1 0.1 1</specular>
          </material>
        </visual>
      </link>
    </model>
"""


def kat_doldur(raf_ad, raf_x, raf_y, yon, kat_no, kat_yuzey, rng):
    """Bir rafin bir katini kutularla doldurur.

    Strateji: iki uctan iceri dogru yerlestirir.
    Once sol uctan birkac kutu, sonra sag uctan birkac kutu.
    Ortada dogal bir bosluk kalir.

    Doner: (sdf_metin_listesi, envanter_kayit_listesi)
    """
    sdf_parcalari = []
    kayitlar = []

    # Bu kata sigan kutu tipleri (ust tablaya carpmasin)
    uygun_tipler = [t for t, (_, _, h) in KUTU_TIPLERI.items() if h <= 0.45]

    sol_kenar = raf_x - RAF_UZUNLUK / 2 + 0.05
    sag_kenar = raf_x + RAF_UZUNLUK / 2 - 0.05

    # Her uctan kac kutu konacak
    sol_adet = rng.randint(*SOL_KUTU_ADEDI)
    sag_adet = rng.randint(*SAG_KUTU_ADEDI)

    yerlesimler = []   # (x_merkez, tip) listesi

    # --- Sol uctan iceri ---
    imlec = sol_kenar
    for _ in range(sol_adet):
        tip = rng.choice(uygun_tipler)
        ex = KUTU_TIPLERI[tip][0]
        if imlec + ex > sag_kenar:
            break
        yerlesimler.append((imlec + ex / 2, tip))
        imlec += ex + rng.uniform(*KUTU_ARASI_BOSLUK)
    sol_bitis = imlec

    # --- Sag uctan iceri ---
    imlec = sag_kenar
    for _ in range(sag_adet):
        tip = rng.choice(uygun_tipler)
        ex = KUTU_TIPLERI[tip][0]
        # sol taraftan gelenlerle carpisiyor mu
        if imlec - ex < sol_bitis + ORTA_MIN_BOSLUK:
            break
        yerlesimler.append((imlec - ex / 2, tip))
        imlec -= ex + rng.uniform(*KUTU_ARASI_BOSLUK)

    # --- SDF ve envanter uret ---
    yerlesimler.sort(key=lambda p: p[0])   # soldan saga sirala

    for poz_no, (kx, tip) in enumerate(yerlesimler, start=1):
        ex, dy, yz = KUTU_TIPLERI[tip]

        # y: kutu rafin on kenarina yaslanir
        if yon == "guney":
            on_kenar = raf_y - RAF_DERINLIK / 2
            ky = on_kenar + dy / 2
        else:  # kuzey
            on_kenar = raf_y + RAF_DERINLIK / 2
            ky = on_kenar - dy / 2

        kz = kat_yuzey + yz / 2

        if rng.random() < RENKLI_ORAN:
            renk = rng.choice(RENKLI_LISTE)
        else:
            renk = "karton"

        amb, dif = RENKLER[renk]
        ad = f"kutu_{raf_ad}_k{kat_no}_p{poz_no}"

        sdf_parcalari.append(SDF_SABLON.format(
            ad=ad, x=kx, y=ky, z=kz,
            ex=ex, dy=dy, yz=yz,
            amb=amb, dif=dif,
        ))

        kayitlar.append({
            "id": ad,
            "adres": f"{raf_ad}-kat{kat_no}-poz{poz_no}",
            "raf": raf_ad,
            "kat": kat_no,
            "pozisyon": poz_no,
            "renk": renk,
            "boyut": tip,
            "konum": {"x": round(kx, 3), "y": round(ky, 3), "z": round(kz, 3)},
        })

    return sdf_parcalari, kayitlar


def main():
    rng = random.Random(TOHUM)

    tum_sdf = []
    tum_envanter = []

    for raf_ad, (rx, ry, yon) in RAFLAR.items():
        for kat_no, kat_yuzey in enumerate(KAT_YUZEYLERI, start=1):
            sdf, kayit = kat_doldur(raf_ad, rx, ry, yon, kat_no, kat_yuzey, rng)
            tum_sdf.extend(sdf)
            tum_envanter.extend(kayit)

    # SDF dosyasi
    with open("kutular.sdf", "w") as f:
        f.write("<!-- OTOMATIK URETILDI: kutu_uret.py -->\n")
        f.writelines(tum_sdf)

    # Envanter dosyasi
    with open("envanter.json", "w") as f:
        json.dump({
            "raf_konumlari": {
                ad: {"x": x, "y": y, "yon": yon}
                for ad, (x, y, yon) in RAFLAR.items()
            },
            "kat_yuzeyleri": KAT_YUZEYLERI,
            "kutular": tum_envanter,
        }, f, indent=2, ensure_ascii=False)

    # Ozet
    print(f"Toplam kutu: {len(tum_envanter)}")
    sayim = {}
    for k in tum_envanter:
        sayim[k["renk"]] = sayim.get(k["renk"], 0) + 1
    print("Renk dagilimi:")
    for renk, adet in sorted(sayim.items()):
        print(f"  {renk:8s}: {adet}")
    print()
    print("Uretilen dosyalar: kutular.sdf, envanter.json")


if __name__ == "__main__":
    main()
