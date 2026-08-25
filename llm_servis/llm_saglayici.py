"""
llm_saglayici.py -- TUM saglayici cagrisi bu dosyada toplanir.

PROJE_DOSYASI.md Sprint 4, madde 3: "Saglayici cagrisini tek fonksiyonda
topla (gecis kolayligi)". Yani: bu dosyanin DISINDA hicbir yerde
'google.generativeai' ya da baska bir saglayici SDK'si import EDILMEZ.
Yarin Groq'a veya OpenRouter'a gecmek istersen sadece bu dosya degisir,
komut_cozumleyici.py ve main.py tek satir bile degismez.

Guvenlik (PROJE_DOSYASI.md Sprint 4 notu + Sprint 1'deki API anahtari
olayi): anahtar SADECE .env'den okunur, koda asla yazilmaz.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError


class LLMHatasi(Exception):
    """Saglayici cagrisiyla ilgili tum hatalarin ortak tabani.

    Ust katmanlar (komut_cozumleyici.py, main.py) sadece bu tipi
    yakalar -- Gemini'ye ozgu istisna tiplerini bilmek zorunda kalmazlar.
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


_MODEL_ADI = "gemini-3.6-flash"  # 2.5-flash yeni hesaplara kapatildi (Google'in
                                  # kendi hata mesaji bu modeli oneriyor, Agustos 2026)
_ZAMAN_ASIMI_SN = 20.0

_istemci: genai.Client | None = None


def _istemci_al() -> genai.Client:
    """Istemciyi tembel (lazy) olusturur -- API anahtari sadece
    gercekten cagri yapilacagi an okunur, import aninda degil.
    Boylece anahtar yoksa bile modul import edilebilir (testler icin)."""
    global _istemci
    if _istemci is None:
        anahtar = os.environ.get("GOOGLE_API_KEY")
        if not anahtar:
            raise LLMHatasi(
                "GOOGLE_API_KEY bulunamadi. .env dosyasina ekleyin "
                "(bkz. .env.example). .bashrc'ye ASLA yazmayin."
            )
        _istemci = genai.Client(api_key=anahtar)
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
        yanit = istemci.models.generate_content(
            model=_MODEL_ADI,
            contents=kullanici_metni,
            config=types.GenerateContentConfig(
                system_instruction=sistem_talimati,
                temperature=0.0,  # yapilandirilmis JSON icin tutarlilik onemli
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=int(_ZAMAN_ASIMI_SN * 1000)),
            ),
        )
    except ClientError as e:
        # 429 = kota/rate limit, google-genai bunu status_code ile veriyor
        if getattr(e, "code", None) == 429:
            raise LLMKotaHatasi(f"Gemini kota/rate limit asildi: {e}") from e
        raise LLMHatasi(f"Gemini istemci hatasi: {e}") from e
    except ServerError as e:
        raise LLMHatasi(f"Gemini sunucu hatasi (gecici olabilir): {e}") from e
    except APIError as e:
        raise LLMHatasi(f"Gemini API hatasi: {e}") from e
    except (TimeoutError, httpx.TimeoutException) as e:
        # httpx.TimeoutException (ReadTimeout/ConnectTimeout/vb.) builtin
        # TimeoutError'dan miras ALMIYOR -- google-genai http_options
        # zaman asimini alttaki httpx istemcisiyle uyguluyor, o yuzden
        # bu ayrica yakalanmazsa asagi katmanlara LLMHatasi degil ham
        # httpx exception'i sizip programi cokertiyor (Sprint 6
        # dogruluk_olcum.py ile canli API testinde yakalandi).
        raise LLMHatasi(f"Gemini zaman asimi ({_ZAMAN_ASIMI_SN}s): {e}") from e

    metin = getattr(yanit, "text", None)
    if not metin:
        raise LLMYanitHatasi("Gemini bos yanit dondurdu (guvenlik filtresi olabilir).")

    return LLMYaniti(metin=metin, model=_MODEL_ADI)