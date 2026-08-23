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


class Filtre(BaseModel):
    renk: Optional[Renk] = None
    boyut: Optional[Boyut] = None

    def bos_mu(self) -> bool:
        return self.renk is None and self.boyut is None


class Sorgu(BaseModel):
    """LLM'in uretmesi gereken tek ve nihai yapi."""

    tip: SorguTipi
    raf: Optional[str] = None
    kat: Optional[int] = Field(default=None, ge=1, le=3)
    filtre: Optional[Filtre] = None

    @field_validator("raf")
    @classmethod
    def raf_gecerli_mi(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.upper() not in GECERLI_RAFLAR:
            raise ValueError(
                f"Gecersiz raf adi: {v!r}. Gecerli raflar: {sorted(GECERLI_RAFLAR)}"
            )
        return v.upper() if v else v

    def dogrula(self) -> None:
        """Tip'e gore zorunlu alanlarin var olup olmadigini kontrol eder.

        Pydantic tek basina 'tip=adres ise raf sart' gibi capraz-alan
        kurallarini kolayca ifade edemiyor, o yuzden ayri bir dogrulama.
        """
        if self.tip == SorguTipi.ADRES:
            if not self.raf:
                raise ValueError("adres sorgusu icin 'raf' zorunlu")
            if not self.kat:
                raise ValueError("adres sorgusu icin 'kat' zorunlu")
        elif self.tip == SorguTipi.ARAMA:
            if not self.filtre or self.filtre.bos_mu():
                raise ValueError("arama sorgusu icin en az bir filtre (renk/boyut) zorunlu")
        elif self.tip == SorguTipi.SAYIM:
            if not self.filtre or self.filtre.bos_mu():
                raise ValueError("sayim sorgusu icin en az bir filtre (renk/boyut) zorunlu")


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
