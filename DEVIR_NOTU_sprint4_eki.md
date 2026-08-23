# DEVİR NOTU EKİ — Sprint 4 (LLM Komut Çözümleme) Doğrulandı
**Tarih:** 23 Ağustos 2026
**Durum:** Sprint 4 madde 1-6 tamamlandı ve gerçek API ile doğrulandı.

---

## Bugün tamamlananlar

1. **FastAPI servisi kuruldu:** `~/staj_ws/src/depo_robotu/llm_servis/`
   altında bağımsız bir servis (`main.py`, `komut_cozumleyici.py`,
   `llm_saglayici.py`, `sorgu_semasi.py`). ROS 2 `colcon build` zincirine
   dahil değil, kendi `pip install`'ı var.

2. **LLM sağlayıcı: Google AI Studio (Gemini) seçildi.**
   - Tüm saglayici çağrısı `llm_saglayici.py`'de TEK fonksiyonda
     (`llm_cagir`) toplandı — yarın Groq/OpenRouter'a geçilirse sadece
     bu dosya değişir.
   - **Model adı:** `gemini-3.6-flash` kullanılıyor. `gemini-2.5-flash`
     23 Ağustos 2026 itibarıyla yeni hesaplara kapatıldı (404 hatası,
     Google'ın kendi mesajı `gemini-3.6-flash`'i önerdi). İleride tekrar
     404 alınırsa muhtemelen model yine değişmiştir, hata mesajındaki
     önerilen adı kullan.
   - **API key formatı değişti:** Google artık `AIzaSy...` yerine
     `AQ.Ab...` ("Auth key") formatında key veriyor (Haziran 2026
     itibarıyla). Eski `AIza` formatı Eylül 2026'da tamamen kapanacak.
     `google-genai` SDK'sı yeni formatı native destekliyor, kod
     değişikliği gerekmedi.

3. **Doğal dil → JSON sorgu + belirsizlik yönetimi çalışıyor.**
   `komut_cozumleyici.py`, LLM'in ürettiği JSON'u pydantic ile doğruluyor,
   sonra `arama`/`sayim` tipli sorgularda **gerçek envanter.json'a karşı
   sayarak** eşleşmeleri buluyor (LLM'e saydırmıyor — tasarım ilkesi:
   "belirsizliği LLM çözer, kesinliği veritabanı sağlar").

   **Bulunan ve düzeltilen hata:** `envanter.json`'un gerçek yapısı
   düz bir kutu listesi değil — üst seviyede `raf_konumlari`,
   `kat_yuzeyleri`, `kutular` anahtarları var (`kutu_uret.py` çıktısı).
   İlk yazımda bu varsayılmamıştı, `_envanter_yukle` fonksiyonu
   `veri.get("kutular", [])` ile düzeltildi (geriye dönük uyumluluk için
   düz liste durumu da destekleniyor).

4. **Üç sorgu tipi de gerçek API ile uçtan uca test edildi (curl):**

   | Komut | Sonuç |
   |---|---|
   | "A1'in 3. katına git" | `tip:adres, raf:A1, kat:3` ✅ |
   | "kırmızı kutuyu bul" | 11 eşleşme, `belirsiz:true`, tam liste döndü ✅ |
   | "kaç yeşil kutu var" | `tip:sayim, eslesme_sayisi:11, eslesmeler:null` ✅ |

   Sayım sorgusunda kutu listesi DÖNDÜRÜLMÜYOR (bilinçli tasarım) —
   sadece sayı. Arama sorgusunda birden fazla eşleşme varsa LLM'e değil
   kullanıcıya soruluyor (belirsiz:true + liste).

5. **Mock testler (`test_komut_cozumleyici.py`) gerçek envanter formatına
   güncellendi ve geçiyor** — 9 senaryo (adres, tek/çoklu/sıfır eşleşme,
   sayım, geçersiz raf, eksik alan, bozuk JSON, ilgisiz komut), API
   anahtarı olmadan LLM çağrısı mock'lanarak test ediliyor.

---

## Önemli teknik notlar (ileride hatırlanmalı)

- **Bu servis simülasyon GEREKTİRMİYOR.** `envanter.json` sabit bir
  dosya, LLM çağrısı internet üzerinden gidiyor — Gazebo/ROS 2 hiç
  devreye girmiyor. Test etmek için sadece `uvicorn main:app` yeterli.
- **`tip:adres` sorgusu koordinat ÜRETMİYOR** — bilinçli tasarım, sadece
  `raf`+`kat` döner. Koordinata çevirme (`adres_veritabani.json` /
  `tarama_pozisyonlari.json` okuma) Sprint 3'ün ürettiği navigasyon
  katmanının işi, burada karışmıyoruz.
- **`.env` dosyası git'e eklenmedi** (`.gitignore`'a `.env` eklendi).
  API key `GOOGLE_API_KEY=` satırında, boşluksuz `=` ile.
- **Ücretsiz katman notu:** Gemini Flash modelleri kredi kartsız
  ücretsiz, ama RPM/RPD limitleri sık değişiyor ve Google artık sabit
  bir tablo yayınlamıyor — canlı limitler için
  `aistudio.google.com/rate-limit`. `llm_saglayici.py` 429 hatasını
  ayrı yakalayıp (`LLMKotaHatasi`) kullanıcı dostu mesaja çeviriyor.

---

## Sıradaki: Sprint 5'e hazırlık / Sprint 4'ün geri kalanı

`main.py`'deki `/komut` endpoint'i şu an sadece sorguyu çözüp JSON
döndürüyor. Sprint 5'in çıktısı olan tam zincir
(komut → LLM → sorgu → navigasyon → tarama → doğrulama) için:

1. `tip:adres` sorgusu geldiğinde `tarama_pozisyonlari.json`'dan
   `raf`+`kat`'a karşılık gelen (x,y,yaw) okunup Nav2'ye hedef olarak
   verilecek bir katman eklenmeli (muhtemelen ayrı bir
   `navigasyon_koprusu.py`, ROS 2 tarafında, FastAPI servisinin DIŞINDA
   — bu servis ROS 2'den bağımsız kalmalı, ROS 2 node'u ayrı çalışıp
   bu servise HTTP ile sorgu atmalı, ya da tam tersi).
2. `tip:arama` sorgusu belirsizse (`belirsiz:true`), kullanıcıya
   sorulacak arayüz/akış henüz yok — şu an sadece API cevabı dönüyor.
3. Hatalı/anlaşılmayan komut yönetimi (madde 6) zaten `main.py`'de var
   ama gerçek kullanıcı arayüzünde nasıl gösterileceği belirlenmedi.

**Önce karar verilmesi gereken:** Sprint 5'e geçmeden, bu FastAPI
servisinin ROS 2 tarafıyla nasıl konuşacağı (HTTP'den ROS 2'ye köprü mü,
yoksa ROS 2 node'u FastAPI'yi mi çağıracak) netleşmeli.
