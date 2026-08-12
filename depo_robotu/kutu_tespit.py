#!/usr/bin/env python3
"""
Nesne tespiti - Sprint 2D.

HSV renk maskeleme ile kutulari tespit eder, piksel_kat_tespit.py'deki
isin-duzlem mantigiyla hangi katta olduklarini hesaplar, boyutlarini
piksel alani + mesafeden kestirir, sonuclari /tespitler'e JSON olarak
yayinlar.

renk_probu.py ile olculen gercek HSV degerlerine dayanir:
  sari    H~28  S~172 V~138
  karton  H~17  S~94  V~114   <- raftan (asagida) S ile ayriliyor
  kirmizi H~0   S~197 V~132   (H=179 civari da kirmizi, HSV cemberi)
  yesil   H~60  S~166 V~129
  mavi    H~113 S~170 V~110   <- raf direginden (asagida) AYIRT EDILEMIYOR,
                                  sekil (en-boy orani) filtresi sart

BILINEN SINIR: mavi kutu ile rafin mavi destek direkleri HSV'de
neredeyse ozdes (H=113 vs H=109). Renkle ayrilamiyor, bounding-box
en-boy orani ile (direkler ince-uzun, kutular kareye yakin) filtreleniyor.
Bu filtre normal tarama mesafesinde (~1.5m) guvenilir; kameraya asiri
yakin cekimlerde (>1m yakinlik) direkler de kareye yakin gorunebilir,
o durumda yanlis pozitif riski var.
"""

import json
import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener
import tf_transformations


# HSV araliklari: (renk_adi -> [(alt, ust), ...])  -- kirmizi 2 aralik ister
RENK_ARALIKLARI = {
    'kirmizi': [
        (np.array([0, 120, 60]), np.array([8, 255, 255])),
        (np.array([172, 120, 60]), np.array([179, 255, 255])),
    ],
    'sari': [(np.array([20, 120, 60]), np.array([35, 255, 255]))],
    'yesil': [(np.array([45, 100, 60]), np.array([75, 255, 255]))],
    'mavi': [(np.array([100, 120, 60]), np.array([125, 255, 255]))],
    # karton: raf tablasiyla ayni H, ama DUSUK doygunluk (S) ile ayriliyor
    'karton': [(np.array([8, 60, 80]), np.array([25, 145, 170]))],
}

# renkleri ciziminde kullanmak icin BGR karsiliklari
CIZIM_RENKLERI = {
    'kirmizi': (0, 0, 255),
    'sari': (0, 255, 255),
    'yesil': (0, 255, 0),
    'mavi': (255, 0, 0),
    'karton': (19, 69, 139),
}

MIN_KONTUR_ALANI = 120       # px^2 - gurultuyu ele (200 -> 120: birkac cm poz
                              # sapmasinda kucuk/kismi kontur parcalarini elemiyordu)
MAX_KONTUR_ORANI = 0.5       # goruntunun yarisindan buyuk kontur = arka plan
EN_BOY_ALT_SINIR = 0.3       # direk filtresi (butun renklere uygulanir)
EN_BOY_UST_SINIR = 4.0       # 2.5 -> 4.0: yan yana duran iki kutu bazi pozlarda
                              # tek genis bloba birlesiyor (oran ~3.6), gercek
                              # kutuyu direk sanip elemesin diye ust sinir gevsetildi

KAT_YUKSEKLIKLERI = {1: 0.63, 2: 1.18, 3: 1.68}
KAT_TOLERANS = 0.35          # 0.30 -> 0.35: poz sapmasindan gelen z-tahmin
                              # gurultusune pay birakildi (kat atamasi zaten
                              # en-yakin mantigiyla yapiliyor, cakisma riski yok)

# Raf direk konumu filtresi: en-boy orani direkleri hep elemiyor (bkz.
# NOTLAR.md SORUN 12) - direkler rafin en kenarinda oldugundan genis FOV'da
# yandan/capraz gorunuyor ve raf tablalari tarafindan boluniyor, boylece
# kareye yakin kucuk parcalara ayrilip filtreyi geciyor. Piksel_kat_hesapla
# zaten ray-plane kesisiminde yanal (raf boyunca) konumu hesapliyor; bu
# konum direk merkezine (RAF_UZUNLUK'tan turetilmis, kutu_uret.py'deki
# sol_kenar/sag_kenar ile ayni) yakinsa tespit reddediliyor.
RAF_UZUNLUK = 2.8            # kutu_uret.py ile ayni
DIREK_KENAR_PAYI = 0.05      # kutu_uret.py'deki sol_kenar/sag_kenar payi
DIREK_X = RAF_UZUNLUK / 2 - DIREK_KENAR_PAYI   # = 1.35
# En kucuk kutu (0.30 m) kenara yaslandiginda merkezi direkten sadece 0.15 m
# uzakta olabiliyor (kutu_uret.py yerlesim geometrisinden gelen minimum).
# 0.12'lik tolerans bu kutuyu 0.03 m pay ile ayirt ediyordu; birkac cm'lik
# poz sapmasi yanal_konum tahminini bu banda itip gercek kutuyu direk sanip
# eliyordu. Payi buyutmek icin tolerans BUYUTULMEDI, KUCULTULDU (0.08) - amac
# gercek kenar kutusuna daha genis guvenlik marji birakmak.
DIREK_TOLERANS = 0.08        # metre


class KutuTespit(Node):

    def __init__(self):
        super().__init__('kutu_tespit')

        self.bridge = CvBridge()
        self.son_kare = None
        self.k_matrisi = None
        self.mesafe = None

        self.tf_buffer = Buffer()
        self.tf_dinleyici = TransformListener(self.tf_buffer, self)

        self.create_subscription(
            CameraInfo, '/camera/camera_info', self.camera_info_geldi, 10)
        self.create_subscription(
            Image, '/camera/image_raw', self.goruntu_geldi, 10)
        self.create_subscription(
            LaserScan, '/scan', self.scan_geldi, 10)

        self.tespit_yayinci = self.create_publisher(String, '/tespitler', 10)

        cv2.namedWindow('Kutu Tespit')
        # ~2 Hz'de bir isle - her karede degil, CPU'yu bosa yakmayalim
        self.create_timer(0.5, self.tespit_dongusu)

        self.get_logger().info('Kutu tespit hazir.')

    def camera_info_geldi(self, mesaj):
        if self.k_matrisi is None:
            k = mesaj.k
            self.k_matrisi = {'fx': k[0], 'fy': k[4], 'cx': k[2], 'cy': k[5]}

    def goruntu_geldi(self, mesaj):
        self.son_kare = self.bridge.imgmsg_to_cv2(mesaj, desired_encoding='bgr8')

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

    def piksel_kat_hesapla(self, u, v):
        """piksel_kat_tespit.py ile ayni mantik - (kat, fark, yanal_konum) donuyor.

        yanal_konum: isinin x=mesafe duzlemini kestigi noktanin, raf boyunca
        (soldan saga) robotun merkez hattina gore konumu. Robot rafa dik ve
        ortali durdugundan bu deger dogrudan raf-yerel x koordinatiyla
        kiyaslanabiliyor (direk filtresi icin).
        """
        fx, fy = self.k_matrisi['fx'], self.k_matrisi['fy']
        cx, cy = self.k_matrisi['cx'], self.k_matrisi['cy']
        x_norm = (u - cx) / fx
        y_norm = (v - cy) / fy
        yerel_yon = np.array([x_norm, y_norm, 1.0, 0.0])

        try:
            donusum = self.tf_buffer.lookup_transform(
                'base_footprint', 'camera_rgb_optical_frame', rclpy.time.Time())
        except Exception:
            return None, None, None

        q = donusum.transform.rotation
        donusum_matrisi = tf_transformations.quaternion_matrix([q.x, q.y, q.z, q.w])
        yon = donusum_matrisi @ yerel_yon
        yon_x, yon_y, yon_z = yon[0], yon[1], yon[2]

        t = donusum.transform.translation
        kamera_konumu = (t.x, t.y, t.z)

        if yon_x < 1e-6:
            return None, None, None
        t_param = (self.mesafe - kamera_konumu[0]) / yon_x
        hedef_z = kamera_konumu[2] + t_param * yon_z
        yanal_konum = kamera_konumu[1] + t_param * yon_y

        en_yakin_kat = min(
            KAT_YUKSEKLIKLERI, key=lambda k: abs(KAT_YUKSEKLIKLERI[k] - hedef_z))
        fark = abs(KAT_YUKSEKLIKLERI[en_yakin_kat] - hedef_z)
        if fark > KAT_TOLERANS:
            return None, fark, yanal_konum
        return en_yakin_kat, fark, yanal_konum

    def boyut_kestir(self, genislik_px):
        if self.k_matrisi is None or self.mesafe is None:
            return 'bilinmiyor'
        fx = self.k_matrisi['fx']
        fiziksel_genislik = genislik_px * self.mesafe / fx
        if fiziksel_genislik > 0.48:
            return 'buyuk'
        elif fiziksel_genislik > 0.35:
            return 'orta'
        return 'kucuk'

    def _birlesik_konturu_ayir(self, kontur):
        """Bitisik duran iki kutunun HSV maskede tek kontura birlesmesini
        distance-transform + watershed ile ayirir (bkz. NOTLAR.md - iki
        karton kutu tek genis bloba birlesiyordu, MORPH_CLOSE kernelini
        kucultmek/kaldirmak cozmedi cunku kutular hamur maskede zaten
        birbirine degiyor, morfolojik kapatmadan gelen bir kopru degil).

        Tek kutuluk konturlarda mesafe haritasinin tek bir tepe bolgesi
        olur -> bolme yapilmaz, orijinal bounding rect aynen doner.
        """
        x, y, w, h = cv2.boundingRect(kontur)
        alt_maske = np.zeros((h, w), np.uint8)
        cv2.drawContours(alt_maske, [kontur], -1, 255, thickness=cv2.FILLED, offset=(-x, -y))

        mesafe_haritasi = cv2.distanceTransform(alt_maske, cv2.DIST_L2, 5)
        tepe_degeri = mesafe_haritasi.max()
        if tepe_degeri < 1e-3:
            return [(x, y, w, h)]

        _, on_plan = cv2.threshold(mesafe_haritasi, 0.5 * tepe_degeri, 255, cv2.THRESH_BINARY)
        on_plan = on_plan.astype(np.uint8)
        n_bilesen, etiketler = cv2.connectedComponents(on_plan)
        if n_bilesen <= 2:      # arka plan (0) + tek nesne cekirdegi -> bolme gerekmiyor
            return [(x, y, w, h)]

        etiketler = etiketler + 1
        bilinmeyen = cv2.subtract(alt_maske, on_plan)
        etiketler[bilinmeyen == 255] = 0
        renkli = cv2.cvtColor(alt_maske, cv2.COLOR_GRAY2BGR)
        cv2.watershed(renkli, etiketler)

        sonuc = []
        for etiket in range(2, n_bilesen + 1):
            parca = np.uint8(etiketler == etiket) * 255
            alt_konturlar, _ = cv2.findContours(parca, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for ak in alt_konturlar:
                if cv2.contourArea(ak) < MIN_KONTUR_ALANI * 0.5:
                    continue
                ax, ay, aw, ah = cv2.boundingRect(ak)
                sonuc.append((x + ax, y + ay, aw, ah))

        return sonuc if sonuc else [(x, y, w, h)]

    def tespit_dongusu(self):
        if self.son_kare is None or self.k_matrisi is None or self.mesafe is None:
            return

        goruntu = self.son_kare.copy()
        hsv = cv2.cvtColor(goruntu, cv2.COLOR_BGR2HSV)
        goruntu_alani = goruntu.shape[0] * goruntu.shape[1]

        tespitler = []

        for renk, araliklar in RENK_ARALIKLARI.items():
            maske = None
            for alt, ust in araliklar:
                parca = cv2.inRange(hsv, alt, ust)
                maske = parca if maske is None else cv2.bitwise_or(maske, parca)

            # gurultu temizligi
            cekirdek = np.ones((5, 5), np.uint8)
            maske = cv2.morphologyEx(maske, cv2.MORPH_OPEN, cekirdek)
            maske = cv2.morphologyEx(maske, cv2.MORPH_CLOSE, cekirdek)

            konturlar, _ = cv2.findContours(
                maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            kutu_kutulari = []
            for kontur in konturlar:
                alan = cv2.contourArea(kontur)
                if alan < MIN_KONTUR_ALANI or alan > goruntu_alani * MAX_KONTUR_ORANI:
                    continue
                kutu_kutulari.extend(self._birlesik_konturu_ayir(kontur))

            for x, y, w, h in kutu_kutulari:
                oran = w / float(h) if h > 0 else 0
                if oran < EN_BOY_ALT_SINIR or oran > EN_BOY_UST_SINIR:
                    continue  # muhtemelen raf diregi (ince-uzun)

                merkez_u, merkez_v = x + w // 2, y + h // 2
                kat, fark, yanal_konum = self.piksel_kat_hesapla(merkez_u, merkez_v)
                if kat is None:
                    continue
                if yanal_konum is not None and abs(abs(yanal_konum) - DIREK_X) <= DIREK_TOLERANS:
                    continue  # raf diregi konumuna denk geliyor

                boyut = self.boyut_kestir(w)

                tespitler.append({
                    'renk': renk, 'boyut': boyut, 'kat': kat,
                    'piksel': [merkez_u, merkez_v], 'fark_m': round(fark, 3),
                })

                bgr = CIZIM_RENKLERI[renk]
                cv2.rectangle(goruntu, (x, y), (x + w, y + h), bgr, 2)
                cv2.putText(
                    goruntu, f'{renk} {boyut} K{kat}', (x, y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, bgr, 2)

        if tespitler:
            mesaj = String()
            mesaj.data = json.dumps(tespitler, ensure_ascii=False)
            self.tespit_yayinci.publish(mesaj)
            self.get_logger().info(f'{len(tespitler)} tespit -> /tespitler')

        cv2.imshow('Kutu Tespit', goruntu)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    dugum = KutuTespit()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    cv2.destroyAllWindows()
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()