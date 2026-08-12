#!/usr/bin/env python3
"""
Isin-duzlem kesisimi - Asama B.

Kameranin su anki (TF'ten okunan gercek) acisiyla hangi kata baktigini
hesaplar. Nesne tespiti yok; sadece TF + geometri dogrulamasi.
"""

import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Int32
from tf2_ros import Buffer, TransformListener
import tf_transformations


class KatTespit(Node):

    KAT_YUKSEKLIKLERI = {1: 0.63, 2: 1.18, 3: 1.68}  # kutu merkezi, kamera_kontrol.py ile ayni kongre
    KAT_TOLERANS = 0.30  # metre - bir katin "kabul" araligi

    def __init__(self):
        super().__init__('kat_tespit')

        # TF dinleyicisi: Buffer gecmis donusumleri tutar,
        # TransformListener /tf ve /tf_static topiclerini dinleyip
        # Buffer'i gunceller. Ikisi de sabit tutulmali (self. ile).
        self.tf_buffer = Buffer()
        self.tf_dinleyici = TransformListener(self.tf_buffer, self)

        self.mesafe = None
        self.scan_abone = self.create_subscription(
            LaserScan, '/scan', self.scan_geldi, 10)

        self.kat_yayinci = self.create_publisher(Int32, '/bakilan_kat', 10)

        # Periyodik kontrol - TF her an hazir olmayabilir (baslangicta
        # birkac saniye gecikme normal), o yuzden abone yerine timer.
        self.zamanlayici = self.create_timer(0.5, self.kontrol_et)

        self.get_logger().info('Kat tespit hazir. TF ve LIDAR bekleniyor.')

    def scan_geldi(self, mesaj):
        # kamera_kontrol.py ile ayni mantik: on ±60 derece, minimum mesafe
        n = len(mesaj.ranges)
        yariyay = int(math.radians(60) / mesaj.angle_increment)
        gecerli = []
        for i in range(-yariyay, yariyay + 1):
            d = mesaj.ranges[i % n]
            if (not math.isinf(d) and not math.isnan(d)
                    and mesaj.range_min < d < mesaj.range_max):
                gecerli.append(d)
        self.mesafe = min(gecerli) if gecerli else None

    def kontrol_et(self):
        if self.mesafe is None:
            self.get_logger().warn('Onumde olcum yok, hesap yapilamiyor.',
                                    throttle_duration_sec=3.0)
            return

        try:
            # base_footprint -> camera_link donusumu. rclpy.time.Time()
            # (bos) = "en son mevcut olan donusumu ver".
            donusum = self.tf_buffer.lookup_transform(
                'base_footprint', 'camera_link', rclpy.time.Time())
        except Exception as e:
            self.get_logger().warn(f'TF henuz hazir degil: {e}',
                                    throttle_duration_sec=3.0)
            return

        # --- 1) Kamera konumu (dunya/base_footprint cercevesinde) ---
        t = donusum.transform.translation
        kamera_konumu = (t.x, t.y, t.z)

        # --- 2) Kamera yonu: camera_link'te sabit (1,0,0) vektorunu,
        #        TF'ten gelen quaternion ile dondur ---
        q = donusum.transform.rotation
        donusum_matrisi = tf_transformations.quaternion_matrix(
            [q.x, q.y, q.z, q.w])
        yerel_ileri = (1.0, 0.0, 0.0, 0.0)  # 4. eleman 0 = "yon", "konum" degil
        yon = donusum_matrisi @ yerel_ileri
        yon_x, yon_y, yon_z = yon[0], yon[1], yon[2]

        # --- 3) Isini LIDAR mesafesi kadar ilerlet ---
        # LIDAR yatay duzlemde olctugu icin, isinin yatay bilesenindeki
        # (x-y) mesafesi "mesafe" kadar oldugunda t'yi buluyoruz.
        yatay_hiz = math.hypot(yon_x, yon_y)
        if yatay_hiz < 1e-6:
            self.get_logger().warn('Kamera tam dikey bakiyor, hesap gecersiz.')
            return
        t_param = self.mesafe / yatay_hiz

        hedef_z = kamera_konumu[2] + t_param * yon_z

        # --- 4) En yakin kati bul ---
        en_yakin_kat = min(
            self.KAT_YUKSEKLIKLERI,
            key=lambda k: abs(self.KAT_YUKSEKLIKLERI[k] - hedef_z))
        fark = abs(self.KAT_YUKSEKLIKLERI[en_yakin_kat] - hedef_z)

        if fark > self.KAT_TOLERANS:
            self.get_logger().warn(
                f'Hesaplanan yukseklik ({hedef_z:.2f} m) hicbir kata '
                f'yakin degil (en yakini kat {en_yakin_kat}, fark {fark:.2f} m).')
            return

        self.kat_yayinci.publish(Int32(data=en_yakin_kat))
        self.get_logger().info(
            f'Mesafe {self.mesafe:.2f} m, hesaplanan yukseklik {hedef_z:.2f} m '
            f'-> Kat {en_yakin_kat} (fark {fark:.2f} m)')


def main(args=None):
    rclpy.init(args=args)
    dugum = KatTespit()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()