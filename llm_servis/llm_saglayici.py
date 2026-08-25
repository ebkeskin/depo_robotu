"""
llm_saglayici.py -- TUM saglayici cagrisi bu dosyada toplanir.

PROJE_DOSYASI.md Sprint 4, madde 3: "Saglayici cagrisini tek fonksiyonda
topla (gecis kolayligi)". Yani: bu dosyanin DISINDA hicbir yerde
saglayiciya ozgu bir SDK import EDILMEZ. Bu sayede Sprint 6'da
Gemini'den Groq'a gecis SADECE bu dosya degistirilerek yapildi --
komut_cozumleyici.py, main.py, sorgu_semasi.py ve navigasyon_koprusu.py
TEK SATIR bile degismedi (llm_cagir'in imzasi ve LLMYaniti/LLMHatasi/
LLMKotaHatasi/LLMYanitHatasi sozlesmesi AYNEN korundu -- bkz.
PROJE_DOSYASI.md Sprint 6 Sonuc 3, "Groq'a gecis" notu).

Guvenlik (PROJE_DOSYASI.md Sprint 4 notu + Sprint 1'deki API anahtari
olayi): anahtar SADECE .env'den okunur, koda asla yazilmaz.

SAGLAYICI GECMISI:
- Sprint 4-6 (23-25 Agustos 2026): Google Gemini (gemini-3.6-flash).
  Sprint 6'nin TUM canli LLM dogrulamalari (Madde 1/3/5/6 eylem ayrimi,
  secim, iptal, en yakin -- bkz. navigasyon_koprusu.py) bu saglayiciyla
  yapildi.
- 25 Agustos 2026: Groq'a gecildi -- sebep, Gemini ucretsiz katmaninin
  GUNLUK (dakikalik degil) kotasi (gemini-3.6-flash,
  GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit=20/GUN) Sprint 6
  dogruluk_olcum.py ile tekrar tekrar tukendi (bkz. PROJE_DOSYASI.md
  Sprint 6 Sonuc 3). GOOGLE_API_KEY .env'de KASITLI olarak SILINMEDI --
  ileride geri donulmek istenirse hazir dursun (kullanilmiyor).
  GECIS ONCESI GEMINI ILE YAPILAN TUM CANLI TESTLER GROQ ILE HENUZ
  YENIDEN DOGRULANMADI -- bu onemli bir bosluk, gizlenmemeli.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from groq import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    Groq,
    GroqError,
    RateLimitError,
)


class LLMHatasi(Exception):
    """Saglayici cagrisiyla ilgili tum hatalarin ortak tabani.

    Ust katmanlar (komut_cozumleyici.py, main.py) sadece bu tipi
    yakalar -- saglayiciya ozgu istisna tiplerini bilmek zorunda kalmazlar.
    Bu da saglayici degisikliginde ust katmanlarin degismemesini saglar.
    """


class LLMKotaHatasi(LLMHatasi):
    """Rate limit / kota asimi. Cagiran taraf 'biraz sonra tekrar dene'
    diyebilsin diye ayri tutuldu."""


class LLMYanitHatasi(LLMHatasi):
    """Saglayici cevap verdi ama beklenmeyen bir sekilde (bos, guvenlik
    filtresine takildi, vb.)."""


@dataclass(frozen=True)
class LLMYaniti:
    metin: str
    model: str


# Sprint 6 Groq gecisinde (25 Agustos 2026) 3 aday CANLI karsilastirmayla
# test edildi (SISTEM_TALIMATI + 3 ornek komut, biri "hard"/dolayli):
#   - openai/gpt-oss-120b : 3/3 dogru JSON, hizli (~1-2s)          -> SECILDI
#   - qwen/qwen3.6-27b    : 1/3 gecersiz JSON uretti (json_validate_failed)
#   - groq/compound-mini  : agentic bir sarmalayici (perde arkasinda
#                           deprecate edilmis llama-3.3-70b-versatile'i
#                           kullaniyor, hata mesajindan anlasildi), 2.
#                           istekte paylasilan TPM kotasina carpti
# llama-3.3-70b-versatile (kullanicinin ilk onerisi) Groq'un dogrudan
# cagrilabilir model listesinde (client.models.list()) ARTIK YOK --
# varsayilmadi, canli sorguyla dogrulandi.
_MODEL_ADI = "openai/gpt-oss-120b"
_ZAMAN_ASIMI_SN = 20.0

# Adim 3 kucuk-olcekli canli dogrulamada (25 Agustos 2026) bulunan gercek
# sorun: Groq'un json_object modu SEMAYI ZORLAMIYOR (bkz. modul docstring'i
# ve llm_cagir icindeki ayni uyari) -- "Kac kirmizi kutu var?" gibi bir
# sayim sorgusunda model "en_yakin": null dondurdu, ama Sorgu semasinda
# en_yakin duz bir bool (Optional degil) oldugu icin pydantic bunu
# reddetti. SISTEM_TALIMATI'nin kendisi (komut_cozumleyici.py) BURADAN
# DEGISTIRILMEDI -- kullanicinin onayiyla sadece Groq'a giden sistem
# mesajinin SONUNA, bu dosyaya ozel kisa bir hatirlatma EKLENIYOR.
_GROQ_EK_HATIRLATMA = (
    "\n\nEK KURAL (JSON gecerliligi icin kritik): 'en_yakin' alani "
    "ASLA null olamaz -- sadece true veya false olmali (varsayilan false)."
)


def _groq_sistem_mesaji(sistem_talimati: str) -> str:
    return sistem_talimati + _GROQ_EK_HATIRLATMA

_istemci: Groq | None = None


def _istemci_al() -> Groq:
    """Istemciyi tembel (lazy) olusturur -- API anahtari sadece
    gercekten cagri yapilacagi an okunur, import aninda degil.
    Boylece anahtar yoksa bile modul import edilebilir (testler icin)."""
    global _istemci
    if _istemci is None:
        anahtar = os.environ.get("GROQ_API_KEY")
        if not anahtar:
            raise LLMHatasi(
                "GROQ_API_KEY bulunamadi. .env dosyasina ekleyin "
                "(bkz. .env.example). .bashrc'ye ASLA yazmayin."
            )
        _istemci = Groq(api_key=anahtar)
    return _istemci


def llm_cagir(sistem_talimati: str, kullanici_metni: str) -> LLMYaniti:
    """TEK GIRIS NOKTASI. Butun proje LLM'e bu fonksiyon uzerinden konusur.

    Args:
        sistem_talimati: Modelin rolunu / cikti formatini anlatan talimat.
        kullanici_metni: Kullanicinin dogal dil komutu.

    Returns:
        LLMYaniti(metin=..., model=...)

    Raises:
        LLMKotaHatasi: Rate limit / kota asildi.
        LLMYanitHatasi: Yanit bos veya kullanilamaz.
        LLMHatasi: Diger tum saglayici hatalari (ag, kimlik dogrulama, vb.)
    """
    istemci = _istemci_al()
    try:
        yanit = istemci.chat.completions.create(
            model=_MODEL_ADI,
            messages=[
                {"role": "system", "content": _groq_sistem_mesaji(sistem_talimati)},
                {"role": "user", "content": kullanici_metni},
            ],
            temperature=0.0,  # yapilandirilmis JSON icin tutarlilik onemli
            # DIKKAT: Gemini'nin response_mime_type'inin aksine, Groq'un
            # json_object modu SADECE "gecerli JSON uret" garantisi verir --
            # BIZIM SORGU SEMAMIZA uyacagini GARANTI ETMEZ. Sema uyumu
            # SISTEM_TALIMATI'ndaki (komut_cozumleyici.py) aciklama ve
            # orneklere birakiliyor; bu dosyaya veya SISTEM_TALIMATI'na
            # ekstra bir sema-hatirlatmasi EKLENMEDI -- 3 canli ornekle
            # (yukaridaki model secim notu) zaten yeterince guvenilir
            # bulundu, gereksiz degisiklik yapilmadi.
            response_format={"type": "json_object"},
            timeout=_ZAMAN_ASIMI_SN,
        )
    except RateLimitError as e:
        raise LLMKotaHatasi(f"Groq kota/rate limit asildi: {e}") from e
    except APITimeoutError as e:
        raise LLMHatasi(f"Groq zaman asimi ({_ZAMAN_ASIMI_SN}s): {e}") from e
    except httpx.TimeoutException as e:
        # Gemini gecisinde ogrenilen ders (bkz. PROJE_DOSYASI.md Sprint 6
        # Sonuc 3): alttaki httpx istemcisinin attigi ReadTimeout/vb.
        # exception'lar SDK'nin kendi APITimeoutError'una HER ZAMAN
        # sarilmayabilir -- ayrica yakalanmazsa LLMHatasi'ye donusmeden
        # sizip programi cokertir. Ayni savunma burada da uygulandi.
        raise LLMHatasi(f"Groq zaman asimi (httpx, {_ZAMAN_ASIMI_SN}s): {e}") from e
    except APIConnectionError as e:
        raise LLMHatasi(f"Groq baglanti hatasi: {e}") from e
    except APIStatusError as e:
        # RateLimitError/APITimeoutError yukarida ayri yakalandigi icin
        # buraya sadece diger durum kodlari (400/401/403/404/409/422/5xx)
        # duser -- orn. canli testte gorulen json_validate_failed (400).
        raise LLMHatasi(f"Groq API hatasi (status={e.status_code}): {e}") from e
    except GroqError as e:
        raise LLMHatasi(f"Groq hatasi: {e}") from e

    metin = yanit.choices[0].message.content if yanit.choices else None
    if not metin:
        raise LLMYanitHatasi("Groq bos yanit dondurdu (guvenlik filtresi olabilir).")

    return LLMYaniti(metin=metin, model=_MODEL_ADI)
