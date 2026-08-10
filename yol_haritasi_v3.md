# Yol Haritası — v3 (Araştırma Sonrası Güncelleme)

**Proje:** Yapay Zeka Destekli Akıllı Depo Robotu Simülasyonu
**Ortam:** Ubuntu 22.04 · ROS 2 Humble · Gazebo Sim 8 (Harmonic) · TurtleBot3 Waffle Pi

> Bu sürüm, aktif algılama araştırmasının bulgularını mevcut sprint yapısına
> yediriyor. Araştırma belgesindeki "3 haftalık plan" ayrı bir takvim değil —
> Sprint 2'nin algı katmanının detaylandırılmış halidir.

---

## Sprint 1 — Altyapı ✅ TAMAMLANDI

- `.bashrc` temizliği, `ida` / `staj` ortam ayrımı
- API anahtarı güvenliği
- Gazebo Classic yerine Harmonic kararı (çakışma analizi)
- `turtlebot3_simulations` kaynaktan derleme + 5 yama
- Robot çalışır durumda: sürülüyor, sensörleri yayın yapıyor
- Git kurulumu, kurulum notları belgesi

---

## Sprint 2 — Ortam ve Algı 🔄 DEVAM EDİYOR

### 2A — Ortam ✅ BİTTİ

- `depo_robotu` ROS 2 paketi
- `depo.sdf`: 12×12 m depo, 9 raf (3 kat), duvarlar, kapı
- `depo.launch.py`: kendi dünyamızı yükleyen launch
- `kutu_uret.py`: 96 kutu üretiyor, iki uçtan hizalı yerleşim
- `envanter.json`: **ground truth** — her kutunun adresi, rengi, boyutu, konumu
- setuptools 58.2.0 sabitlemesi

### 2B — Hareketli Kamera ✅ BİTTİ

- `camera_joint` → `revolute` (tilt ekseni, -0.5 … +1.2 rad)
- `JointPositionController` eklentisi
- `ros_gz_bridge` üzerinden `/kamera_acisi` (Float64 ↔ gz.msgs.Double)
- `kamera_kontrol.py`: LIDAR'dan mesafe okuyup açı hesaplıyor
- FOV ayarı: 1.085 → 1.7 → **1.3 rad** (denemelerle bulundu)

**Literatürdeki karşılığı:** Active Perception / Viewpoint Planning.
Baseline karşılaştırması için sabit kamera (tilt = 0) sürümü saklanacak.

### 2C — Geometri ve Konumlandırma ☐ SIRADAKİ

Araştırmadan gelen asıl teknik katkı bu bölümde.

| # | İş | Not |
|---|---|---|
| 1 | **TF ağacı doğrulama** | `map → odom → base_link → camera_link` zinciri. Tilt açısı TF'e yansıyor mu? `JointStatePublisher` eklentisi var mı? |
| 2 | **Kamera iç parametreleri** | Kalibrasyona gerek yok — `/camera/camera_info` içinde `k` matrisi hazır |
| 3 | **Mesafe hesabı: oracle modu** | Robot konumu (`/odom`) + raf koordinatı (`envanter.json`) → dik mesafe. Kesin, gürültüsüz |
| 4 | **Mesafe hesabı: algı modu** | LIDAR ±60° yayına doğru uydurma (line fitting). Önce en küçük kareler, gürektiyse RANSAC |
| 5 | **Işın-düzlem kesişimi** | Piksel → ışın → yatay raf düzlemleriyle kesişim → **hangi kat?** Bu, projenin özgün teknik katkısı |

**Neden bu sıra:** TF önce, çünkü Sprint 3 (SLAM/Nav2) buna bağımlı ve
ray-plane hesabı da doğru TF olmadan yanlış sonuç verir. RANSAC en sona,
çünkü bilinen bir ortamda muhtemelen gereksiz — erken optimizasyon yapma.

### 2D — Nesne Tespiti ☐

| # | İş | Not |
|---|---|---|
| 1 | HSV renk tespiti | **Kırmızı iki aralık ister** (HSV çemberinde 0'ın iki yanında) |
| 2 | Boyut sınıflandırma | Piksel alanı + mesafe → büyük/orta/küçük |
| 3 | Kat ataması | 2C-5'teki ışın-düzlem sonucuyla birleştir |
| 4 | Tespit topic'i | `/tespitler` — renk, boyut, kat, konum |
| 5 | YOLOv8n (opsiyonel) | Genel nesne tanıma. 4 GB VRAM → nano/small, medium/large kullanma |

### 2E — Tarama Davranışı ☐

**Look-and-Move** (literatür terimi) durum makinesi:

```
1. Robot rafın önüne konumlan, dur
2. Mesafeyi hesapla (oracle veya algı)
3. Her kat için tilt açısını hesapla
4. Sırayla: açıya git → dur → net kare al → tespit et
5. Sonuçları envantere yaz
```

Hareket halinde tespit yapılmaz — motion blur tespiti bozar.

**Sprint 2 çıktısı:** Robot bir rafın önünde durup üç katı tarayabiliyor,
gördüğü nesnelerin rengini, boyutunu ve **hangi katta olduğunu** raporluyor.

---

## Sprint 3 — Navigasyon ve Semantik Harita ☐

| # | İş |
|---|---|
| 1 | `slam_toolbox` ile depoyu elle gezerek haritalama, haritayı kaydetme |
| 2 | Nav2 ayağa kaldırma, RViz'den hedef vererek doğrulama |
| 3 | AMCL ile kaydedilmiş harita üzerinde konumlandırma |
| 4 | **Adres veritabanı**: `A1-kat3-poz2 → (x, y, yaw)` eşlemesi |
| 5 | **Tarama pozisyonu**: her raf için robotun duracağı optimum nokta |
| 6 | Adres verince robotun oraya gidip yönelmesi |

**Kritik nokta:** Robotun rafa **dik** yönelmesi Sprint 2'de elle yapılıyordu.
Nav2 geldiğinde hedef poz (konum + yön) verilecek, sorun kendiliğinden çözülecek.

**Nav2 uyarıları:** koridor 3.2 m, yan geçitler 1.2 m — `inflation_radius`
buna göre ayarlanmalı, yoksa "no valid path" hatası alınır.

**Sprint 3 çıktısı:** "A1'e git" → robot otonom gidip rafa dik konumlanıyor.

---

## Sprint 4 — LLM Komut Çözümleme ☐

| # | İş |
|---|---|
| 1 | FastAPI servisi kurulumu |
| 2 | LLM sağlayıcı seçimi (Groq / OpenRouter / Google AI Studio) — rate limit ve kota kriterleri |
| 3 | Sağlayıcı çağrısını **tek fonksiyonda topla** (geçiş kolaylığı) |
| 4 | Doğal dil → yapılandırılmış sorgu (JSON) |
| 5 | Belirsizlik yönetimi: "kırmızı kutu" → 13 eşleşme var, ne yapmalı? |
| 6 | Hatalı/anlaşılmayan komut yönetimi |

**Sorgu tipleri:**

| Komut | Üretilecek sorgu |
|---|---|
| "A1'in 3. katına git" | `{tip: "adres", raf: "A1", kat: 3}` |
| "Kırmızı kutuyu bul" | `{tip: "arama", filtre: {renk: "kirmizi"}}` |
| "Kaç yeşil kutu var?" | `{tip: "sayim", filtre: {renk: "yesil"}}` |
| "Büyük mavi kutu neredeydi?" | `{tip: "arama", filtre: {renk: "mavi", boyut: "buyuk"}}` |

**Tasarım ilkesi:** Belirsizliği LLM çözer, kesinliği veritabanı sağlar.
LLM'e koordinat hesaplatma, veritabanına cümle yorumlatma.

**Sprint 4 çıktısı:** Cümle gir → temiz JSON sorgu çıkıyor.

---

## Sprint 5 — Entegrasyon ve Envanter ☐

| # | İş |
|---|---|
| 1 | Zinciri kapat: komut → LLM → sorgu → navigasyon → tarama → doğrulama |
| 2 | **Envanter kaydı**: robot dolaştıkça gördüklerini adresiyle biriktirir |
| 3 | Envanterden sorgu: "yeşil kutu nerede?" → aramadan cevap |
| 4 | Hedefe varınca görsel doğrulama |
| 5 | **Oracle vs algı karşılaştırması** — ground truth ile ölçüm |

**Envanter kaydı formatı:**
```json
{
  "adres": "A1-kat3-poz2",
  "renk": "kirmizi",
  "boyut": "buyuk",
  "konum": {"x": -4.6, "y": 3.9, "z": 1.68},
  "guven": 0.87,
  "zaman": "2026-08-06T15:30:00"
}
```

**Sprint 5 çıktısı:** Tam senaryo demosu. Projenin can alıcı noktası.

---

## Sprint 6 — Ölçüm, Cilalama, Sunum ☐

### Metrikler (ground truth sayesinde nicel sonuç)

| Metrik | Ne ölçer |
|---|---|
| Tespit precision / recall | Bulunan nesneler ÷ gerçekte var olanlar |
| Konumlandırma hatası | Tahmin edilen 3B konum ile gerçek konum arası Öklid mesafesi |
| Kat atama doğruluğu | Doğru kata atanan tespit oranı |
| Görev başarı oranı | Doğru nesnenin önüne varma oranı |
| Sorgu ayrıştırma doğruluğu | LLM JSON'u ÷ elle etiketlenmiş referans (50–100 komut) |
| Tarama süresi | Bir rafı tam taramak ne kadar sürüyor |

### Baseline karşılaştırmaları

| Karşılaştırma | Ne gösterir |
|---|---|
| **Tilt kamera vs sabit kamera** | Hareketli kameranın kazancı |
| Oracle modu vs algı modu | Algının maliyeti |
| LLM ayrıştırma vs anahtar kelime eşleme | LLM'in kazancı |

### Diğer

- Hata yönetimi (kutu bulunamadı, adres geçersiz, navigasyon başarısız)
- README, mimari diyagramı
- `NOTLAR.md` → Word belgesine derleme
- Demo videosu, sunum

---

## Sprint 7 (Opsiyonel) — Bonus ☐

Öncelik sırasıyla:
1. QR / barkod okuma (`pyzbar`) — kutu kimliği doğrulama
2. Frontier keşfi — otonom haritalama
3. VLM ile görsel doğrulama
4. OCR — etiket okuma (düşük çözünürlükte zor)
5. Çoklu hedef / görev sırası
6. Pan ekseni (sağa-sola) — tilt yeterli gelmezse

---

## Terminoloji (rapor için)

| Türkçe | İngilizce | Nerede kullanılıyor |
|---|---|---|
| Aktif algılama | Active Perception | Hareketli kamera yaklaşımı |
| Bakış açısı planlama | Viewpoint Planning | Tilt açısı hesabı |
| Bak-ve-hareket et | Look-and-Move | Tarama stratejisi |
| İğne deliği kamera modeli | Pinhole Camera Model | Piksel → ışın dönüşümü |
| Işın-düzlem kesişimi | Ray-Plane Intersection | Kat tespiti |
| İç parametre matrisi | Intrinsic Matrix | `/camera/camera_info` |
| Görüş engeli | Occlusion | Rafın kutuyu gizlemesi |
| Kesin doğru referans | Ground Truth | `envanter.json` |
| Semantik navigasyon | Semantic Navigation | Projenin genel çerçevesi |

---

## Riskler ve zaman kutusu

**Kritik uyarı:** Sprint 1-3 "altyapı", Sprint 4-6 "özgün katkı".
Altyapıda takılıp kalma. Sprint 3 iki haftayı aşarsa kapsamı daralt
(örneğin otonom keşfi bırak, elle haritalama yeterli).

Değerlendirilecek kısım algı + LLM entegrasyonu; uyumluluk savaşı değil.

**Açık riskler:**
- TF ağacında tilt açısı yansımıyorsa ray-plane hesabı yanlış çıkar
- Nav2 `inflation_radius` dar geçitlerde yol bulamayabilir
- LLM rate limit geliştirme sırasında sıkıntı yaratabilir
