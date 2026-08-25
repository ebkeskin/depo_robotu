#!/usr/bin/env python3
"""
coklu_raf_analiz.py -- Sprint 6: coklu_raf_tarama_testi.py'nin tilt/sabit
ham verilerini (coklu_raf_ham_veri_{tilt,sabit}.json, bu dizinde) ROS'suz
olarak analiz edip 2 metrigi hesaplar: (1) kat-bazli dogruluk kirilimi,
(2) konumlandirma hatasi (tahmini vs envanter.json'daki gercek konum,
Oklid mesafesi). kutu_uret.py ile AYNI desen: saf Python, dogrudan
`python3 coklu_raf_analiz.py` ile calisir, ROS ortami sourcelanmasi
GEREKMEZ.

Tahmini dunya konumu hesabi icin konum_donusum.py'deki (depo_robotu
paketi) AYNI fonksiyonlar kullanilir -- mantik burada TEKRAR YAZILMADI.
ROS kurulumu olmadan da calisabilmesi icin kaynak dosyaya sys.path ile
DOGRUDAN erisilir (kurulu/sourcelanmis ROS paketine degil).

KONUM ESLESTIRME -- BILINEN SINIR (gizlenmedi, acikca burada belgelendi):
envanter.json'daki (raf,kat) kombinasyonlarinin %78'inde (21/27) AYNI
renkten 2+ kutu var. tarama_kontrol.py kendi dogruluk hesabini SADECE
renkle yapiyor (hangi ozel kutunun eslendigi onemsiz, bkz. asagidaki
_kat_bazli_dogruluk -- o algoritmanin birebir portu). Ama konumlandirma
hatasi icin HANGI ozel kutuya eslendigi onemli olduğundan, burada GREEDY
EN YAKIN eslestirme kullanildi: ayni (raf,kat,renk) icindeki TUM olasi
(tespit, gercek-kutu) ciftleri tahmini dunya-mesafesine gore siralanir,
en yakindan baslanarak ac-goz (greedy) atanir. Bu, DOGRU eslestirmeyi
GARANTI ETMEZ -- birden fazla ayni renkte kutu oldugunda, bir tespitin
GERCEKTE hangi kutuya ait oldugu bilinmiyor (kutu_tespit.py bu bilgiyi
tasimiyor); sunulan sadece EN MANTIKLI (en yakin) varsayimla bir tahmin.
Eslesen CIFT SAYISI ise tarama_kontrol.py'nin kendi renk-bazli sonucuyla
HER ZAMAN AYNIDIR (matematiksel olarak ayni bipartite eslestirme
problemi, sadece HANGI ozel ciftin secildigi farkli olabilir) -- bu,
asagida her (raf,kat) icin bir tutarlilik kontrolu olarak dogrulanir.

Ayrica konum_donusum.py'nin kendi belgeledigi "mesafe = sabit standoff
mesafesi" varsayimi (canli LIDAR degil) burada da GECERLI -- Oklid
hatasinin bir kismi bu BILINEN, ONCEDEN BELGELENMIS sapmadan gelir, YENI
bir hata degildir.

Kullanim:
  python3 coklu_raf_analiz.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

_BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(_BURASI.parent / 'depo_robotu'))
from konum_donusum import oklid_hatasi, tahmini_dunya_konumu  # noqa: E402

RAF_YARI_DERINLIK = 0.4  # m -- coklu_raf_tarama_testi.py / oracle_algi_karsilastirma.py ile AYNI
KORIDOR_PAYI = 1.6       # m -- coklu_raf_tarama_testi.py ile AYNI
MESAFE = RAF_YARI_DERINLIK + KORIDOR_PAYI  # standart tarama duruşu mesafesi

ENVANTER_YOLU = _BURASI / 'envanter.json'


def envanter_yukle() -> dict:
    with open(ENVANTER_YOLU, 'r', encoding='utf-8') as f:
        return json.load(f)


def ham_veri_yukle(etiket: str) -> list:
    yol = _BURASI / f'coklu_raf_ham_veri_{etiket}.json'
    with open(yol, 'r', encoding='utf-8') as f:
        return json.load(f)['sonuclar']


def _kat_bazli_dogruluk(tespit_kat: list, gt_kat: list) -> tuple[int, int]:
    """tarama_kontrol.py'nin _rapor_olustur'undaki renk-bazli greedy
    algoritmanin birebir portu (sadece kat bazinda cagrilir): her gt icin
    ayni renkte ilk (kalan) tespiti bul ve tuket. (eslesen, fazla) doner."""
    kalan = list(tespit_kat)
    eslesen = 0
    for gt in gt_kat:
        for i, t in enumerate(kalan):
            if t['renk'] == gt['renk']:
                eslesen += 1
                del kalan[i]
                break
    fazla = len(kalan)
    return eslesen, fazla


def _konum_eslestir(tespit_kat: list, gt_kat: list, robot_x: float, robot_y: float, yaw: float):
    """Ayni (raf,kat) icindeki tespit/gt ciftlerini GREEDY EN YAKIN
    dunya-mesafesine gore eslestirir (bkz. modul docstring -- bilinen
    eslestirme belirsizligi). [(hata_m, tespit, gt), ...] eslesen ciftleri
    doner."""
    adaylar = []
    for ti, t in enumerate(tespit_kat):
        est = tahmini_dunya_konumu(robot_x, robot_y, yaw, MESAFE, t['yanal_konum'], t['kat'])
        for gi, gt in enumerate(gt_kat):
            if t['renk'] != gt['renk']:
                continue
            gercek = (gt['konum']['x'], gt['konum']['y'], gt['konum']['z'])
            hata = oklid_hatasi(est, gercek)
            adaylar.append((hata, ti, gi))
    adaylar.sort(key=lambda a: a[0])

    tespit_kullanildi: set = set()
    gt_kullanildi: set = set()
    eslesmeler = []
    for hata, ti, gi in adaylar:
        if ti in tespit_kullanildi or gi in gt_kullanildi:
            continue
        tespit_kullanildi.add(ti)
        gt_kullanildi.add(gi)
        eslesmeler.append((hata, tespit_kat[ti], gt_kat[gi]))
    return eslesmeler


def analiz_et(etiket: str, envanter: dict) -> dict:
    sonuclar = ham_veri_yukle(etiket)
    kutular = envanter['kutular']

    kat_dogruluk_satirlari = []  # (raf, kat, eslesen, toplam)
    tum_hatalar: list = []
    kat_hatalari = {1: [], 2: [], 3: []}
    tutarlilik_sorunu = []  # renk-sayisi eslesen != konum-eslestirme eslesen sayisi olan (raf,kat)
    belirsiz_gruplar = 0  # ayni renkten 2+ gt kutusu olan (raf,kat,renk) grubu sayisi

    for s in sonuclar:
        if 'hata' in s:
            continue
        raf = s['raf']
        robot_x, robot_y, yaw = s['robot_x'], s['robot_y'], s['yaw']
        rapor = s['rapor']
        for kat_str, tespit_kat in rapor['tespitler'].items():
            kat = int(kat_str)
            gt_kat = [k for k in kutular if k['raf'] == raf and k['kat'] == kat]

            eslesen, _fazla = _kat_bazli_dogruluk(tespit_kat, gt_kat)
            kat_dogruluk_satirlari.append((raf, kat, eslesen, len(gt_kat)))

            renk_sayaci = Counter(k['renk'] for k in gt_kat)
            belirsiz_gruplar += sum(1 for c in renk_sayaci.values() if c >= 2)

            eslesmeler = _konum_eslestir(tespit_kat, gt_kat, robot_x, robot_y, yaw)
            if len(eslesmeler) != eslesen:
                tutarlilik_sorunu.append((raf, kat, eslesen, len(eslesmeler)))
            for hata, _t, _gt in eslesmeler:
                tum_hatalar.append(hata)
                kat_hatalari[kat].append(hata)

    return {
        'etiket': etiket,
        'kat_dogruluk_satirlari': kat_dogruluk_satirlari,
        'tum_hatalar': tum_hatalar,
        'kat_hatalari': kat_hatalari,
        'tutarlilik_sorunu': tutarlilik_sorunu,
        'belirsiz_gruplar': belirsiz_gruplar,
    }


def _istatistik(hatalar: list) -> dict:
    if not hatalar:
        return {'n': 0}
    return {
        'n': len(hatalar),
        'ortalama': round(statistics.mean(hatalar), 3),
        'medyan': round(statistics.median(hatalar), 3),
        'min': round(min(hatalar), 3),
        'maks': round(max(hatalar), 3),
        'std': round(statistics.pstdev(hatalar), 3),
    }


def rapor_yazdir(sonuc: dict) -> None:
    etiket = sonuc['etiket']
    print(f"\n=== {etiket.upper()} -- kat-bazli dogruluk ===")
    print(f"{'Raf':<5}{'Kat':<5}{'Eslesen':<10}{'Toplam':<8}{'Dogruluk':<10}")
    kat_toplam = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    for raf, kat, eslesen, toplam in sonuc['kat_dogruluk_satirlari']:
        oran = eslesen / toplam if toplam else 0.0
        print(f"{raf:<5}{kat:<5}{eslesen:<10}{toplam:<8}{oran:<10.3f}")
        kat_toplam[kat][0] += eslesen
        kat_toplam[kat][1] += toplam
    print(f"\n--- {etiket} kat ozeti (9 raf toplami) ---")
    for kat in (1, 2, 3):
        e, t = kat_toplam[kat]
        print(f"Kat {kat}: {e}/{t} = {e / t:.3f}" if t else f"Kat {kat}: veri yok")

    print(f"\n=== {etiket.upper()} -- konumlandirma hatasi (Oklid, m) ===")
    print(f"Genel: {_istatistik(sonuc['tum_hatalar'])}")
    for kat in (1, 2, 3):
        print(f"Kat {kat}: {_istatistik(sonuc['kat_hatalari'][kat])}")

    if sonuc['tutarlilik_sorunu']:
        print(f"\n[UYARI] Tutarlilik kontrolu basarisiz (raf,kat) sayisi: {len(sonuc['tutarlilik_sorunu'])}")
        for raf, kat, renk_esl, konum_esl in sonuc['tutarlilik_sorunu']:
            print(f"  {raf} kat{kat}: renk-bazli eslesen={renk_esl}, konum-bazli eslesen={konum_esl}")
    else:
        print('\n[OK] Tutarlilik kontrolu: konum-bazli eslesme sayisi HER (raf,kat) icin '
              "tarama_kontrol.py'nin renk-bazli sonucuyla birebir ayni.")

    print(f"\n[BILINEN SINIR] Ayni renkten 2+ gercek kutu bulunan (raf,kat,renk) grubu sayisi: "
          f"{sonuc['belirsiz_gruplar']} -- bu gruplardaki konum eslestirmeleri EN YAKIN VARSAYIMDIR, "
          f"kesin degildir (bkz. modul docstring'i).")


def main():
    envanter = envanter_yukle()
    sonuclar = {}
    for etiket in ('tilt', 'sabit'):
        sonuc = analiz_et(etiket, envanter)
        sonuclar[etiket] = sonuc
        rapor_yazdir(sonuc)

    cikti_yolu = _BURASI / 'coklu_raf_analiz_sonuclari.json'
    with open(cikti_yolu, 'w', encoding='utf-8') as f:
        json.dump({
            etiket: {
                'kat_dogruluk_satirlari': s['kat_dogruluk_satirlari'],
                'konum_hatasi_istatistik': _istatistik(s['tum_hatalar']),
                'konum_hatasi_kat_bazli': {k: _istatistik(v) for k, v in s['kat_hatalari'].items()},
                'belirsiz_gruplar': s['belirsiz_gruplar'],
                'tutarlilik_sorunu_sayisi': len(s['tutarlilik_sorunu']),
            }
            for etiket, s in sonuclar.items()
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSonuclar kaydedildi: {cikti_yolu}")


if __name__ == '__main__':
    main()
