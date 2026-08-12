# PROJE DOSYASI — Yapay Zeka Destekli Akıllı Depo Robotu Simülasyonu

**Son güncelleme:** 12 Ağustos 2026
**Durum:** Sprint 2D — Nesne Tespiti (devam ediyor) — HSV renk tespiti + kat
ataması çalışıyor, iki bilinen sınır durumu açık madde olarak kayıtlı (§12)

> Bu dosya projenin tam devir belgesidir. Yeni bir sohbete bu dosyayı vererek
> kaldığın yerden devam edebilirsin. Ne yapıldığı, neden yapıldığı, nasıl
> yapıldığı ve sırada ne olduğu burada yazılıdır.

---

# 1. PROJE TANIMI

## 1.1. Kim, ne için yapıyor

Bilgisayar mühendisliği 3. sınıf öğrencisiyim. Bir yazılım firmasında staj
yapıyorum ve bu proje staj çalışmam. Ofisteki kıdemli mühendis abim mentorluk
yapıyor, ancak o da simülasyon konusunda deneyimli değil — birlikte öğreniyoruz.

**Öğrenme tercihi:** Kodu kopyala-yapıştır yapmak yerine, her satırın ne
yaptığını anlayarak yazmak istiyorum. Açıklamalı anlatım tercih ediyorum.

## 1.2. Projenin amacı

Simülasyon ortamında çalışan, doğal dil komutlarını anlayan ve depo raflarındaki
nesneleri bulup konumlandırabilen otonom bir robot geliştirmek.

**Temel akış:**

```
Kullanıcı doğal dil komutu verir
        ↓
FastAPI servisi → LLM (Groq/OpenRouter) → yapılandırılmış JSON sorgu
        ↓
Sorgu tipine göre: adres bazlı mı, arama mı, envanter sorgusu mu?
        ↓
Nav2 ile hedefe otonom navigasyon
        ↓
Rafın önünde durup kamerayı dikey tarama (Look-and-Move)
        ↓
Renk + boyut tespiti, ışın-düzlem kesişimi ile kat tespiti
        ↓
Sonuç raporu + envanter kaydı
```

## 1.3. Projeyi özgün kılan fikirler

Bu fikirler geliştirme sürecinde ortaya çıktı ve projenin değerini belirliyor:

**a) Pasif envanter toplama.** Robot bir hedefe giderken yol boyunca gördüğü
*diğer* nesneleri de adresleriyle kaydeder. Zamanla deponun canlı 3B envanterini
çıkarır. Sonra "yeşil kutu nerede?" diye sorulduğunda aramaya çıkmaz, hafızasından
cevap verir.

**b) Çok modlu sorgulama.** Gerçek depoda "kırmızı kutuyu getir" anlamsızdır
(20 tane kırmızı kutu var). Sistem şu sorgu tiplerini desteklemeli:
- Adres bazlı: "A1'in 3. katına git"
- Arama: "kırmızı kutuyu bul" → birden fazla eşleşme, hangisi?
- Sayım: "kaç yeşil kutu var?"
- Tarif bazlı: "kırmızıydı, üstünde şu yazıyordu, adresini unuttum"

**c) Aktif algılama.** Sabit kamera dar koridorda rafın üç katını birden
göremiyor. Kameraya tilt ekseni eklendi; robot rafın önünde durup kamerayı
dikey tarayarak tüm katları inceliyor.

**d) Ground truth ile ölçülebilirlik.** Depodaki her kutunun gerçek konumu ve
özellikleri `envanter.json`'da kayıtlı. Bu sayede "algı %87 doğrulukla çalıştı"
gibi **nicel** sonuçlar raporlanabiliyor — "çalışıyor" demekten çok daha güçlü.

## 1.4. Tasarım ilkesi

**Belirsizliği LLM çözer, kesinliği veritabanı sağlar.**

LLM'e koordinat hesaplatma (uydurur), veritabanına cümle yorumlatma (yapamaz).
Her katman kendi işini yapar.

---

# 2. ORTAM VE DONANIM

## 2.1. Yazılım yığını

| Bileşen | Sürüm | Not |
|---|---|---|
| İşletim sistemi | Ubuntu 22.04 (Jammy) | |
| ROS | ROS 2 Humble Hawksbill | |
| Simülatör | Gazebo Sim 8.14.0 (Harmonic) | Classic 11 DEĞİL — bkz. §4.1 |
| Köprü | `ros-humble-ros-gzharmonic*` (apt) | `/opt/ros/humble` altında, çakışma yok |
| Robot | TurtleBot3 waffle_pi | Kaynaktan derlendi, `jazzy` branch |
| Python | 3.10 | setuptools **58.2.0**'a sabitlendi |
| Conda | Anaconda3 | `auto_activate_base false` yapıldı |

## 2.2. Donanım

| Bileşen | Değer | Not |
|---|---|---|
| İşlemci | Intel i5 10. nesil | Yeterli |
| Ekran kartı | NVIDIA GTX 1650 Ti | **nouveau** sürücü aktif, 4 GB VRAM |
| RAM | 16 GB | Yeterli |
| Performans | Gazebo %85–99 real-time | Sorun yok |

**Açık konu:** Laptop uzun süredir bakım görmedi (toz + termal macun).
~10 gün içinde yaptırılacak. O zamana kadar uzun süreli çalışmalarda
`watch -n 2 sensors` ile sıcaklık izlenmeli. CPU sürekli 90 °C+ ise mola verilmeli.

**nouveau sürücü notu:** Açık kaynak sürücü GPU sıcaklığını okuyamıyor (N/A) ve
3B performansı NVIDIA'nın kapalı sürücüsüne göre düşük. Şimdilik sorun yok;
YOLO eklenince performans sıkıntısı çıkarsa NVIDIA sürücüsüne geçiş değerlendirilir.

## 2.3. Paralel proje: İDA (kritik kısıt)

Aynı bilgisayarda bir takım projesi var: **İDA**, Gazebo Harmonic kullanıyor.
Takım kaptanı kurmuş. **Bu kurulum bozulmamalı.**

Bu kısıt projenin en önemli teknik kararını belirledi (§4.1).

**Ortam ayrımı:** `.bashrc`'de iki alias tanımlı, hiçbir proje ortamı otomatik
yüklenmiyor:

```bash
# İDA'ya çalışırken açılan terminalde:
ida

# Staj projesine çalışırken açılan terminalde:
staj
```

İki ortam birbirine karışmaz.

---

# 3. DOSYA YAPISI

```
~/staj_ws/                                  ← ROS 2 workspace
├── src/
│   ├── turtlebot3_simulations/             ← ROBOTIS deposu (YAMALI, bkz. §5)
│   │   └── turtlebot3_gazebo/
│   │       ├── CMakeLists.txt              ← Y1, Y2, Y3
│   │       ├── params/
│   │       │   └── turtlebot3_waffle_pi_bridge.yaml   ← Y4
│   │       ├── urdf/
│   │       │   └── turtlebot3_waffle_pi.urdf          ← Y9
│   │       └── models/turtlebot3_waffle_pi/
│   │           └── model.sdf               ← Y6, Y7, Y8
│   │
│   └── depo_robotu/                        ← BENİM PAKETİM (git ile takipli)
│       ├── package.xml
│       ├── setup.py
│       ├── NOTLAR.md                       ← sorunlar ve çözümleri
│       ├── KOMUTLAR.md                     ← hızlı komut referansı
│       ├── kurulum_notlari.docx            ← Sprint 1 raporu
│       ├── worlds/
│       │   └── depo.sdf                    ← depo dünyası
│       ├── launch/
│       │   └── depo.launch.py              ← ana launch dosyası
│       ├── araclar/
│       │   ├── kutu_uret.py                ← kutu üretme betiği
│       │   ├── kutular.sdf                 ← üretilen SDF (depo.sdf'e yapıştırılır)
│       │   └── envanter.json               ← GROUND TRUTH
│       └── depo_robotu/                    ← Python node'ları
│           └── kamera_kontrol.py
│
├── build/  install/  log/                  ← colcon çıktıları
│
└── (ayrıca) ~/girdap_ws/                   ← İDA projesi, DOKUNMA
```

## 3.1. Yedek dosyalar

| Yedek | İçerik |
|---|---|
| `~/.bashrc.yedek` | Temizlik öncesi |
| `model.sdf.yedek` | Orijinal robot modeli |
| `model.sdf.yedek2` | Renk + açı değişikliği sonrası |
| `turtlebot3_waffle_pi.urdf.yedek` | URDF revolute değişikliği öncesi |
| `depo.sdf.yedek` … `.yedek4` | Dünya dosyasının çeşitli aşamaları |
| `CMakeLists.txt.yedek` | Yamalar öncesi |

---

# 4. TEMEL TEKNİK KARARLAR

## 4.1. Gazebo Harmonic (Classic 11 değil)

**Karar:** Her iki proje de tek Gazebo (Harmonic) üzerinde yürütülüyor.

**Neden:** Gazebo Classic 11 kurulmaya çalışıldığında apt şu hatayı verdi:

```
gz-tools2 : Conflicts: gazebo (>= 11.0.0) but 11.10.2+dfsg-1 is to be installed
E: Error, pkgProblemResolver::Resolve generated breaks
```

Harmonic'in bileşeni `gz-tools2`, Classic 11 ile aynı sistemde bulunmayı
reddediyor. Classic kurulsaydı apt İDA'nın Harmonic kurulumunu sökecekti.

**Sonucu:** `turtlebot3_simulations` apt yerine kaynaktan, `jazzy` branch'inden
derlendi. Bu, Humble ile resmi olarak eşleşmeyen bir kombinasyon olduğu için
Y1–Y3 yamaları gerekti.

**Yan fayda:** İDA ve staj projesi aynı altyapıyı kullanıyor; birinde öğrenilen
`ros_gz` bilgisi diğerine aktarılıyor. Ayrıca Gazebo Classic kullanım ömrünü
doldurdu, Harmonic gelecekte de destekleniyor.

## 4.2. Robot: TurtleBot3 waffle_pi

`burger` değil `waffle_pi` seçildi çünkü **kamera** gerekiyor (burger'da yok).

**Bileşenler:**

| Bileşen | Detay | ROS 2 topic |
|---|---|---|
| 2D LIDAR (LDS-01) | 360 ışın, 1° aralık, 0.12–3.5 m, yerden ~0.18 m | `/scan` |
| RGB kamera | 640×480, 30 FPS, FOV **1.3 rad**, yerden ~0.11 m | `/camera/image_raw` |
| Kamera bilgisi | İç parametre matrisi (`k`) | `/camera/camera_info` |
| IMU | 3 eksen | `/imu` |
| Tekerlek enkoderleri | Odometri | `/odom`, `/joint_states` |
| **Kamera tilt servosu** | Eklendi, -0.5 … +1.2 rad | `/kamera_acisi` |
| Diferansiyel tahrik | Yerinde 360° dönebilir | `/cmd_vel` |

**Derinlik kamerası YOK.** Bu önemli bir kısıt — 3B konumlandırma sadece RGB +
LIDAR + bilinen geometri ile yapılacak.

**TF ağacı:**

```
base_footprint
└── base_link
    ├── base_scan (LIDAR)
    ├── imu_link
    ├── wheel_left_link, wheel_right_link
    ├── caster_back_left_link, caster_back_right_link
    └── camera_link          ← REVOLUTE (tilt), TF'e yansıyor ✅
        └── camera_rgb_frame
            └── camera_rgb_optical_frame
```

## 4.3. Depo tasarımı

**Boyut:** 12 × 12 m, duvarlar ±6 m'de, 2 m yüksek
**Kapı:** Güney duvarında 4 m boşluk (x: -2 … +2)
**Robot başlangıcı:** (0, -5) — kapının içi

**9 raf, 3×3 ızgara:**

| Adres | Konum (x, y) | Bakış yönü |
|---|---|---|
| A1 | (-4, 4) | güney |
| A2 | (0, 4) | güney |
| A3 | (4, 4) | güney |
| B1 | (-4, 0) | güney |
| B2 | (0, 0) | güney |
| B3 | (4, 0) | güney |
| C1 | (-4, -4) | kuzey |
| C2 | (0, -4) | kuzey |
| C3 | (4, -4) | kuzey |

**Raf ölçüleri:** 2.8 × 0.8 × 1.5 m, 3 kat
**Kat yüzeyleri:** z = 0.48 / 1.03 / 1.53 m
**Koridorlar:** sıralar arası 3.2 m, yan geçitler 1.2 m

**Tasarım notları:**
- Rafın `collision`'ı **tek blok** (2.8 × 0.8 × 1.5), `visual`'ı çok parçalı
  (mavi direkler + turuncu tablalar). Hem performanslı hem güzel.
  Robot raf altına giremez — kasıtlı, gerçek depo robotları da giremez.
- Model seviyesinde `<pose>` kullanıldı; iç parçalar ona göreli.
  Rafın yerini değiştirmek için tek satır yeterli.
- **Tek yönlü bakış:** Her rafın bir "ön yüzü" var. B sırası iki koridor
  arasında ama kutular sadece güney kenara yaslı. Robot doğru koridordan
  geçmeli — bu bilgi `envanter.json`'da (`yon` alanı) var.
- Çift taraflı yapmak istenirse: betikte `RAFLAR` sözlüğüne `"cift"` yönü
  eklenip doldurma fonksiyonu güncellenir. **Node'lar değişmez** çünkü yön
  bilgisini JSON'dan okuyorlar. (Veriyi koddan ayırma ilkesi.)

## 4.4. Kutular

`araclar/kutu_uret.py` betiği üretiyor. ~96 kutu, ~50 karton + ~46 renkli.

**Kutu tipleri:**

| Tip | Boyut (en × derinlik × yükseklik) |
|---|---|
| büyük | 0.55 × 0.60 × 0.42 |
| orta | 0.42 × 0.50 × 0.35 |
| küçük | 0.30 × 0.35 × 0.28 |

**Renkler:** kırmızı, yeşil, mavi, sarı, karton (kahverengi)

**Yerleşim mantığı:**
- Kutular rafın **ön kenarına yaslı** (gerçek depolarda böyle — alan verimliliği)
- **İki uçtan içeri** doğru dizilir, ortada doğal boşluk kalır
- Her rafın her katında 2–5 kutu, rastgele boyut ve renk
- Çoğu karton, azı renkli → robot "kırmızı kutu" ararken kartonlar arasından
  ayırt etmek zorunda (gerçekçi zorluk)

**Kutu z hesabı:** `kat_yüzeyi + kutu_yüksekliği / 2`

**Betik ayarları** (üst kısımda, kolayca değiştirilebilir):

```python
TOHUM = 42                        # aynı sayı = aynı dizilim
RENKLI_ORAN = 0.35
SOL_KUTU_ADEDI = (1, 3)
SAG_KUTU_ADEDI = (1, 3)
KUTU_ARASI_BOSLUK = (0.05, 0.25)
ORTA_MIN_BOSLUK = 0.15
```

**Çıktılar:**
- `kutular.sdf` → `depo.sdf`'e yapıştırılır
- `envanter.json` → **ground truth**, her kutunun adresi/rengi/boyutu/konumu

**envanter.json kayıt formatı:**

```json
{
  "id": "kutu_A1_k1_p2",
  "adres": "A1-kat1-poz2",
  "raf": "A1", "kat": 1, "pozisyon": 2,
  "renk": "kirmizi", "boyut": "buyuk",
  "konum": {"x": -4.605, "y": 3.9, "z": 0.69}
}
```

## 4.5. Hareketli kamera (aktif algılama)

**Problem:** Koridor 3.2 m, robot rafa en fazla ~1.6 m yaklaşabiliyor.
Kamera yerden sadece 0.11 m'de. Sabit kamerayla rafın üç katı birden görülemiyor.

**Denenen ve elenen çözümler:**

| Deneme | Sonuç |
|---|---|
| Kamera 20° sabit yukarı eğim | Uzaktan (≈4 m) çalışıyor, koridordan çalışmıyor |
| FOV 1.085 → 1.7 rad (≈97°) | Her şey kadraja giriyor ama nesneler çok küçülüyor |
| "Robot 2 m geri çekilsin" | **Elendi** — gerçek depoda boş alan yoktur, her metrekare değerli |
| Yük platformu ekleme | **Elendi** — LIDAR ve kamerayı kapatma riski |

**Uygulanan çözüm:** `camera_joint` `fixed` → `revolute` yapıldı.

```
Eksen: y (tilt), <xyz>0 -1 0</xyz>
Sınırlar: -0.5 … +1.2 rad
Kontrolcü: gz-sim-joint-position-controller-system
Topic: /kamera_acisi (Float64 ↔ gz.msgs.Double)
FOV: 1.3 rad (deneme sonucu seçildi)
```

**Pan (sağa-sola) eklenmedi.** Robot zaten yerinde 360° dönebiliyor.
Tilt yeterli gelmezse ileride değerlendirilir.

**Kazanım:** Kameranın açısı bilindiği için, görülen nesnenin **hangi katta**
olduğu hesaplanabiliyor. Bu, `A1-kat3-kırmızı kutu` şeklinde 3B adreslemeyi
mümkün kılıyor — sabit kamerayla imkânsızdı.

## 4.6. Mesafe hesabı: oracle vs algı

İki yaklaşım da geçerli, ikisi de uygulanacak:

**Oracle modu (kesin):** Robot konumu (`/odom`) + raf koordinatı
(`envanter.json`) → dik mesafe. Gürültüsüz, hızlı. Sprint 3'te Nav2 zaten
"hangi rafa gidiyorum" bilgisini taşıyacak.

**Algı modu (gerçekçi):** LIDAR ±60° yayına doğru uydurma (line fitting).
Haritada olmayan engelleri de görür. Önce en küçük kareler denenecek,
gürültü sorun olursa RANSAC'a geçilecek.

**Neden ikisi de:** Sprint 6'da karşılaştırma tabanı (baseline) olarak
kullanılacak — "algının maliyeti nedir?" sorusunun cevabı.

---

# 5. UYGULANAN YAMALAR (KRİTİK)

> `~/staj_ws` silinip yeniden kurulursa bu yamaların **hepsi tekrar**
> uygulanmalıdır. Aksi halde derleme başarısız olur veya sistem yanlış çalışır.
> Bu dosyalar ROBOTIS deposuna ait, `git pull` de üzerine yazabilir.

| # | Dosya | Konu |
|---|---|---|
| Y1 | `turtlebot3_gazebo/CMakeLists.txt` | vendor paketleri kaldırıldı |
| Y2 | `turtlebot3_gazebo/CMakeLists.txt` | `find_package` sürümlendi |
| Y3 | `turtlebot3_gazebo/CMakeLists.txt` | link hedefleri sürümlendi |
| Y4 | `params/turtlebot3_waffle_pi_bridge.yaml` | TwistStamped → Twist |
| Y5 | `~/.bashrc` (`staj` alias) | mesh yolu eklendi |
| Y6 | `models/.../model.sdf` | gövde rengi turuncu |
| Y7 | `models/.../model.sdf` | kamera FOV 1.3 |
| Y8 | `models/.../model.sdf` | tilt joint + kontrolcü + JointStatePublisher |
| Y9 | `urdf/turtlebot3_waffle_pi.urdf` | `camera_joint` revolute |

## Y1 — vendor paketlerinin kaldırılması

**Hata:**
```
CMake Error at CMakeLists.txt:29 (find_package):
  Could not find a package configuration file provided by "gz_math_vendor"
```

**Sebep:** `gz_math_vendor` / `gz_sim_vendor` / `gz_plugin_vendor` paketleri
ROS 2 Jazzy'ye özgü sarmalayıcılar. Humble'da bu katman yok. Kütüphaneler
sistemde mevcut ama farklı isimle: `gz-math7`, `gz-sim8`, `gz-plugin2`.

```bash
cd ~/staj_ws/src/turtlebot3_simulations/turtlebot3_gazebo
cp CMakeLists.txt CMakeLists.txt.yedek

sed -i '/find_package(gz_math_vendor REQUIRED)/d; \
        /find_package(gz_sim_vendor REQUIRED)/d; \
        /find_package(gz_plugin_vendor REQUIRED)/d' CMakeLists.txt
```

## Y2 — find_package sürümleme

```bash
sed -i 's/find_package(gz-math REQUIRED)/find_package(gz-math7 REQUIRED)/; \
        s/find_package(gz-sim REQUIRED)/find_package(gz-sim8 REQUIRED)/; \
        s/find_package(gz-plugin REQUIRED)/find_package(gz-plugin2 REQUIRED)/' CMakeLists.txt
```

Sistemdeki sürümleri görmek için:
```bash
ls /usr/lib/x86_64-linux-gnu/cmake/ | grep -i "gz-"
```

## Y3 — link hedefleri sürümleme

**Hata:**
```
CMake Error at CMakeLists.txt:66 (add_library):
  Target "obstacles" links to target "gz-sim::gz-sim" but the target was not found.
```

```bash
sed -i 's/gz-sim::gz-sim/gz-sim8::gz-sim8/g; \
        s/gz-math::gz-math/gz-math7::gz-math7/g; \
        s/gz-plugin::/gz-plugin2::/g' CMakeLists.txt
```

Bu üç yamadan sonra: `Summary: 3 packages finished`

## Y4 — cmd_vel mesaj tipi

**Belirti:** Gazebo ve robot açılıyor, teleop çalışıyor ama robot kımıldamıyor.

**Teşhis:**
```
$ ros2 topic info /cmd_vel
Type: ['geometry_msgs/msg/Twist', 'geometry_msgs/msg/TwistStamped']
Publisher count: 1
Subscription count: 1
```

Aynı topic'te iki farklı tip. `teleop_keyboard` düz `Twist` yayınlıyor,
köprü `TwistStamped` bekliyor.

**Doğrulama testi** (bu çalışıyorsa teşhis kesin):
```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/TwistStamped "{twist: {linear: {x: 0.2}}}" --rate 10
```

**Çözüm:**
```bash
cd ~/staj_ws/src/turtlebot3_simulations/turtlebot3_gazebo/params
sed -i '32s|geometry_msgs/msg/TwistStamped|geometry_msgs/msg/Twist|' turtlebot3_waffle_pi_bridge.yaml
```

Paket geliştiricileri bu durumu öngörmüş — `burger_bridge.yaml`'da ilgili
satırın yanında `# If you use Twist, you need to change the type to Twist` yorumu var.

## Y5 — mesh yolu

**Belirti:** Fizik ve sensörler çalışıyor, robot Entity Tree'de var ama görünmüyor.
```
[Err] Unable to find file with URI [model://turtlebot3_common/meshes/bases/waffle_pi_base.stl]
```

**Çözüm:** `~/.bashrc` içindeki `staj` alias'ına eklendi:
```bash
export GZ_SIM_RESOURCE_PATH=~/staj_ws/install/turtlebot3_gazebo/share/turtlebot3_gazebo/models:$GZ_SIM_RESOURCE_PATH
```

## Y6 — gövde rengi

`model.sdf` satır 41-42 (ana gövde):
```bash
sed -i '41s/0.3 0.3 0.3 1.0/0.9 0.45 0.05 1.0/; 42s/0.3 0.3 0.3 1.0/0.9 0.45 0.05 1.0/' model.sdf
```
Turuncu = depo aracı görünümü. Tekerlekler koyu bırakıldı.

## Y7 — kamera FOV

```bash
sed -i 's|<horizontal_fov>1.085595</horizontal_fov>|<horizontal_fov>1.3</horizontal_fov>|' model.sdf
```

## Y8 — tilt mekanizması (3 parça)

**a) `camera_link`'e kütle ver** (satır ~356). Boş `<link name="camera_link"/>`
yerine:

```xml
<link name="camera_link">
  <inertial>
    <pose>0.073 -0.011 0.084 0 0 0</pose>
    <mass>0.05</mass>
    <inertia>
      <ixx>0.00001</ixx><ixy>0.0</ixy><ixz>0.0</ixz>
      <iyy>0.00001</iyy><iyz>0.0</iyz><izz>0.00001</izz>
    </inertia>
  </inertial>
</link>
```

*Neden:* Fizik motoru dönebilen parçanın kütlesini bilmek zorunda.

**b) `camera_joint`'i revolute yap:**

```xml
<joint name="camera_joint" type="revolute">
  <parent>base_link</parent>
  <child>camera_link</child>
  <pose>0.073 -0.011 0.084 0 0 0</pose>
  <axis>
    <xyz>0 -1 0</xyz>
    <limit>
      <lower>-0.5</lower><upper>1.2</upper>
      <effort>10</effort><velocity>2.0</velocity>
    </limit>
    <dynamics>
      <damping>0.05</damping><friction>0.01</friction>
    </dynamics>
  </axis>
</joint>
```

*Not:* Pose'daki pitch **sıfırlandı** (önceden -0.349 sabit eğim vardı).
Artık açıyı joint kontrol ediyor. `damping` ve `friction` titremeyi önlüyor.

**c) Kontrolcü eklentisi** (`DiffDrive` yanına):

```xml
<plugin filename="gz-sim-joint-position-controller-system"
        name="gz::sim::systems::JointPositionController">
  <joint_name>camera_joint</joint_name>
  <topic>kamera_acisi</topic>
  <p_gain>2.0</p_gain>
  <i_gain>0.05</i_gain>
  <d_gain>0.1</d_gain>
</plugin>
```

**d) `JointStatePublisher`'a kamera ekle** (satır ~539'dan sonra):

```bash
sed -i '539a\      <joint_name>camera_joint</joint_name>' model.sdf
```

*Neden:* Bu olmadan kamera açısı `/joint_states`'e düşmez, TF tilt'i görmez.

## Y9 — URDF revolute (TF için kritik)

**Belirti:** `/joint_states` kamera açısını doğru gösteriyor (0.81 rad) ama
TF hâlâ sıfır dönme gösteriyor.

**Sebep:** `robot_state_publisher` `model.sdf`'i değil, `urdf/turtlebot3_waffle_pi.urdf`
dosyasını okuyor. Orada `camera_joint` hâlâ `fixed` olarak tanımlıydı; RSP
"bu sabit joint" deyip açı bilgisini yok sayıyordu.

**Çözüm** — `urdf/turtlebot3_waffle_pi.urdf` satır ~227:

```xml
<joint name="camera_joint" type="revolute">
  <origin xyz="0.073 -0.011 0.084" rpy="0 0 0"/>
  <parent link="base_link"/>
  <child link="camera_link"/>
  <axis xyz="0 -1 0"/>
  <limit lower="-0.5" upper="1.2" effort="10" velocity="2.0"/>
</joint>
```

**KRİTİK:** URDF'teki `axis` ve `limit` değerleri `model.sdf`'tekiyle
**birebir aynı** olmalı. Farklıysa Gazebo bir açıya götürür, TF başka açı
gösterir — teşhis edilmesi çok zor bir hata olur.

**Doğrulama:**
```bash
ros2 topic pub --once /kamera_acisi std_msgs/msg/Float64 "{data: 0.8}"
ros2 run tf2_ros tf2_echo base_link camera_link
# Beklenen: RPY (degree) [0.000, -46.169, 0.000]  ← pitch sıfır DEĞİL
```

---

# 6. ÇÖZÜLEN DİĞER SORUNLAR

## S1 — setuptools sürümü çok yeni

**Belirti:**
```
error: option --editable not recognized
error: option --uninstall not recognized
```
`colcon build` başarısız, `setup.py` dosyasında hiçbir hata yok.

**Sebep:** ROS 2 Humble'ın `ament_python` derleyicisi eski `setup.py develop`
yöntemini kullanır; bu yöntem setuptools 64'te kaldırıldı. Sistemde 82.0.1 vardı
(kullanıcı bazlı, `~/.local/`).

**Çözüm:**
```bash
cd ~/staj_ws && rm -rf build/depo_robotu install/depo_robotu
pip3 install --user setuptools==58.2.0
```

**Not:** İleride yeni setuptools gerektiren bir iş olursa (ultralytics vb.)
sistem geneli yükseltmek yerine `venv` kullanılmalı.

## S2 — Kendi dünyam yüklenmiyor

**Belirti:** `ros2 launch depo_robotu depo.launch.py` çalışıyor ama Entity Tree'de
`ground_plane` / `sun` görünüyor (TurtleBot3'ün varsayılan dünyası).

**Sebep:** `empty_world.launch.py` içinde dünya yolu **sabit kodlanmış**,
argüman kabul etmiyor.

**Çözüm:** Kendi `depo.launch.py` sıfırdan yazıldı. ROBOTIS'in alt-launch
dosyaları (`robot_state_publisher.launch.py`, `spawn_turtlebot3.launch.py`)
hâlâ çağrılıyor, sadece dünya yolu değişti.

**Ek notlar:**
- `<world name="default">` olarak bırakıldı — `spawn_turtlebot3.launch.py`
  bu ismi bekliyor. `depo` yapılırsa robot dünyaya eklenemiyor.
- `AppendEnvironmentVariable` (model yolu) eylemi listenin **başına** alındı.
  ROBOTIS'te en sonda; yarış durumu yaratabiliyor.

## S3 — Eski Gazebo süreçleri

**Belirti:** Sahne boş görünüyor, Entity Tree çelişkili, değişiklikler yansımıyor.

**Sebep:** `Ctrl+C` her zaman tüm süreçleri öldürmüyor. Gazebo sunucu (`-s`) ve
arayüz (`-g`) ayrı süreçler; yeni arayüz eski sunucuya bağlanabiliyor.

**Çözüm:**
```bash
pkill -f "gz sim"; pkill -f ruby
pkill -f parameter_bridge; pkill -f robot_state_publisher
sleep 2
```

**Alışkanlık:** Garip bir davranış görüldüğünde ilk iş bu.

## S4 — teleop KeyError

```
KeyError: 'TURTLEBOT3_MODEL'
```
O terminalde `staj` yazılmamış. **Her yeni terminalde önce `staj`.**

## S5 — Robot kendi kendine dönüyor gibi

Teleop'ta kalıntı açısal hız var. `s` veya boşluk = force stop.

## S6 — LIDAR "ölçüm yok" diyor ama önümde raf var

**Belirti:** `kamera_kontrol` node'u "Onumde olcum yok" uyarısı veriyor.

**Teşhis:** LIDAR 360 ışın yayınlıyor ama node sadece ortadaki 11 ışına bakıyordu.
Robot rafa **dik** durmuyorsa (örneğin 63° açıyla), merkez ışınlar koridor
boyunca gidip 3.5 m menzilde bir şey bulamıyor.

**Robot yönünü kontrol etme:**
```bash
ros2 topic echo /odom --once | head -20
# quaternion'dan yaw: yaw = 2 * atan2(q.z, q.w)
```

**Çözüm:** `scan_geldi` fonksiyonu ±60° yaya genişletildi ve ortalama yerine
**minimum** alınıyor:

```python
def scan_geldi(self, mesaj):
    n = len(mesaj.ranges)
    yariyay = int(math.radians(60) / mesaj.angle_increment)
    gecerli = []
    for i in range(-yariyay, yariyay + 1):
        d = mesaj.ranges[i % n]
        if (not math.isinf(d) and not math.isnan(d)
                and mesaj.range_min < d < mesaj.range_max):
            gecerli.append(d)
    self.mesafe = min(gecerli) if gecerli else None
```

**Kalan zaaf:** Minimum aldığımız için yandaki bir kutu/duvar "raf" sanılabilir.
Sprint 3'te oracle moduna geçilince bu belirsizlik kalkacak.

## S7 — Kutular görünmüyor (görüş engeli)

**Belirti:** Gazebo'da kutu var ama kamera görüntüsünde yok.

**Sebepler ve çözümler:**
- Kutular rafın ortasında duruyordu → **ön kenara yaslandı** (gerçek depolarda
  böyle, alan verimliliği)
- Kutular çok küçüktü (30 cm) → **farklı boyutlar** eklendi (28–42 cm)
- Robot rafa çok yakınsa üstteki rafın alt yüzeyi görüşü kesiyor →
  Look-and-Move stratejisiyle uygun mesafe seçilecek

**Geometrik doğrulama yapıldı:** FOV 1.7 rad iken dikey görüş 81°, 2 m
mesafede kadraj -0.86 … 2.97 m arasını kapsıyor — üç kat da içeride. Yani
geometrik engel yoktu, sorun nişan almadaydı. FOV 1.3'e çekildi ki nesneler
daha büyük görünsün.

---

# 7. YOL HARİTASI

## Sprint 1 — Altyapı ✅ TAMAMLANDI

- `.bashrc` temizliği, `ida` / `staj` ortam ayrımı
- Sızmış API anahtarı iptal edildi
- Gazebo Classic yerine Harmonic kararı
- `turtlebot3_simulations` kaynaktan derleme + Y1–Y5
- Robot çalışır durumda: sürülüyor, sensörleri yayın yapıyor
- Git kurulumu, `kurulum_notlari.docx`

## Sprint 2 — Ortam ve Algı 🔄 DEVAM EDİYOR

### 2A — Ortam ✅

- `depo_robotu` ROS 2 paketi
- `depo.sdf`: 12×12 m depo, 9 raf, duvarlar, kapı
- `depo.launch.py`
- `kutu_uret.py` → 96 kutu + `envanter.json`
- setuptools 58.2.0

### 2B — Hareketli kamera ✅

- Tilt joint, kontrolcü, köprü, FOV ayarı (Y6–Y9)
- `kamera_kontrol.py`: LIDAR mesafesinden açı hesabı
- TF tilt yansıması doğrulandı

### 2C — Geometri ve konumlandırma 🔄 KISMEN TAMAMLANDI (4-5 açık)

| # | İş | Durum |
|---|---|---|
| 1 | TF ağacı doğrulama | ✅ |
| 2 | Kamera iç parametreleri | ✅ hazır (`/camera/camera_info`, kalibrasyon gerekmez) |
| 3 | **Işın-düzlem kesişimi** | ✅ TAMAMLANDI — hem basit (Aşama B, `kat_tespit.py`) hem piksel bazlı (Aşama A, `piksel_kat_tespit.py` → `kutu_tespit.py`) |
| 4 | Mesafe: oracle modu | ☐ hâlâ yapılmadı — bilinçli erteleme, bkz. §12 |
| 5 | Mesafe: algı modu (line fitting) | ☐ hâlâ yapılmadı — bilinçli erteleme, bkz. §12 |

### 2D — Nesne tespiti 🔄 DEVAM EDİYOR

| # | İş | Not |
|---|---|---|
| 1 | HSV renk tespiti | **Kırmızı İKİ aralık ister** (HSV çemberinde 0'ın iki yanında) |
| 2 | Boyut sınıflandırma | piksel alanı + mesafe → büyük/orta/küçük |
| 3 | Kat ataması | 2C-3 ile birleştir |
| 4 | `/tespitler` topic'i | renk, boyut, kat, konum |
| 5 | YOLOv8n (opsiyonel) | 4 GB VRAM → nano/small, medium/large **kullanma** |

### 2E — Tarama davranışı (Look-and-Move) ☐

```
1. Robot rafın önüne konumlan, DUR
2. Mesafeyi hesapla (oracle veya algı)
3. Her kat için tilt açısını hesapla
4. Sırayla: açıya git → DUR → net kare al → tespit et
5. Sonuçları envantere yaz
```

Hareket halinde tespit yapılmaz — motion blur tespiti bozar.

**Sprint 2 çıktısı:** Robot bir rafın önünde durup üç katı tarayabiliyor,
gördüğü nesnelerin rengini, boyutunu ve **hangi katta olduğunu** raporluyor.

## Sprint 3 — Navigasyon ve semantik harita ☐

| # | İş |
|---|---|
| 1 | `slam_toolbox` ile haritalama, haritayı kaydetme |
| 2 | Nav2 ayağa kaldırma, RViz'den hedef vererek doğrulama |
| 3 | AMCL ile kayıtlı harita üzerinde konumlandırma |
| 4 | Adres veritabanı: `A1-kat3-poz2 → (x, y, yaw)` |
| 5 | Tarama pozisyonu: her raf için optimum durma noktası |
| 6 | Adres verince robotun gidip **rafa dik yönelmesi** |

**Kritik:** Robotun rafa dik yönelmesi şu an elle yapılıyor. Nav2'de hedef poz
(konum + yön) verilecek, sorun kendiliğinden çözülecek.

**Nav2 uyarısı:** Koridor 3.2 m, yan geçitler 1.2 m. `inflation_radius` buna
göre ayarlanmalı, yoksa "no valid path" hatası alınır.

## Sprint 4 — LLM komut çözümleme ☐

| # | İş |
|---|---|
| 1 | FastAPI servisi |
| 2 | LLM sağlayıcı seçimi (Groq / OpenRouter / Google AI Studio) |
| 3 | Sağlayıcı çağrısını **tek fonksiyonda topla** |
| 4 | Doğal dil → yapılandırılmış JSON sorgu |
| 5 | Belirsizlik yönetimi: "kırmızı kutu" → 13 eşleşme, ne yapmalı? |
| 6 | Hatalı komut yönetimi |

**Sorgu tipleri:**

| Komut | Üretilecek sorgu |
|---|---|
| "A1'in 3. katına git" | `{tip: "adres", raf: "A1", kat: 3}` |
| "Kırmızı kutuyu bul" | `{tip: "arama", filtre: {renk: "kirmizi"}}` |
| "Kaç yeşil kutu var?" | `{tip: "sayim", filtre: {renk: "yesil"}}` |
| "Büyük mavi kutu neredeydi?" | `{tip: "arama", filtre: {renk: "mavi", boyut: "buyuk"}}` |

**Güvenlik:** API anahtarı `.env`'de tutulacak, `.bashrc`'ye **asla** yazılmayacak,
`.gitignore`'a eklenecek. (Sprint 1'de bu konuda bir olay yaşandı.)

## Sprint 5 — Entegrasyon ve envanter ☐

| # | İş |
|---|---|
| 1 | Zinciri kapat: komut → LLM → sorgu → navigasyon → tarama → doğrulama |
| 2 | Envanter kaydı: robot dolaştıkça gördüklerini adresiyle biriktirir |
| 3 | Envanterden sorgu: "yeşil kutu nerede?" → aramadan cevap |
| 4 | Hedefe varınca görsel doğrulama |
| 5 | Oracle vs algı karşılaştırması |

**Envanter kaydı formatı:**
```json
{
  "adres": "A1-kat3-poz2",
  "renk": "kirmizi", "boyut": "buyuk",
  "konum": {"x": -4.6, "y": 3.9, "z": 1.68},
  "guven": 0.87,
  "zaman": "2026-08-06T15:30:00"
}
```

**Sprint 5 çıktısı:** Tam senaryo demosu. **Projenin can alıcı noktası.**

## Sprint 6 — Ölçüm, cilalama, sunum ☐

**Metrikler** (ground truth sayesinde nicel):

| Metrik | Ne ölçer |
|---|---|
| Tespit precision / recall | Bulunan ÷ gerçekte var olan |
| Konumlandırma hatası | Tahmin ile gerçek konum arası Öklid mesafesi |
| Kat atama doğruluğu | Doğru kata atanan tespit oranı |
| Görev başarı oranı | Doğru nesnenin önüne varma oranı |
| Sorgu ayrıştırma doğruluğu | LLM JSON'u ÷ elle etiketlenmiş referans (50–100 komut) |
| Tarama süresi | Bir rafı tam taramak ne kadar sürüyor |

**Baseline karşılaştırmaları:**

| Karşılaştırma | Ne gösterir |
|---|---|
| Tilt kamera vs **sabit kamera** | Hareketli kameranın kazancı |
| Oracle modu vs algı modu | Algının maliyeti |
| LLM ayrıştırma vs anahtar kelime eşleme | LLM'in kazancı |

> **ÖNEMLİ:** Sabit kamera (tilt=0) sürümü baseline için saklanmalı, silinmemeli.

> **ÖNEMLİ (precision/recall payda tasarımı):** `kutu_tespit.py`'nin tespitleri
> rafa göre kapsamlanmamış (shelf-scoped değil) — bkz. §12 AÇIK MADDE 2
> güncellemesi ve `NOTLAR.md` SORUN 12. Geniş FOV komşu rafların (örn. B2
> taranırken A2/C2) aynı kat yüksekliğindeki kutularını da yakalayabiliyor.
> Precision/recall hesaplanırken bu "hedeflenmeyen rafa ait tespit"ler ham
> haliyle paydaya (bulunan tespit sayısı) girip precision'ı yapay şekilde
> düşürebilir veya recall'u yanıltıcı şekilde şişirebilir (aynı renkte bir
> kutu doğru raftan değil komşu raftan "bulundu" sayılabilir — Sprint 2E'de
> tam olarak bu yaşandı: B2 testinde 8/8 renk eşleşti ama 25 tespit hiçbir
> B2 kutusuyla eşleşmedi). Ölçüm mantığı buna göre tasarlanmalı: sadece
> hedeflenen raf adresine (bilinen x,y aralığına) düşen tespitler sayılmalı,
> ya da bu ayrım çözülene kadar metrik raporunda "kapsam dışı tespit" ayrı
> bir sütun olarak tutulmalı (bkz. `tarama_kontrol.py`'nin `fazla_tespit`
> alanı, mevcut kaba yaklaşım).

**Diğer:** hata yönetimi, README, mimari diyagramı, `NOTLAR.md` → Word,
demo videosu, sunum.

## Sprint 7 (opsiyonel) — Bonus ☐

Öncelik sırasıyla:
1. QR / barkod okuma (`pyzbar`) — kutu kimliği doğrulama
2. Frontier keşfi — otonom haritalama
3. VLM ile görsel doğrulama
4. OCR — etiket okuma (düşük çözünürlükte zor)
5. Çoklu hedef / görev sırası
6. Pan ekseni (sağa-sola)

---

# 8. SIRADAKİ İŞ: IŞIN-DÜZLEM KESİŞİMİ

## 8.1. Amaç

Kameranın gördüğü bir noktanın **hangi rafı katında** olduğunu hesaplamak.

## 8.2. Matematik

Işın bir noktadan çıkar ve bir yöne gider:
```
P(t) = kamera_konumu + t · yön_vektörü        (t ≥ 0)
```

Raf katları yatay düzlemler:
```
z = 0.48   (kat 1)
z = 1.03   (kat 2)
z = 1.53   (kat 3)
```

Kesişim:
```
kamera_z + t · yön_z = kat_z
t = (kat_z − kamera_z) / yön_z
```

`t` bulununca kesişim noktasının x, y'si hesaplanır. Sonra "bu nokta rafın
sınırları içinde mi?" kontrol edilir.

## 8.3. İki aşama

**Aşama B (önce bu):** Kameranın **merkez ışını** hangi katı kesiyor?
Nesne tespitine gerek yok, sadece "kamera şu an hangi kata bakıyor?" sorusu.
TF'in doğru çalıştığını da kanıtlar.

**Aşama A (sonra):** Görüntüdeki her tespit edilen nesnenin **pikselinden**
ışın atıp kat bulmak. Pinhole model + `camera_info`'daki `k` matrisi gerekir:
```
d_cam = K⁻¹ · [u, v, 1]ᵀ
```
Sonra bu vektör TF ile dünya çerçevesine dönüştürülür.

## 8.4. Tasarım kararları (B için)

**Hangi çerçeve?**
- `camera_rgb_optical_frame` → görüntü işleme standardı (z ileri, x sağ, y aşağı).
  İleride piksel hesabı için doğru olan bu.
- `camera_link` → daha sezgisel eksenler. **Başlangıç için bu kullanılacak.**

**Hangi referans?**
- Kat yükseklikleri dünya zemininden ölçülü (z = 0.48 vb.)
- Robot sabitken `base_footprint` yeterli
- Sprint 3'te `map` / `odom` çerçevesine geçilecek

**TF'ten dönüşüm alma:** `tf2_ros` kütüphanesinin `Buffer` ve
`TransformListener` sınıfları kullanılacak.

## 8.5. Yazılacak node

`depo_robotu/kat_tespit.py`
- TF'ten kamera konumu ve yönünü al
- Merkez ışınını hesapla
- Üç kat düzlemiyle kesiştir
- Hangi katı kestiğini yayınla (`/bakilan_kat`)

## 8.6. Bulgu: minimum kullanışlı tarama mesafesi

Tilt sınırı (-0.5 … +1.2 rad) nedeniyle kamera her mesafeden her kata
bakamıyor. Robot rafa çok yaklaşırsa açı doyuma uğruyor (1.2 rad'da
kilitleniyor), üst katlar görülemez hale geliyor.

**Hesaplanan minimum mesafeler** (kutu-merkezi hedefleriyle):

| Kat | Minimum mesafe |
|---|---|
| Kat 1 | ~0.21 m |
| Kat 2 | ~0.42 m |
| Kat 3 | ~0.62 m |

**Neden şu an sorun değil:** Koridor 3.2 m — bu, gerçek depolarda
kullanılan standart reach-truck koridor genişliği (1.5–4 m aralığının
üst-orta bandı), robotun kendi ihtiyacından çok daha geniş bırakıldı.
Robot koridor ortasında konumlanırsa rafa ~1.6 m kalıyor — doyma
sınırının (~0.62 m) çok üzerinde, yaklaşık 1 metrelik güvenlik payı var.

**Sprint 3 çapraz kontrol:** Nav2 tarama pozisyonu belirlenirken
(§2E, Sprint 3 madde 5), seçilen durma noktasının raftan mesafesi
0.65-0.70 m'nin altına düşmemeli. Kestirilen koridor-merkezi mesafesi
(~1.6 m) bu sınırın çok üzerinde olduğu için normalde risk yok, ama
`inflation_radius` ayarı gevşek verilirse veya tarama pozisyonu bilinçli
olarak rafa yakın seçilirse bu sınır ihlal edilebilir. Sprint 3'te
gerçek durma noktası netleşince bu değer tekrar doğrulanmalı.

## 8.7. Asama A: piksel bazli isin-duzlem kesisimi

`piksel_kat_tespit.py` yazildi - artik sabit merkez isin yerine, K matrisi
ile HERHANGI bir pikselden isin atip kat hesaplayabiliyoruz. Fareyle
tiklanabilir test araci - ilerde nesne tespitinin (kutu_tespit.py)
tikladigin yerin yerine tespit edilen kutunun merkez pikselini besleyecek.

**Bulunan ve duzeltilen hata:** Ilk versiyon, LIDAR mesafesini isinin
YARICAPSAL (radial) uzakligi gibi kullaniyordu (`hypot(yon_x, yon_y)`).
Bu, goruntu merkezine yakin pikseller icin dogru sonuc veriyordu ama
kose/kenar piksellerde sistematik hataya yol aciyordu.

**Duzeltme:** Raf, robotun ileri eksenine (x) dik DUZ BIR DUZLEM olarak
modellendi (`x = mesafe`), yaricapsal mesafe yerine. Duzeltme hem
simulasyonsuz elle kurulan test senaryolariyla (3 senaryo, hepsi gecti)
hem de gercek sahnede dogrulandi (tek karede farkli pikseller farkli,
tutarli katlara denk geldi).

**Onemli tasarim notu:** Bu formul, robotun rafa KABACA DIK durdugu
varsayimina dayaniyor. Egik acida robot rafa bakarsa formul gecersiz
olur. Sprint 2E'nin "robot rafin onune konumlan, DUR" adimi zaten bu
varsayimi saglayacak sekilde tasarlanmisti.

# 9. MEVCUT KOD

## 9.1. `kamera_kontrol.py` (çalışıyor)

Görevi: LIDAR'dan mesafe okur, istenen kat için tilt açısını hesaplar, yayınlar.

```python
#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Float64, Int32


class KameraKontrol(Node):

    KAMERA_YUKSEKLIK = 0.11
    KAT_YUKSEKLIKLERI = {1: 0.63, 2: 1.18, 3: 1.68}
    ACI_ALT_SINIR = -0.5
    ACI_UST_SINIR = 1.2

    def __init__(self):
        super().__init__('kamera_kontrol')
        self.mesafe = None
        self.scan_abone = self.create_subscription(
            LaserScan, '/scan', self.scan_geldi, 10)
        self.kat_abone = self.create_subscription(
            Int32, '/hedef_kat', self.kat_istendi, 10)
        self.aci_yayinci = self.create_publisher(
            Float64, '/kamera_acisi', 10)
        self.get_logger().info(
            'Kamera kontrol hazir. /hedef_kat topicine 1, 2 veya 3 gonderin.')

    def scan_geldi(self, mesaj):
        n = len(mesaj.ranges)
        yariyay = int(math.radians(60) / mesaj.angle_increment)
        gecerli = []
        for i in range(-yariyay, yariyay + 1):
            d = mesaj.ranges[i % n]
            if (not math.isinf(d) and not math.isnan(d)
                    and mesaj.range_min < d < mesaj.range_max):
                gecerli.append(d)
        self.mesafe = min(gecerli) if gecerli else None

    def kat_istendi(self, mesaj):
        kat = mesaj.data
        if kat not in self.KAT_YUKSEKLIKLERI:
            self.get_logger().warn(f'Gecersiz kat: {kat}. 1, 2 veya 3 olmali.')
            return
        if self.mesafe is None:
            self.get_logger().warn('Onumde olcum yok, aci hesaplanamiyor.')
            return

        hedef_z = self.KAT_YUKSEKLIKLERI[kat]
        yukseklik_farki = hedef_z - self.KAMERA_YUKSEKLIK
        aci = math.atan2(yukseklik_farki, self.mesafe)
        aci = max(self.ACI_ALT_SINIR, min(self.ACI_UST_SINIR, aci))
        self.aci_yayinci.publish(Float64(data=aci))
        self.get_logger().info(
            f'Kat {kat} -> mesafe {self.mesafe:.2f} m, '
            f'aci {aci:.3f} rad ({math.degrees(aci):.1f} derece)')


def main(args=None):
    rclpy.init(args=args)
    dugum = KameraKontrol()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
```

**Kullanımı:**
```bash
ros2 run depo_robotu kamera_kontrol
# baska terminalde:
ros2 topic pub --once /hedef_kat std_msgs/msg/Int32 "{data: 2}"
```

## 9.2. `depo.launch.py` (çalışıyor)

ROBOTIS'in `empty_world.launch.py` yapısını taklit eder, tek fark dünya yolu.
Ayrıca `/kamera_acisi` köprüsünü kurar:

```python
kamera_koprusu = Node(
    package='ros_gz_bridge',
    executable='parameter_bridge',
    name='kamera_aci_koprusu',
    arguments=['/kamera_acisi@std_msgs/msg/Float64@gz.msgs.Double'],
    output='screen'
)
```

Köprü satırının anlamı: `topic@ROS_tipi@Gazebo_tipi`

## 9.3. `setup.py` entry_points

```python
entry_points={
    'console_scripts': [
        'kamera_kontrol = depo_robotu.kamera_kontrol:main',
    ],
},
```

---

# 10. GÜNLÜK KULLANIM

> **Her yeni terminalde önce `staj` yaz.**

## Derleme

```bash
cd ~/staj_ws
colcon build --symlink-install --packages-select depo_robotu
# turtlebot3_gazebo degistirildiyse:
colcon build --symlink-install --packages-select turtlebot3_gazebo
```
Derlemeden sonra **yeni terminal** aç.

## Dört terminal düzeni

```bash
# Terminal 1 — simulasyon
staj
ros2 launch depo_robotu depo.launch.py

# Terminal 2 — kamera goruntusu
staj
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# Terminal 3 — surus  (w/x ileri-geri, a/d donus, s veya bosluk = DUR)
staj
ros2 run turtlebot3_teleop teleop_keyboard

# Terminal 4 — inceleme
staj
gz topic -t /kamera_acisi -m gz.msgs.Double -p "data: 0.5"
ros2 topic pub --once /kamera_acisi std_msgs/msg/Float64 "{data: 0.5}"
ros2 topic echo /scan --once | grep -A3 "ranges:"
ros2 topic echo /odom --once | head -20
ros2 topic echo /joint_states --once
ros2 run tf2_ros tf2_echo base_link camera_link
ros2 topic echo /camera/camera_info --once
```

## Temizlik

```bash
pkill -f "gz sim"; pkill -f ruby
pkill -f parameter_bridge; pkill -f robot_state_publisher
sleep 2
```

## Kutu üretme

```bash
cd ~/staj_ws/src/depo_robotu/araclar
python3 kutu_uret.py
# sonra kutular.sdf icerigini depo.sdf'e yapistir (eski kutulari sil!)
```

## Git

```bash
cd ~/staj_ws/src/depo_robotu
git status
git add .
git commit -m "aciklama"
git log --oneline
```

## XML kontrolü

```bash
xmllint --noout ~/staj_ws/src/depo_robotu/worlds/depo.sdf && echo "XML saglam"
```

## Kısayollar

| Terminator | | Nano | |
|---|---|---|---|
| `Ctrl+Shift+O` | yatay böl | `Ctrl+O` → Enter | kaydet |
| `Ctrl+Shift+E` | dikey böl | `Ctrl+X` | çık |
| `Ctrl+Shift+V` | yapıştır | `Ctrl+W` | ara |
| `Ctrl+C` | durdur | `Ctrl+_` | satıra git |
| | | `Ctrl+K` | satırı kes |

## Güvenlik alışkanlıkları

```bash
# Riskli apt komutlarini once dene:
sudo apt install -s <paketler>
# Ciktida "Remv" varsa DUR. "0 to remove" ise guvenli.
```

**`sudo apt autoremove` ÇALIŞTIRMA** — kaldırma listesinde NVIDIA
kütüphaneleri var, Gazebo'nun grafiğini bozabilir.

---

# 11. TERMİNOLOJİ (rapor için)

| Türkçe | İngilizce | Nerede |
|---|---|---|
| Aktif algılama | Active Perception | Hareketli kamera yaklaşımı |
| Bakış açısı planlama | Viewpoint Planning | Tilt açısı hesabı |
| En iyi sonraki bakış | Next Best View (NBV) | Hangi rafa önce bakmalı |
| Bak-ve-hareket et | Look-and-Move | Tarama stratejisi |
| Görsel servolama | Visual Servoing (IBVS/PBVS) | Kamera yönlendirme |
| İğne deliği kamera modeli | Pinhole Camera Model | Piksel → ışın |
| İç parametre matrisi | Intrinsic Matrix (K) | `/camera/camera_info` |
| Işın-düzlem kesişimi | Ray-Plane Intersection | Kat tespiti |
| Görüş engeli | Occlusion | Rafın kutuyu gizlemesi |
| Düzlem/doğru uydurma | Plane/Line Fitting (RANSAC) | LIDAR'dan mesafe |
| Kesin doğru referans | Ground Truth | `envanter.json` |
| Semantik navigasyon | Semantic Navigation | Projenin çerçevesi |
| Hareket bulanıklığı | Motion Blur | Neden durup çekiyoruz |

---

# 12. AÇIK KONULAR

- [ ] Yeni GROQ API anahtarı — `.env`'de, `.gitignore`'a ekle, `.bashrc`'ye **asla**
- [ ] Takım kaptanına `.bashrc` İDA bloğu düzenlemesi bildirilecek
      (`GZ_SIM_RESOURCE_PATH` iki satırı birleştirildi — eskiden ikincisi
      birincinin üzerine yazıyordu, bu bir bug'dı)
- [ ] Laptop bakımı (toz + termal macun)
- [ ] LLM sağlayıcı araştırması — rate limit ve ücretsiz kota kriterleri
- [ ] Sprint 1 demo videosu (`Ctrl+Alt+Shift+R`)
- [ ] `NOTLAR.md` → Word belgesine derleme
- [ ] Sabit kamera (tilt=0) sürümünü baseline için sakla
- [ ] Sprint 2C-4 (algi modu, LIDAR line fitting) hala yapilmadi. Su anki
      piksel_kat_tespit.py "robot rafa dik duruyor" varsayimiyla calisiyor
      (mesafe = LIDAR'daki en yakin nokta, x=mesafe duzlemi). Cok yakinda
      dogru sonuc veriyor, ama robot rafa CAPRAZ duruyorsa veya raftan
      COK uzaktaysa (>2m gibi) hata buyuyor. Look-and-Move (§2E) zaten
      robotu dik durduracagi icin normal operasyonda sorun cikmayacak,
      ama Sprint 2C-4'u atlamayi bilerek sectik - ilerde donup yapilacak.
      - [ ] Sprint 2C-4 (algi modu, LIDAR line fitting) hala yapilmadi. Su anki
      piksel_kat_tespit.py "robot rafa dik duruyor" varsayimiyla calisiyor
      (mesafe = LIDAR'daki en yakin nokta, x=mesafe duzlemi). Cok yakinda
      dogru sonuc veriyor, ama robot rafa CAPRAZ duruyorsa veya raftan
      COK uzaktaysa (>2m gibi) hata buyuyor. Look-and-Move (§2E) zaten
      robotu dik durduracagi icin normal operasyonda sorun cikmayacak,
      ama Sprint 2C-4'u atlamayi bilerek sectik - ilerde donup yapilacak.

- [ ] Sprint 2D basladi: kutu_tespit.py (HSV renk tespiti, 5 renk) ve
      renk_probu.py (HSV kalibrasyon araci) yazildi. Renk esikleri
      renk_probu.py ile olculen gercek degerlere dayanarak ayarlandi.

      BULUNAN IKI RISK:
      1) Mavi kutu ile rafin mavi destek diregi HSV'de neredeyse ozdes
         (H=113-114 vs H=109). Renkle ayrilamiyor - bounding-box en-boy
         orani filtresi eklendi (direkler ince-uzun, kutular kareye
         yakin varsayimi). Bu filtre normal mesafede (~1.5m, rafa dik)
         guvenilir; asiri yakin + capraz acida direkler de kareye yakin
         gorunebiliyor, yanlis pozitif riski var.
      2) Karton kutu ile turuncu raf tablasi ayni H degerine sahip
         (H~17-19), doygunluk (S) ile ayriliyor (karton S~94, raf S~183).
         Ancak S degeri isik acisina/mesafeye gore degisebiliyor -
         capraz acida bu ayrim da bozulabilir.

      Ilk testte (kamera rafa cok yakin + capraz) her iki filtre de
      basarisiz oldu - mavi direkler kutu sanildi, performans da dustu
      (asiri sayida yanlis kontur isleniyor). Dogru mesafede (1.4-1.6m,
      rafa dik) tekrar test edilecek - eger orada da sorun devam ederse
      raf gorsel geometrisinde (mavi direk/turuncu tabla cakismasi)
      gercek bir sorun olabilir, kontrol edilecek.

      GUNCELLEME (12 Agustos 2026, dogru mesafede test sonrasi):
      Dogru mesafede (1.6m, rafa dik) tekrar test edildi - en-boy orani
      filtresi orada da YETERSIZ kaldi. Sebep: direkler rafin en kenarinda
      oldugundan genis FOV (1.3 rad) tum raf genisligini alabilmek icin
      onlari capraz aciyla goruyor (on yuz degil yan yuz gorunuyor), ve
      yatay raf tablalari direk siluetini kat kat parcaliyor - boylece
      direk, kareye yakin birkac kucuk parcaya bolunup filtreyi geciyor.

      DUZELTME (uygulandi): piksel_kat_hesapla artik isinin x=mesafe
      duzlemini kestigi noktanin RAF BOYUNCA yanal konumunu da hesapliyor.
      Bu konum, RAF_UZUNLUK'tan turetilen direk merkezine (~1.35m, 0.12m
      tolerans) yakinsa tespit reddediliyor. Canli teshis ile dogrulandi:
      onceden yanlis-pozitif olan 4 direk konturunun tamami artik doguru
      sekilde reddediliyor.

      ACIK MADDE 1 - KESIN DOGRULANMADI: Gercek mavi kutu (B2'de x=1.2m)
      ile direk (x=1.35m) sadece 0.15m arayla, ikisi de kadrajin en
      kenarinda. Bu mesafede/acida geometrik kestirim hatasi bu farktan
      buyuk olabiliyor - en yakin aday tespitin yukseklik uyumu da zayifti
      (fark≈0.30m, tolerans siniri). GERCEK KUTUNUN YENI FILTRE TARAFINDAN
      YANLISLIKLA ELENMEDIGI DOGRULANMADI. Farkli mesafe/acilarda ve
      mumkunse envanterdeki bilinen konumla capraz kontrolle tekrar
      test edilmeli.

      ACIK MADDE 2 - x=mesafe DUZLEM VARSAYIMI ACIK ARKALI RAFLARDA
      GECERSIZ OLABILIR: Raflarin arkasi kapali degil (sadece 2 direk +
      3 ince tabla, arka panel yok). Kamera bosluklardan baktiginda ayni
      x'teki daha uzak bir rafi (orn. B2'nin 4m arkasindaki A2) gorebiliyor.
      piksel_kat_hesapla'nin x=mesafe varsayimi (LIDAR'in ONUNDEKI rafa olan
      mesafeyi kullanir) boyle gorulen uzak nesneler icin tamamen gecersiz
      bir yukseklik/adres uretir. B2 testinde envanterle eslesmeyen kucuk
      mavi/sari tespitler bulundu; en olasi aciklama bu ama kaynagi kesin
      dogrulanmadi. Kod degisikligi yapilmadi, sadece risk kaydi.

      GUNCELLEME (Sprint 2E, tarama_kontrol.py ile B2 testi):
      Bu risk artik sayisal olarak dogrulandi. B2 onunde uc kat da
      tarandiginda kat basina 8-13 tespit geliyor (envanterde B2'nin kat
      basina en fazla 4 kutusu var). kutu_tespit.py bir tespitin hangi
      RAFA ait oldugunu hic hesaplamiyor - sadece kat (z yuksekligi)
      hesapliyor - bu yuzden genis FOV'un yakaladigi komsu raf (A2/C2)
      kutulari B2'ye aitmis gibi listeye giriyor. Detay: bkz. NOTLAR.md
      SORUN 12. Kod degisikligi hala yapilmadi (kutu_tespit.py'ye
      dokunulmadi, sadece orkestrasyon katmani tarama_kontrol.py bu
      farki `fazla_tespit` alaniyla raporda gosteriyor). Sprint 6
      metrik tasarimini etkiler, bkz. §7 Metrikler notu.
---

# 13. RİSKLER VE UYARILAR

**Zaman kutusu:** Sprint 1–3 "altyapı", Sprint 4–6 "özgün katkı".
Altyapıda takılıp kalma. Sprint 3 iki haftayı aşarsa kapsamı daralt
(otonom keşfi bırak, elle haritalama yeterli). Değerlendirilecek kısım
algı + LLM entegrasyonu; uyumluluk savaşı değil.

**Teknik riskler:**
- Nav2 `inflation_radius` dar geçitlerde (1.2 m) yol bulamayabilir
- LLM rate limit geliştirme sırasında sıkıntı yaratabilir
- YOLO eklenince 4 GB VRAM sınırı — nano/small kullan
- `git pull` yaparsan `turtlebot3_simulations` yamaları silinebilir

**Metodolojik uyarılar:**
- Erken optimizasyon yapma: RANSAC'tan önce en küçük kareler dene
- Bilinen ortamda oracle modu her zaman daha doğru — algı modu baseline için
- HSV'de kırmızı **iki aralık** ister, yoksa tespitlerin yarısı kaçar
- Değişiklik yapmadan önce **yedek al** (bu proje boyunca birkaç kez kurtardı)
