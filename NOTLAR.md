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

## SORUN 11 — LIDAR mesafesi yanlış, kat tespiti sistematik hatalı

**Belirti**
Robot bir rafın (B2) tam ortasında, rafa dik durduğu halde `kamera_kontrol`
düğümünün ölçtüğü mesafe geometrik olarak beklenenden ~0.65 m fazla
(1.75 m yerine ~1.1 m bekleniyordu). Bu yanlış mesafe `kutu_tespit.py`'nin
kat hesaplarına giriyor ve kamera hangi açıya gönderilirse gönderilsin
aynı fiziksel kutu hep aynı (yanlış) kata atanıyor — merkez kırmızı kutu
(gerçekte kat2) sürekli kat3, kenar sarı/yeşil kutular (gerçekte kat1)
sürekli kat2 çıkıyor.

**Teşhis**
`/scan` mesajı ham okunduğunda, robotun tam önünde (açı 0°, dünya +y yönü)
`inf` dönüyor — 3.5 m menzilde hiçbir şeye çarpmıyor. ±60°'lik koninin
gördüğü tek nokta, açısal olarak rafın kenar direğine denk geliyor; o
noktanın mesafesi (1.738 m), direğin en yakın köşesine geometrik olarak
hesaplanan mesafeyle (1.746 m) neredeyse birebir örtüşüyor.

**Sebep**
gz-sim'in `gpu_lidar` sensörü ışınları **render motoruyla** hesaplıyor —
yani sadece `<visual>` geometrisine çarpıyor, fizik motorunun kullandığı
`<collision>`'a değil. `depo.sdf`'teki raflar performans için tek parça
**görünmez** collision bloğu + parçalı (2 dikey direk + 3 ince tabla)
**visual**'dan oluşuyor (bkz. KARAR 3). Robot rafın merkezinde durduğunda,
LIDAR yüksekliğinde (~0.13 m) önünde hiçbir visual yok — direkler
kenarlarda (x=±1.35), tablalar çok daha yukarıda (z≥0.45). Işın boşluktan
geçip hiçbir şeye çarpmıyor; koni sadece açılı gidip kenar direklerine
değen ışınları görüyor.

**Elenen hipotezler**
- LIDAR/TF mount offset (`lidar_joint`, `model.sdf`): rotasyon yok, sadece
  ~6 cm öteleme — 65 cm'lik farkı açıklamıyor.
- `raf_B2`'nin `depo.sdf` içindeki collision pose/size'ı: dokümandaki
  y=-0.4 güney-kenar varsayımıyla birebir örtüşüyor, tutarsızlık yok.

**Çözüm**
9 rafın tamamına, collision ile aynı pose/boyutta, kamera için tamamen
saydam (`<transparency>1</transparency>`) bir `lidar_dolgu` visual
eklendi. Görünüm değişmedi, LIDAR artık gerçek raf yüzeyini görüyor.

**Doğrulama**
Ölçülen mesafe 1.75 m → 1.15 m (beklenen ~1.1 m'ye çok yakın). B2 önünde
üç kata da tarama yapıldı, `kutu_tespit.py`'nin kat atamaları
`envanter.json` ground truth ile artık eşleşiyor.

**Ders**
gz-sim'de `gpu_lidar` / kamera gibi **render-tabanlı** sensörler sadece
`<visual>` geometrisini görür. Performans için "collision tek blok, visual
parçalı" tasarlanan herhangi bir statik model (raf, dolap, vb.), o modele
bakan bir LIDAR/derinlik kamerası eklenecekse aynı sorunu verir. Yeni bir
sensör eklenmeden önce, o sensörün ray-tracing mi (collision görür) yoksa
render-tabanlı mı (sadece visual görür) çalıştığı kontrol edilmeli.

---

## SORUN 12 — kutu_tespit tespitleri rafa göre kapsamlanmıyor (shelf-scoped değil)

**Belirti**
`tarama_kontrol.py` (Sprint 2E) ile B2 önünde üç kat tarandığında, kat
başına 8-13 tespit geliyor; oysa `envanter.json`'a göre B2'nin kat
başına en fazla 4 kutusu var (toplam 8 kutu / 3 kat). Renk bazlı
eşleştirmeyle envanterin tamamı (8/8) "bulundu" sayılsa da, 25 tespit
hiçbir gerçek B2 kutusuyla eşleşmeden fazlalık kalıyor.

**Sebep**
`kutu_tespit.py` bir pikselin *hangi rafa* ait olduğunu hiç hesaplamıyor
— sadece `piksel_kat_hesapla` ile hangi **kata** (z yüksekliğine) denk
geldiğini buluyor (`kutu_tespit.py:130` civarı). Geniş kamera FOV'u
(bkz. KARAR 1) B2'nin önünden bakarken komşu raflardaki (aynı sütun,
farklı satır — örn. A2/C2) aynı kat yüksekliğindeki kutuları da
kadraja alabiliyor; bunlar da aynı z-aralığına düştüğü için tespit
listesine "B2'ye ait" gibi karışıyor. Bu, "Açık konular" bölümündeki
raf-arkası boşluk gözlemiyle aynı kök nedenin (dar koridorda geniş FOV,
adres bilgisi olmayan ray-plane kestirimi) farklı bir belirtisi —
oradaki gözlem tek node (`kutu_tespit` tek başına, `renk_probu`
tarzı manuel test) ile şüpheliydi, `tarama_kontrol`'ün üç kat +
envanter karşılaştırması bunu somut sayılarla doğruladı.

**Durum**
Kod değişikliği yapılmadı — `kutu_tespit.py`'ye dokunulmadı (bkz. bu
node'u orkestre eden `tarama_kontrol.py`'nin tasarım kısıtı: mevcut
node'lar değiştirilmeyecek). `tarama_kontrol.py`'nin raporu artık
`fazla_tespit` alanıyla bu farkı açıkça gösteriyor, gizlemiyor.

**Olası çözüm yönleri (henüz uygulanmadı)**
- `piksel_kat_hesapla`'nın zaten hesapladığı yanal (raf boyunca) konuma
  ek olarak *derinlik* (ışının hangi raf düzlemini kestiği) de
  hesaplanıp, hedef rafın bilinen (x, y) adresiyle karşılaştırılabilir.
- Ya da tespit sırasında LIDAR mesafesini "sadece en yakın rafa kadar"
  değil, hedef rafın bilinen mesafesiyle sınırlı bir pencereye
  kısıtlamak (şu an zaten `self.mesafe` = LIDAR'ın gördüğü en yakın
  nokta, ama bu en yakın rafın önündeki objeyi verir, arka rafları
  elemez — bkz. SORUN 11'deki visual/collision ayrımı da bu mesafenin
  güvenilirliğini etkiliyor).

---

## SORUN 13 — bitişik iki kutu tek kontura birleşiyor (kontur birleşmesi)

**Belirti**
`tarama_kontrol.py` ile B2 taranırken kat2'deki 2 karton kutu (küçük +
orta, raf-yerel x farkı ~0.5 m) `/tespitler`'de tek bir "buyuk" karton
tespiti olarak çıkıyor — envanterdeki 2 kutu yerine 1.

**Sebep**
İki kutu kamera açısından bakıldığında görüntüde optik olarak
birbirine değiyor; HSV maskesinde `MORPH_CLOSE`/`OPEN` öncesi ham
maskede bile tek blok halinde bitişikler (kernel=0 testiyle
doğrulandı — köprü morfolojik kapatmadan gelmiyor, kutular gerçekten
temas ediyor). `cv2.findContours(RETR_EXTERNAL, ...)` bu tek bloğu
kaçınılmaz olarak tek dış kontur olarak döndürüyor.

Önceki bir oturumda `EN_BOY_UST_SINIR` 2.5 → 4.0'a gevşetilmişti (bu
birleşik bloğun en-boy oranı ~3.6 olduğu için direk filtresine
takılmasın diye) — bu sadece blob'un tamamen elenmesini önlüyordu,
gerçek nedeni (tek kontur = tek tespit) çözmüyordu.

**Çözüm**
`kutu_tespit.py`'ye `_birlesik_konturu_ayir` metodu eklendi: her
external kontur, kendi bounding-box'ı içinde crop'lanıp
`cv2.distanceTransform` + `cv2.watershed` ile ayrıştırılıyor. Tek
kutuluk konturlarda mesafe haritasının tek bir tepe bölgesi olduğundan
bölme yapılmıyor (orijinal bounding rect aynen dönüyor — mevcut
tek-kutu tespitlerinde regresyon riski yok); ≥2 ayrık tepe bulunursa
her biri ayrı bir tespit olarak döner. Bölme, global değil kontur
bazında lokal yapılıyor — aksi halde tek bir global mesafe eşiği,
görüntüdeki diğer küçük/izole kutuları da eleyebilirdi.

`MORPH_CLOSE`/`OPEN` kernel'i 3×3'e küçültülerek de denendi, işe
yaramadı (yukarıdaki "Sebep" bölümüne bkz.) — 5×5'e geri alındı.

**Doğrulama**
B2 kat2 penceresinde tekrarlanan taramalarda artık 2 ayrı karton
tespiti geliyor (önceden 1). Direk (`mavi`) tespit sayıları taramalar
arasında aynı aralıkta kaldı (6-9/pencere) — direk filtresinde
regresyon yok.

**Açık nokta**
Bölünen kutunun boyut kestirimi (`boyut_kestir`) kareler arasında
"orta"/"buyuk" arasında salınabiliyor — watershed sınırındaki piksel
gürültüsünden kaynaklanıyor gibi görünüyor, sayım doğruluğunu
etkilemiyor ama boyut alanı gürültülü kalabilir.

**Ek doğrulama (C2, sabit eşik yetersiz kaldı)**
B2'nin ardından C2 rafında da aynı testi (raf=C2, `tarama_kontrol.py`)
tekrarladık. C2'nin `kutu_uret.py`'deki `yon="kuzey"` değeri robotun
rafın **kuzeyinden, güneye bakarak** durması gerektiği anlamına
geliyor (B2'nin tam tersi) — pozisyon (0, -2.0) yaw=-90° ile doğru
raf doğrulandı (13/13 renk eşleşmesi).

C2 kat2'de (orta+büyük karton, ~0.55 m aralık) ve kat3'te (orta+kucuk
karton, ~0.42 m aralık) SORUN 13'teki sabit 0.5 esik orani bu ikiliyi
AYIRAMADI — sadece 1 tespit döndü. Sebep: boyut-simetrik ciftlerde
(B2) birlesim beli mesafe tepesinin ~yarisina kadar dusuyor, ama
boyut-asimetrik ciftlerde bel daha sig kaliyor (~%66) - sabit 0.5
esigi bu ikinci durumu yakalamiyordu.

**Çözüm:** `_birlesik_konturu_ayir` sabit tek oran yerine, 0.75'ten
0.35'e adaptif tarayan bir esige gevsetildi - iki yeterli-buyuklukte
ayri cekirdek bulan EN SIKI (en guvenli) esik kullaniliyor. C2 kat2/
kat3'te dogru ayrim saglandi, B2'de regresyon kontrolu yapildi (kat2
hala dogru 2 karton, direk filtresinde sapma yok).

---

## SORUN 14 — Robot duvara/rafa sıkışıp döndürülünce haritada hayalet geometri

**Belirti**
Robot fiziksel olarak bir duvara/rafa çarpıp sıkıştığında ve o pozisyonda
teleop ile döndürmeye (`a`/`d`) devam edildiğinde, haritada bozulma/hayalet
geometri oluşuyor — daha önce dönüş sırasında görülen "çapraz hayalet duvar"
deseninden (bkz. `config/mapper_params_depo.yaml`'daki
`minimum_travel_heading`, `coarse_search_angle_offset`,
`angle_variance_penalty` ayarları) farklı ve bağımsız bir mekanizma.

**Sebep**
`turtlebot3_simulations/turtlebot3_gazebo/models/turtlebot3_waffle_pi/model.sdf`
içindeki `gz-sim-diff-drive-system` plugin'i (satır ~512-534) odometriyi
gövdenin gerçek dünya pozisyonundan değil, `wheel_left_joint`/
`wheel_right_joint`'in ölçülen açısal hızından kinematik olarak
hesaplıyor. Bu iki teker joint'inde (kamera joint'inin aksine, orada
`<limit><effort>10</effort>` var) **hiçbir `<effort>` (tork) limiti
tanımlı değil** — yani gövde bir engele sıkışıp fiziksel tepki kuvveti
alsa bile ODE'nin hız motoru komutlanan açısal hıza koşulsuz ulaşmaya
çalışıyor. Sonuç: tekerlekler "komutlandığı gibi dönüyormuş" gibi
raporlanıyor, diff-drive plugin bunu entegre edip `/odom`'a fantom
hareket olarak yazıyor, gövde yerinde saysa da SLAM'e "robot hareket
etti" diye yanlış bir prior besleniyor. `mapper_params_depo.yaml`'daki
`minimum_travel_distance`/`minimum_travel_heading` eşikleri bu durumu
engellemiyor, sadece geciktiriyor — sıkışma yeterince sürerse fantom
odom eşikleri de aşıp kötü bir scan-match'e yol açıyor.

Teker-zemin sürtünmesi (`mu`/`mu2 = 100000`, aynı dosyada wheel
collision'larda) neredeyse sonsuz olduğu için normal (çarpışmasız)
sürüşte klasik "teker kayması" bu mekanizmayla açıklanmıyor; sürüş
sırasında ara sıra görülen küçük bozulmalar muhtemelen ayrı bir etki
(dönüş/arama-penceresi kalıntısı veya raf kenarına hafif temas).

**Kök neden — kapsam dışı bırakıldı**
Gerçek düzeltme `turtlebot3_simulations` paketindeki `model.sdf`'e teker
joint'leri için gerçekçi bir `<effort>` limiti eklemek olurdu, ama bu
`depo_robotu` dışında bir sibling pakette workspace-level patch
gerektiriyor (bkz. CLAUDE.md "Workspace-level patches", Y-serisi
patch'ler). Sprint 1-3 altyapı zaman kutusunu aşmamak için şimdilik
ertelendi.

**Geçici çözüm (davranışsal)**
Haritalama sırasında robot bir yere çarparsa hemen `s` (force stop) ile
durulmalı; sıkışmış haldeyken dönmeye/hareket komutu vermeye devam
edilmemeli. Bkz. SORUN 10 — aynı `s`/boşluk force-stop mekanizması.

---

## SORUN 15 — `data_files` (yaml/json/sdf) install altında symlink DEĞİL, kopya

**Belirti**
`config/nav2_params_depo.yaml` (veya `araclar/adres_veritabani.json`,
`worlds/depo.sdf`) kaynakta düzenlenip `colcon build --symlink-install`
çalıştırılmadan test edilirse, Nav2/node'lar **eski değeri** kullanmaya
devam eder — hata vermez, davranış sessizce "değişmemiş" görünür. Bu,
`desired_linear_vel` hız ayarında bir "regresyon" şüphesine yol açmıştı
(2026-08-20); teşhis sonucu kaynak ile install kopyası her ikisi de aynı
(`1.0`) çıktı — o an aktif bir sorun yoktu, ama mekanizma gerçek.

**Sebep**
`--symlink-install` bayrağı `ament_python` paketlerinde sadece Python
modüllerini (`depo_robotu/*.py`) symlink'liyor. `setup.py`'daki
`data_files=` ile eklenen dosyalar (config/*.yaml, araclar/*.json,
worlds/*.sdf, launch/*.py) **her `colcon build`'da düz kopyalanıyor**,
symlink değil (`ls -la ~/staj_ws/install/depo_robotu/share/depo_robotu/...`
ile doğrulanabilir — `-rw-r--r--`, `lrwxrwxrwx` değil). Bu, colcon/
setuptools'un `ament_python` + `data_files` kombinasyonunda bilinen bir
sınırlama, bu projeye özgü bir hata değil.

**Kural**
`config/`, `araclar/`, `worlds/` altındaki herhangi bir dosyayı
düzenledikten sonra, çalıştırmadan/test etmeden önce MUTLAKA:
```bash
colcon build --symlink-install --packages-select depo_robotu
```
Aksi halde install/ altındaki eski kopya sessizce kullanılmaya devam eder.
Şüphede kalırsan: `diff <kaynak> ~/staj_ws/install/depo_robotu/share/depo_robotu/<aynı yol>`
ile ikisini karşılaştır.

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
- [ ] `kutu_tespit.py`'ye mavi kutu/raf direği ayrımı için `piksel_kat_hesapla`'nın
      hesapladığı yanal (raf boyunca) konuma göre kenar-bandı filtresi eklendi
      (`DIREK_X≈1.35 m`, tolerans 0.12 m). Doğru mesafede (1.4-1.8 m, rafa dik)
      test edildi; çoğu direk parçası artık doğru reddediliyor. **Ama gerçek
      mavi kutu (B2 örneğinde x=1.2 m) direğe (x=1.35 m) sadece 0.15 m
      mesafede, ikisi de kadrajın en kenarında — bu mesafede geometrik kestirim
      hatası bu 0.15 m'lik farktan büyük olabiliyor. Gerçek kutunun filtre
      tarafından yanlışlıkla elenmediği doğrulanmadı**, en yakın aday tespitin
      yükseklik uyumu da zayıftı (fark≈0.30 m, tolerans sınırında). Farklı
      mesafe/açılarda ve mümkünse envanterdeki bilinen konumla çapraz kontrol
      ile tekrar doğrulanmalı.
- [ ] Raflar arkası kapalı değil (sadece 2 direk + 3 ince tabla) — kamera
      boşluklardan bakınca aynı x'teki daha uzak bir rafı (örn. B2'nin 4 m
      arkasındaki A2) görebiliyor. `piksel_kat_hesapla`'daki `x=mesafe`
      düzlem varsayımı (LIDAR'ın **önündeki** rafa olan mesafeyi kullanır) bu
      şekilde görülen uzak nesneler için tamamen geçersiz bir yükseklik/adres
      üretir. B2 testinde envanterle eşleşmeyen küçük mavi/sarı tespitler
      bulundu; en olası açıklama bu ama kaynağı kesin doğrulanmadı. Henüz kod
      değişikliği yapılmadı, sadece gözlem/risk kaydı. **Güncelleme:**
      `tarama_kontrol.py` ile yapılan üç-katlı B2 taramasında bu artık
      sayısal olarak doğrulandı (bkz. SORUN 12) — kök neden aynı: tespitler
      rafa göre kapsamlanmıyor (shelf-scoped değil).

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
