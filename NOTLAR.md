# Proje Teknik Notları

**Proje:** Yapay Zeka Destekli Akıllı Depo Robotu Simülasyonu
**Ortam:** Ubuntu 22.04 · ROS 2 Humble · Gazebo Sim 8.14.0 (Harmonic) · TurtleBot3 waffle_pi

> Bu dosya, karşılaşılan sorunları ve çözümlerini anında kaydetmek içindir.
> Yeni bir sorun çözüldüğünde en alta eklenir. Word belgesi buradan derlenir.

---

## ÖNEMLİ: Workspace yeniden kurulursa

`~/staj_ws` silinip baştan kurulursa, aşağıdaki **Y1–Y7** yamalarının tekrar uygulanması gerekir.
Aksi halde derleme başarısız olur veya robot çalışmaz.

Yamaların uygulandığı dosyalar `turtlebot3_simulations` deposuna aittir (ROBOTIS),
yani `git pull` yapılırsa da üzerine yazılabilir.

| Yama | Dosya | Konu |
|---|---|---|
| Y1 | turtlebot3_gazebo/CMakeLists.txt | vendor paketleri kaldırıldı |
| Y2 | turtlebot3_gazebo/CMakeLists.txt | find_package sürümlendi |
| Y3 | turtlebot3_gazebo/CMakeLists.txt | link hedefleri sürümlendi |
| Y4 | params/turtlebot3_waffle_pi_bridge.yaml | TwistStamped → Twist |
| Y5 | ~/.bashrc (staj alias) | mesh yolu eklendi |
| Y6 | models/turtlebot3_waffle_pi/model.sdf | gövde rengi turuncu |
| Y7 | models/turtlebot3_waffle_pi/model.sdf | kamera açısı + FOV |

**Yedekler:**
- `~/.bashrc.yedek`
- `models/turtlebot3_waffle_pi/model.sdf.yedek` (orijinal)
- `models/turtlebot3_waffle_pi/model.sdf.yedek2` (renk+açı değişikliği sonrası)
- `worlds/depo.sdf.yedek`

---

## SORUN 1 — Gazebo Classic 11 ile Harmonic çakışması

**Belirti**
```
gz-tools2 : Conflicts: gazebo (>= 11.0.0) but 11.10.2+dfsg-1 is to be installed
E: Error, pkgProblemResolver::Resolve generated breaks
```

**Sebep**
Harmonic'in bileşeni `gz-tools2`, Gazebo Classic 11 ile aynı sistemde bulunmayı reddediyor.
Classic kurulmak istenirse apt, İDA projesinin Harmonic kurulumunu sökmek zorunda kalıyor.

**Çözüm**
Classic 11 kurulmadı. Her iki proje de tek Gazebo (Harmonic) üzerinde yürütülüyor.
`turtlebot3_simulations` apt yerine kaynaktan, `jazzy` branch'inden derlendi.

**Ders**
Riskli görünen her `apt install` önce `-s` (simulate) ile denenmeli.
Çıktıda `Remv` satırı varsa DURULMALI. `0 to remove` görülürse güvenli.

**Not**
`sudo apt autoremove` ÇALIŞTIRILMAMALI — kaldırma listesinde NVIDIA kütüphaneleri var.

---

## SORUN 2 — jazzy branch Humble'da derlenmiyor (vendor paketleri)

**Belirti**
```
CMake Error at CMakeLists.txt:29 (find_package):
  Could not find a package configuration file provided by "gz_math_vendor"
```

**Sebep**
`gz_math_vendor` / `gz_sim_vendor` / `gz_plugin_vendor` paketleri ROS 2 Jazzy'ye özgü
sarmalayıcılardır; Humble'da bu katman yoktur. Kütüphaneler sistemde mevcuttur ama
farklı isimle: `gz-math7`, `gz-sim8`, `gz-plugin2`.

**Çözüm — Y1**
```bash
cd ~/staj_ws/src/turtlebot3_simulations/turtlebot3_gazebo
cp CMakeLists.txt CMakeLists.txt.yedek

sed -i '/find_package(gz_math_vendor REQUIRED)/d; \
        /find_package(gz_sim_vendor REQUIRED)/d; \
        /find_package(gz_plugin_vendor REQUIRED)/d' CMakeLists.txt
```

**Çözüm — Y2**
```bash
sed -i 's/find_package(gz-math REQUIRED)/find_package(gz-math7 REQUIRED)/; \
        s/find_package(gz-sim REQUIRED)/find_package(gz-sim8 REQUIRED)/; \
        s/find_package(gz-plugin REQUIRED)/find_package(gz-plugin2 REQUIRED)/' CMakeLists.txt
```

**Sistemdeki sürümleri görmek için**
```bash
ls /usr/lib/x86_64-linux-gnu/cmake/ | grep -i "gz-"
```

---

## SORUN 3 — Link hedefleri bulunamıyor

**Belirti**
```
CMake Error at CMakeLists.txt:66 (add_library):
  Target "obstacles" links to target "gz-sim::gz-sim" but the target was not found.
```

**Sebep**
Sorun 2'nin devamı. `find_package` düzeldi ama link hedefleri hâlâ sürümsüz isimle yazılı.

**Çözüm — Y3**
```bash
sed -i 's/gz-sim::gz-sim/gz-sim8::gz-sim8/g; \
        s/gz-math::gz-math/gz-math7::gz-math7/g; \
        s/gz-plugin::/gz-plugin2::/g' CMakeLists.txt
```

Bu üç yamadan sonra: `Summary: 3 packages finished`

---

## SORUN 4 — Robot görünmüyor (mesh bulunamıyor)

**Belirti**
Fizik ve sensörler çalışıyor, robot Entity Tree'de var, ama ekranda görünmüyor.
```
[Err] Unable to find file with URI [model://turtlebot3_common/meshes/bases/waffle_pi_base.stl]
```

**Sebep**
Mesh dosyaları `install` dizininde mevcut, ancak `GZ_SIM_RESOURCE_PATH` o klasörü içermiyor.

**Teşhis**
```bash
find ~/staj_ws -name "waffle_pi_base.stl" 2>/dev/null
```

**Çözüm — Y5**
`~/.bashrc` içindeki `staj` alias'ına eklendi:
```bash
export GZ_SIM_RESOURCE_PATH=~/staj_ws/install/turtlebot3_gazebo/share/turtlebot3_gazebo/models:$GZ_SIM_RESOURCE_PATH
```

---

## SORUN 5 — Robot hareket etmiyor (mesaj tipi uyumsuzluğu)

**Belirti**
Gazebo ve robot açılıyor, teleop çalışıyor ama robot kımıldamıyor.

**Teşhis**
```bash
$ ros2 topic info /cmd_vel
Type: ['geometry_msgs/msg/Twist', 'geometry_msgs/msg/TwistStamped']
Publisher count: 1
Subscription count: 1
```
Aynı topic üzerinde iki farklı mesaj tipi. `teleop_keyboard` düz `Twist` yayınlıyor,
`ros_gz` köprüsü `TwistStamped` bekliyor. Bağlantı kurulmuyor.

**Doğrulama testi** (bu çalışıyorsa teşhis kesin)
```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/TwistStamped "{twist: {linear: {x: 0.2}}}" --rate 10
```

**Çözüm — Y4**
```bash
cd ~/staj_ws/src/turtlebot3_simulations/turtlebot3_gazebo/params
sed -i '32s|geometry_msgs/msg/TwistStamped|geometry_msgs/msg/Twist|' turtlebot3_waffle_pi_bridge.yaml
cd ~/staj_ws && colcon build --symlink-install --packages-select turtlebot3_gazebo
```

**Not**
Paket geliştiricileri bu durumu öngörmüş; `burger_bridge.yaml` içinde ilgili satırın yanında
`# If you use Twist, you need to change the type to Twist` yorumu var.
Sadece `waffle_pi` dosyası değiştirildi.

---

## SORUN 6 — setuptools sürümü çok yeni

**Belirti**
```
error: option --editable not recognized
error: option --uninstall not recognized
```
`colcon build` başarısız oluyor, `setup.py` dosyasında hiçbir hata yok.

**Teşhis**
```bash
python3 -c "import setuptools; print(setuptools.__version__)"   # 82.0.1
python3 -c "import setuptools; print(setuptools.__file__)"      # ~/.local/... (kullanıcı bazlı)
```

**Sebep**
ROS 2 Humble'ın `ament_python` derleyicisi eski `setup.py develop` yöntemini kullanır.
Bu yöntem setuptools 64'te kaldırıldı. Sistemde 82.0.1 kuruluydu.

**Çözüm**
```bash
# önce artıkları temizle
cd ~/staj_ws && rm -rf build/depo_robotu install/depo_robotu

pip3 install --user setuptools==58.2.0
```
58.2.0, ROS 2 Humble'ın resmi olarak beklediği sürümdür.

**Not**
İleride yeni setuptools gerektiren bir Python işi olursa (ultralytics vb.),
sistem geneli yükseltmek yerine `venv` kullanılmalı.

---

## SORUN 7 — Kendi dünyam yüklenmiyor

**Belirti**
`ros2 launch depo_robotu depo.launch.py` çalışıyor ama Entity Tree'de `ground_plane` / `sun`
görünüyor (TurtleBot3'ün varsayılan dünyası), kendi `zemin` / `gunes` modelleri yok.

**Sebep**
`empty_world.launch.py` içinde dünya yolu **sabit kodlanmış**, dışarıdan argüman kabul etmiyor:
```python
world = os.path.join(get_package_share_directory('turtlebot3_gazebo'),
                     'worlds', 'empty_world.world')
```
Gönderilen `world` argümanı görmezden geliniyor.

**Çözüm**
ROBOTIS'in launch dosyası çağrılmak yerine, kendi `depo.launch.py` sıfırdan yazıldı.
Yapı aynı, tek fark:
```python
world = os.path.join(depo_paket, 'worlds', 'depo.sdf')
```
Robot yükleme ve köprü kurma işleri hâlâ ROBOTIS'in alt-launch dosyalarından çağrılıyor
(`robot_state_publisher.launch.py`, `spawn_turtlebot3.launch.py`).

**Ek not**
`<world name="default">` olarak bırakıldı — `spawn_turtlebot3.launch.py` bu ismi bekliyor.
`depo` yapılırsa robot dünyaya eklenemiyor.

**İyileştirme**
`AppendEnvironmentVariable` (model yolu) eylemi listenin **başına** alındı.
ROBOTIS'te en sonda; Gazebo başladıktan sonra ayarlanması yarış durumu yaratabiliyor.

---

## SORUN 8 — Eski Gazebo süreçleri karışıklık yaratıyor

**Belirti**
Entity Tree ile Model paneli çelişiyor; sahne boş görünüyor; değişiklikler yansımıyor.

**Sebep**
`Ctrl+C` her zaman tüm süreçleri öldürmüyor. Gazebo sunucu (`-s`) ve arayüz (`-g`)
ayrı süreçler olduğu için, yeni arayüz eski sunucuya bağlanabiliyor.

**Çözüm**
```bash
pkill -f "gz sim"
pkill -f ruby
pkill -f parameter_bridge
pkill -f robot_state_publisher
sleep 2
ps aux | grep -c "gz sim"   # küçük bir sayı dönmeli
```

**Alışkanlık**
Garip bir davranış görüldüğünde ilk iş bu temizliği yapmak.

---

## SORUN 9 — teleop_keyboard: KeyError 'TURTLEBOT3_MODEL'

**Belirti**
```
KeyError: 'TURTLEBOT3_MODEL'
[ros2run]: Process exited with failure 1
```

**Sebep**
O terminalde `staj` alias'ı çalıştırılmamış, ortam değişkenleri yüklenmemiş.

**Çözüm**
Her yeni terminalde önce `staj` yazılmalı.

---

## SORUN 10 — Robot kendi kendine dönüyor gibi görünüyor

**Belirti**
Kamera görüntüsü sürekli sağa sola kayıyor, robot durmuyor.

**Sebep**
Teleop'ta kalıntı açısal hız var. `a` / `d` tuşları hedef hızı değiştirir ve
kullanıcı durdurana kadar komut aktif kalır.
```
currently:  linear velocity 0.0    angular velocity -0.1
```

**Çözüm**
Teleop terminalinde `s` veya boşluk tuşu → force stop (hem doğrusal hem açısal sıfırlanır).

**Kontrol**
```bash
ros2 topic echo /cmd_vel --once
```

---

## KARAR 1 — Kamera açısı ve görüş alanı

**Problem**
Robot dar koridorda (raflar arası 3.2 m) rafın üç katını birden göremiyor.
Kamera yerden sadece 0.11 m yükseklikte.

**Denenen çözümler**

| Deneme | Değişiklik | Sonuç |
|---|---|---|
| 1 | Kamera 20° yukarı eğildi (`pitch = -0.349`) | Uzaktan (≈4 m) üç kat görünüyor, yakından değil |
| 2 | FOV 1.085 → 1.7 rad (≈97°) | **Yetersiz.** Yakından alt kat hâlâ kadraj dışında |

**Y7 — uygulanan değişiklikler**
```bash
cd ~/staj_ws/src/turtlebot3_simulations/turtlebot3_gazebo/models/turtlebot3_waffle_pi

# 465. satır: kamera açısı (pitch, radyan; negatif = yukarı)
sed -i '465s|<pose>0.073 -0.011 0.084 0 0 0</pose>|<pose>0.073 -0.011 0.084 0 -0.349 0</pose>|' model.sdf

# görüş alanı
sed -i 's|<horizontal_fov>1.085595</horizontal_fov>|<horizontal_fov>1.7</horizontal_fov>|' model.sdf
```

**Elenen seçenek**
"Robot 2 m mesafeden tarasın" fikri elendi — gerçek bir depoda robotun geri çekilebileceği
boş alan bulunmaz, her metrekare değerlidir. Robot koridorda çalışmak zorundadır.

**Alınan karar**
Hareketli (tilt) kamera yapılacak. Sabit kamerayla bu problem geometrik olarak çözülemiyor.

---

## KARAR 2 — Robot görünüşü

- Gövde rengi turuncu yapıldı (**Y6**, `model.sdf` satır 41-42): `0.9 0.45 0.05 1.0`
- Yük platformu eklenmesi **elendi** — LIDAR (tepede) ve kamerayı (önde) kapatma riski var
- Kamera direği eklenirken görünüş de iyileştirilecek

---

## KARAR 3 — Depo tasarımı

**Boyut:** 12 × 12 m, duvarlar ±6 m'de, 2 m yüksek
**Kapı:** Güney duvarında 4 m boşluk (x: -2 ~ +2)
**Raflar:** 9 adet, 3×3 ızgara — A/B/C sıraları, 1/2/3 sütunları

| Adres | Pose (x, y) |
|---|---|
| A1 | (-4, 4) |
| A2 | (0, 4) |
| A3 | (4, 4) |
| B1 | (-4, 0) |
| B2 | (0, 0) |
| B3 | (4, 0) |
| C1 | (-4, -4) |
| C2 | (0, -4) |
| C3 | (4, -4) |

**Raf ölçüleri:** 2.8 × 0.8 × 1.5 m · 3 kat (z = 0.45 / 1.00 / 1.50)
**Koridorlar:** sıralar arası 3.2 m · yan geçitler 1.2 m
**Robot başlangıcı:** (0, -5) — kapının içi

**Kutu z konumları** (kat yüzeyi + 0.03 kalınlık + 0.15 kutu yarısı)

| Kat | Kutu z |
|---|---|
| 1 | 0.63 |
| 2 | 1.18 |
| 3 | 1.68 |

**Tasarım notları**
- Rafların `collision`'ı tek blok (2.8 × 0.8 × 1.5), `visual`'ı çok parçalı
  → hem performanslı hem güzel. Robot raf altına giremez (kasıtlı).
- Model seviyesinde `<pose>` kullanıldı; iç parçalar ona göreli.
  Rafın yerini değiştirmek için tek satır yeterli.
- Aynı renkten birden fazla kutu var → "hangi kırmızı?" belirsizliği kasıtlı,
  Sprint 4-5'te LLM'in çözmesi gereken problem.

---

## Günlük kullanım

Her terminalde **önce `staj`**.

```bash
# Terminal 1 — simülasyon
staj
ros2 launch depo_robotu depo.launch.py

# Terminal 2 — kamera
staj
ros2 run rqt_image_view rqt_image_view /camera/image_raw

# Terminal 3 — sürüş  (w/x ileri-geri, a/d dönüş, s veya boşluk = dur)
staj
ros2 run turtlebot3_teleop teleop_keyboard

# Terminal 4 — inceleme
staj
ros2 topic list
ros2 topic info /cmd_vel
ros2 topic hz /camera/image_raw
```

**Derleme**
```bash
cd ~/staj_ws
colcon build --symlink-install --packages-select depo_robotu
# turtlebot3_gazebo değiştirildiyse:
colcon build --symlink-install --packages-select turtlebot3_gazebo
```

Derlemeden sonra **yeni terminal** açılmalı (ortam tazelensin).

---

## Açık konular

- [ ] Yeni GROQ API anahtarı — `.env` içinde tutulacak, `.bashrc`'ye YAZILMAYACAK, `.gitignore`'a eklenecek
- [ ] Takım kaptanına `.bashrc` İDA bloğu düzenlemesi bildirilecek (`GZ_SIM_RESOURCE_PATH` birleştirmesi)
- [ ] Laptop bakımı (toz + termal macun) — ~10 gün içinde
- [ ] LLM sağlayıcı araştırması (Groq / OpenRouter / Google AI Studio) — rate limit ve ücretsiz kota kriterleri
- [ ] Sağlayıcı çağrısı tek bir fonksiyonda toplanmalı (geçiş kolaylığı)
- [ ] Sprint 1 demo videosu (Ubuntu ekran kaydı: `Ctrl+Alt+Shift+R`)
- [ ] Word belgesi bu notlardan güncellenecek

---

## Sıradaki iş: Hareketli (tilt) kamera

**Neden:** Sabit kamerayla dar koridorda üç kat birden görülemiyor (bkz. KARAR 1).

**Plan**
1. `camera_joint`'i `fixed` → `revolute` yap
2. Dönüş eksenini y ekseni olarak tanımla (tilt)
3. Açı sınırları koy (≈ -60° ile +20°)
4. `JointPositionController` eklentisini ekle
5. `ros_gz_bridge`'e açı komutu köprüsü ekle
6. Tarama node'u yaz: kamerayı üç kat açısına sırayla götür, her birinde dur ve görüntü al

**Kazanım**
Kameranın açısı bilindiği için, görülen nesnenin **hangi katta** olduğu hesaplanabilir.
Bu, `A1-kat3-kırmızı kutu` şeklinde 3B adreslemeyi mümkün kılar — sabit kamerayla imkânsız.

**Beklenen riskler**
- TF ağacı: joint durumu yayınlanmazsa RViz'de kamera yanlış konumda görünür (Sprint 3'te Nav2 için önemli)
- Eklenti uyumu: Harmonic'in `JointPositionController` davranışı denenmeden bilinmiyor
- Titreşim: robot hareket ederken kamera sallanabilir, sönümleme gerekebilir

**Karar:** Şimdilik sadece tilt. Pan (sağa-sola) eklenmeyecek — robot zaten yerinde 360° dönebiliyor.
Tilt çalıştıktan sonra gerekirse pan değerlendirilir.
