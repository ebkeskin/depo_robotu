"""
LLM cagrisini sahteleyerek (gercek API anahtari olmadan) komut_coz'un
mantigini dogrulayan hizli testler. Gercek Gemini entegrasyonu
llm_saglayici.py'de izole oldugu icin burada sadece o fonksiyon
monkeypatch'leniyor -- tek fonksiyonda toplama tasariminin faydasi tam
burada gorulur.
"""

import json
from pathlib import Path
from unittest.mock import patch

import komut_cozumleyici
from llm_saglayici import LLMYaniti

ORNEK_ENVANTER = [
    {"id": "k1", "adres": "A1-kat1-poz1", "raf": "A1", "kat": 1, "pozisyon": 1,
     "renk": "kirmizi", "boyut": "buyuk", "konum": {"x": -4.6, "y": 3.9, "z": 0.69}},
    {"id": "k2", "adres": "A1-kat2-poz1", "raf": "A1", "kat": 2, "pozisyon": 1,
     "renk": "kirmizi", "boyut": "kucuk", "konum": {"x": -4.6, "y": 3.9, "z": 1.24}},
    {"id": "k3", "adres": "B2-kat1-poz1", "raf": "B2", "kat": 1, "pozisyon": 1,
     "renk": "yesil", "boyut": "orta", "konum": {"x": 0.0, "y": 0.0, "z": 0.69}},
]


def _sahte_envanter_yaz(tmp_path: Path) -> Path:
    yol = tmp_path / "envanter.json"
    # gercek envanter.json formati: ust seviyede 'kutular' anahtari var,
    # duz liste degil -- bkz. komut_cozumleyici.py _envanter_yukle
    yol.write_text(json.dumps({"kutular": ORNEK_ENVANTER}), encoding="utf-8")
    return yol


def _llm_sahte(json_metin: str):
    return lambda sistem_talimati, kullanici_metni: LLMYaniti(metin=json_metin, model="sahte")


def test_adres_sorgusu(tmp_path):
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"A1","kat":3,"eylem":"git","katlar":null,"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("A1'in 3. katina git")
    assert sonuc.basarili
    assert sonuc.sorgu.raf == "A1"
    assert sonuc.sorgu.kat == 3
    assert sonuc.sorgu.eylem == "git"
    print("test_adres_sorgusu: OK")


def test_adres_git_katsiz(tmp_path):
    # Madde 1: "git" icin kat belirtilmesi artik zorunlu degil.
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"A2","kat":null,"eylem":"git","katlar":null,"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("A2'ye git")
    assert sonuc.basarili
    assert sonuc.sorgu.kat is None
    print("test_adres_git_katsiz: OK")


def test_adres_tara_belirli_katlar(tmp_path):
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"B1","kat":null,"eylem":"tara","katlar":[1,2],"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("B1'in 1. ve 2. katini tara")
    assert sonuc.basarili
    assert sonuc.sorgu.eylem == "tara"
    assert sonuc.sorgu.katlar == [1, 2]
    print("test_adres_tara_belirli_katlar: OK")


def test_adres_git_ile_katlar_reddedilir(tmp_path):
    # eylem=git iken katlar dolu olamaz (git tarama yapmaz) -- dogrula() hatasi.
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"A2","kat":null,"eylem":"git","katlar":[1],"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("A2'ye git")
    assert not sonuc.basarili
    print("test_adres_git_ile_katlar_reddedilir: OK")


def test_arama_raf_filtresi_daraltir(tmp_path):
    # ORNEK_ENVANTER'da 2 kirmizi kutu var, ikisi de A1'de -- raf=B2 filtresi
    # eklenince 0 eslesme donmeli (raf'in gercekten uygulandigini kanitlar).
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"kirmizi","boyut":null,"raf":"B2"}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("B2'deki kirmizi kutuyu bul", envanter_yolu=envanter_yolu)
    assert not sonuc.basarili
    print("test_arama_raf_filtresi_daraltir: OK")


def test_arama_raf_filtresi_eslesir(tmp_path):
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"yesil","boyut":null,"raf":"B2"}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("B2'deki yesil kutuyu bul", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert not sonuc.belirsiz
    assert sonuc.eslesme_sayisi == 1
    print("test_arama_raf_filtresi_eslesir: OK")


def test_arama_en_yakin_bayragi(tmp_path):
    # Madde 3: en_yakin=true sema uzerinden dogru tasiniyor mu -- mesafe
    # hesabi/navigasyon navigasyon_koprusu.py'nin isi, burada sadece
    # sorgu.en_yakin alaninin dogru parse edildigi dogrulaniyor.
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte(
            '{"tip":"arama","raf":null,"kat":null,'
            '"filtre":{"renk":"kirmizi","boyut":null,"raf":null},"en_yakin":true}'
        ),
    ):
        sonuc = komut_cozumleyici.komut_coz("en yakin kirmizi kutuyu bul", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert sonuc.belirsiz  # ORNEK_ENVANTER'da 2 kirmizi kutu var
    assert sonuc.sorgu.en_yakin is True
    print("test_arama_en_yakin_bayragi: OK")


def test_arama_en_yakin_varsayilan_false(tmp_path):
    # en_yakin alani hic gelmezse (LLM eski/eksik JSON donerse) varsayilan
    # False olmali, sorgu yine de basarili sayilmali.
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"yesil","boyut":null}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("yesil kutuyu bul", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert sonuc.sorgu.en_yakin is False
    print("test_arama_en_yakin_varsayilan_false: OK")


def test_arama_tek_eslesme(tmp_path):
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"yesil","boyut":null}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("yesil kutuyu bul", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert not sonuc.belirsiz
    assert sonuc.eslesme_sayisi == 1
    print("test_arama_tek_eslesme: OK")


def test_arama_belirsiz_coklu_eslesme(tmp_path):
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"kirmizi","boyut":null}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("kirmizi kutuyu bul", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert sonuc.belirsiz
    assert sonuc.eslesme_sayisi == 2
    print("test_arama_belirsiz_coklu_eslesme: OK")


def test_sayim_sorgusu(tmp_path):
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"sayim","raf":null,"kat":null,"filtre":{"renk":"kirmizi","boyut":null}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("kac kirmizi kutu var?", envanter_yolu=envanter_yolu)
    assert sonuc.basarili
    assert sonuc.eslesme_sayisi == 2
    print("test_sayim_sorgusu: OK")


def test_arama_sifir_eslesme(tmp_path):
    envanter_yolu = _sahte_envanter_yaz(tmp_path)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"arama","raf":null,"kat":null,"filtre":{"renk":"sari","boyut":null}}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("sari kutuyu bul", envanter_yolu=envanter_yolu)
    assert not sonuc.basarili
    assert "bulunamadi" in sonuc.hata
    print("test_arama_sifir_eslesme: OK")


def test_gecersiz_raf_reddedilir(tmp_path):
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"Z9","kat":1,"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("Z9'a git")
    assert not sonuc.basarili
    print("test_gecersiz_raf_reddedilir: OK")


def test_eksik_alan_reddedilir(tmp_path):
    # adres tipi ama eylem eksik (kat artik zorunlu degil, bkz. test_adres_git_katsiz)
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":"adres","raf":"A1","kat":null,"eylem":null,"katlar":null,"filtre":null}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("A1'e git")
    assert not sonuc.basarili
    print("test_eksik_alan_reddedilir: OK")


def test_llm_bozuk_json_donerse():
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte("bu json degil {{{"),
    ):
        sonuc = komut_cozumleyici.komut_coz("anlassiz bir sey")
    assert not sonuc.basarili
    print("test_llm_bozuk_json_donerse: OK")


def test_ilgisiz_komut():
    with patch.object(
        komut_cozumleyici, "llm_cagir",
        _llm_sahte('{"tip":null,"hata":"depo robotuyla ilgisiz"}'),
    ):
        sonuc = komut_cozumleyici.komut_coz("bugun hava nasil?")
    assert not sonuc.basarili
    print("test_ilgisiz_komut: OK")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        test_adres_sorgusu(tmp_path)
        test_adres_git_katsiz(tmp_path)
        test_adres_tara_belirli_katlar(tmp_path)
        test_adres_git_ile_katlar_reddedilir(tmp_path)
        test_arama_tek_eslesme(tmp_path)
        test_arama_belirsiz_coklu_eslesme(tmp_path)
        test_arama_raf_filtresi_daraltir(tmp_path)
        test_arama_raf_filtresi_eslesir(tmp_path)
        test_arama_en_yakin_bayragi(tmp_path)
        test_arama_en_yakin_varsayilan_false(tmp_path)
        test_sayim_sorgusu(tmp_path)
        test_arama_sifir_eslesme(tmp_path)
        test_gecersiz_raf_reddedilir(tmp_path)
        test_eksik_alan_reddedilir(tmp_path)
        test_llm_bozuk_json_donerse()
        test_ilgisiz_komut()
    print("\nTUM TESTLER GECTI")