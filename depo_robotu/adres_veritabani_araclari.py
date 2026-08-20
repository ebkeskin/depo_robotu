#!/usr/bin/env python3
"""
adres_veritabani.json'daki tek bir raf girisini guncelleyen ortak fonksiyon.

adres_guncelle.py (CLI, elle deger girme) ve konum_yakala.py (TF'ten olcup
otomatik yazma) ayni guncelleme mantigini burada paylasir - kod tekrarindan
kacinmak icin.
"""

import json
from pathlib import Path

from ament_index_python.packages import get_package_share_directory


def _kaynak_veritabani_yolu():
    """araclar/adres_veritabani.json KAYNAK (git'e giren) dosyasinin yolunu bulur.

    NOT: __file__ burada guvenilir degil - ament_python + setuptools 58.2.0
    (bkz. NOTLAR.md SORUN 6) `setup.py develop` kullanarak Python
    modullerini src -> build/lib -> install/site-packages zincirinde
    GERCEKTEN KOPYALIYOR, --symlink-install'a ragmen symlink'lemiyor (SORUN
    15'teki data_files sorunuyla ayni kok neden, modulleri de etkiliyor).
    Yani __file__.resolve() install ortaminda kendi kopyasinin site-packages
    icindeki konumunu verir, kaynak agactaki konumu degil.

    Bunun yerine get_package_share_directory ile guvenilir install share
    dizini bulunuyor, sonra colcon'un standart workspace duzenine gore
    (<ws>/install/<pkg> <-> <ws>/src/<pkg>, bkz. CLAUDE.md) 'install'
    segmenti 'src' ile degistirilerek KAYNAK dosyaya geri donuluyor - amac
    adres_guncelle.py'nin de belirttigi gibi share kopyasini degil kaynagi
    duzenlemek, boylece degisiklik git'e girer. Bu duzen bulunamazsa (farkli
    bir workspace duzeni), guvenli dusus olarak share kopyasi kullanilir.
    """
    share_dizini = Path(get_package_share_directory('depo_robotu'))
    for ata in share_dizini.parents:
        if ata.name == 'install':
            kaynak = ata.parent / 'src' / 'depo_robotu' / 'araclar' / 'adres_veritabani.json'
            if kaynak.exists():
                return kaynak
            break
    return share_dizini / 'araclar' / 'adres_veritabani.json'


VERITABANI_YOLU = _kaynak_veritabani_yolu()


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
