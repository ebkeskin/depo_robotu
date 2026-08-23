"""
main.py -- Sprint 4 madde 1: FastAPI servisi.

Calistirma:
    cd ~/staj_ws/src/depo_robotu/llm_servis
    pip install -r requirements.txt
    cp .env.example .env   # sonra GOOGLE_API_KEY'i doldur
    uvicorn main:app --reload --port 8000

Test:
    curl -X POST http://localhost:8000/komut \
         -H "Content-Type: application/json" \
         -d '{"metin": "kirmizi kutuyu bul"}'
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from komut_cozumleyici import komut_coz
from sorgu_semasi import SorguSonucu

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Depo Robotu Komut Servisi", version="0.1.0")

# envanter.json'un yolu -- staj_ws icindeki gercek konuma gore ayarla.
# .env'de EN VANTER_YOLU tanimlanmamissa proje yapisindaki varsayilan
# konum (araclar/envanter.json) denenir -- bkz. PROJE_DOSYASI.md 3.
_VARSAYILAN_ENVANTER = (
    Path(__file__).resolve().parent.parent / "araclar" / "envanter.json"
)
ENVANTER_YOLU = Path(os.environ.get("ENVANTER_YOLU", _VARSAYILAN_ENVANTER))


class KomutIstegi(BaseModel):
    metin: str


@app.get("/saglik")
def saglik() -> dict:
    return {
        "durum": "ayakta",
        "envanter_bulundu": ENVANTER_YOLU.exists(),
        "envanter_yolu": str(ENVANTER_YOLU),
    }


@app.post("/komut", response_model=SorguSonucu)
def komut_isle(istek: KomutIstegi) -> SorguSonucu:
    logger.info("Gelen komut: %r", istek.metin)
    sonuc = komut_coz(istek.metin, envanter_yolu=ENVANTER_YOLU)
    if not sonuc.basarili:
        logger.info("Basarisiz: %s", sonuc.hata)
    elif sonuc.belirsiz:
        logger.info("Belirsiz: %d eslesme", sonuc.eslesme_sayisi)
    return sonuc
