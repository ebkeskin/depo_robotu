"""
Sorgu semasi -- LLM'in uretmesi gereken JSON'un yapisi burada tanimli.

Tasarim ilkesi (PROJE_DOSYASI.md 1.4):
    Belirsizligi LLM cozer, kesinligi veritabani saglar.
    LLM'e koordinat hesaplatma, veritabanina cumle yorumlatma.

Bu yuzden bu semada KOORDINAT YOK. Sadece "ne isteniyor" var
(adres / arama / sayim), koordinata cevirme islemi adres_veritabani.json
ve envanter.json ile asagi katmanda (komut_cozumleyici.py) yapiliyor.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SorguTipi(str, Enum):
    ADRES = "adres"
    ARAMA = "arama"
    SAYIM = "sayim"


class Eylem(str, Enum):
    """Madde 1: tip=adres sorgusunun navigasyon mu (git) yoksa navigasyon
    + tarama mi (tara) istedigini ayirt eder -- bkz. navigasyon_koprusu.py."""

    GIT = "git"
    TARA = "tara"


class Renk(str, Enum):
    KIRMIZI = "kirmizi"
    YESIL = "yesil"
    MAVI = "mavi"
    SARI = "sari"
    KARTON = "karton"


class Boyut(str, Enum):
    BUYUK = "buyuk"
    ORTA = "orta"
    KUCUK = "kucuk"


# depo.sdf / envanter.json'daki raf adlari -- bkz. PROJE_DOSYASI.md 4.3
GECERLI_RAFLAR = {"A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"}


def _raf_dogrula(v: Optional[str]) -> Optional[str]:
    """Sorgu.raf ve Filtre.raf icin ortak dogrulama (Madde 2)."""
    if v is not None and v.upper() not in GECERLI_RAFLAR:
        raise ValueError(
            f"Gecersiz raf adi: {v!r}. Gecerli raflar: {sorted(GECERLI_RAFLAR)}"
        )
    return v.upper() if v else v


class Filtre(BaseModel):
    renk: Optional[Renk] = None
    boyut: Optional[Boyut] = None
    # Madde 2: "B2'deki kirmizi kutuyu bul" gibi raf-kapsamli arama/sayim icin.
    raf: Optional[str] = None

    @field_validator("raf")
    @classmethod
    def raf_gecerli_mi(cls, v: Optional[str]) -> Optional[str]:
        return _raf_dogrula(v)

    def bos_mu(self) -> bool:
        return self.renk is None and self.boyut is None and self.raf is None


class Sorgu(BaseModel):
    """LLM'in uretmesi gereken tek ve nihai yapi."""

    tip: SorguTipi
    raf: Optional[str] = None
    kat: Optional[int] = Field(default=None, ge=1, le=3)
    # Madde 1: sadece tip=adres icin anlamli -- "git" (salt navigasyon) mi
    # "tara" (navigasyon + Look-and-Move) mi istendigini ayirt eder.
    eylem: Optional[Eylem] = None
    # Madde 1: eylem=tara ve komutta belirli katlar gecmisse (orn. "1. ve
    # 2. katini tara") o katlarin listesi; None = uc kati da tara.
    katlar: Optional[list[int]] = None
    filtre: Optional[Filtre] = None
    # Madde 3: sadece tip=arama icin anlamli. "En yakin kirmizi kutuyu
    # bul" gibi komutlarda True -- birden fazla eslesme varsa hangisine
    # gidilecegini LLM degil, navigasyon_koprusu.py (robotun /odom veya
    # TF'den bildigi mevcut konumuyla) secer. Koordinat hesabi burada
    # YAPILMAZ (tasarim ilkesi, bkz. modul docstring'i).
    en_yakin: bool = False

    @field_validator("raf")
    @classmethod
    def raf_gecerli_mi(cls, v: Optional[str]) -> Optional[str]:
        return _raf_dogrula(v)

    @field_validator("katlar")
    @classmethod
    def katlar_gecerli_mi(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        if v is None:
            return v
        if not v:
            raise ValueError("'katlar' bos liste olamaz (tum katlar icin null kullan)")
        if any(k < 1 or k > 3 for k in v):
            raise ValueError(f"'katlar' sadece 1-3 arasi degerler icerebilir: {v}")
        if len(set(v)) != len(v):
            raise ValueError(f"'katlar' icinde tekrar eden deger olamaz: {v}")
        return sorted(set(v))

    def dogrula(self) -> None:
        """Tip'e gore zorunlu alanlarin var olup olmadigini kontrol eder.

        Pydantic tek basina 'tip=adres ise raf sart' gibi capraz-alan
        kurallarini kolayca ifade edemiyor, o yuzden ayri bir dogrulama.
        """
        if self.tip == SorguTipi.ADRES:
            if not self.raf:
                raise ValueError("adres sorgusu icin 'raf' zorunlu")
            if self.eylem is None:
                raise ValueError("adres sorgusu icin 'eylem' (git/tara) zorunlu")
            if self.eylem == Eylem.GIT and self.katlar is not None:
                raise ValueError("eylem='git' iken 'katlar' belirtilemez (git tarama yapmaz)")
        elif self.tip == SorguTipi.ARAMA:
            if not self.filtre or self.filtre.bos_mu():
                raise ValueError("arama sorgusu icin en az bir filtre (renk/boyut/raf) zorunlu")
        elif self.tip == SorguTipi.SAYIM:
            if not self.filtre or self.filtre.bos_mu():
                raise ValueError("sayim sorgusu icin en az bir filtre (renk/boyut/raf) zorunlu")


class SorguSonucu(BaseModel):
    """API'nin /komut endpoint'inden donecegi nihai cevap."""

    basarili: bool
    sorgu: Optional[Sorgu] = None
    # Belirsizlik: arama sorgusu birden fazla kutuyla eslesirse
    # LLM'e degil, kullaniciya donulur -- bkz. komut_cozumleyici.py
    belirsiz: bool = False
    eslesme_sayisi: Optional[int] = None
    eslesmeler: Optional[list[dict]] = None
    hata: Optional[str] = None
