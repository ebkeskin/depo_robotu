#!/usr/bin/env python3
"""
Isin-duzlem kesisimi - Asama A (piksel bazli).

Goruntudeki herhangi bir pikselden isin atip hangi kata denk geldigini
hesaplar. Fareyle goruntuye tiklayarak test edilir - ilerde nesne
tespitinin (HSV, Sprint 2D) tikladigi yerin yerine tespit edilen
kutunun merkez pikseli gececek.

Mesafe hala LIDAR'dan geliyor (derinlik kameramiz yok, §4.2) - fark,
Asama B'deki sabit merkez isin yerine artik pikselin KENDI acisini
kullanmamiz.
"""

import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from tf2_ros import Buffer, TransformListener
import tf_transformations


class PikselKatTespit(Node):

    # kutu-merkezi kongre - kamera_kontrol.py ve kat_tespit.py ile ayni
    KAT_YUKSEKLIKLERI = {1: 0.63, 2: 1.18, 3: 1.68}
    KAT_TOLERANS = 0.30

    def __init__(self):
        super().__init__('piksel_kat_tespit')

        self.bridge = CvBridge()
        self.son_kare = None
        self.k_matrisi = None  # [fx, fy, cx, cy]
        self.mesafe = None

        self.tf_buffer = Buffer()
        self.tf_dinleyici = TransformListener(self.tf_buffer, self)

        self.create_subscription(
            CameraInfo, '/camera/camera_info', self.camera_info_geldi, 10)
        self.create_subscription(
            Image, '/camera/image_raw', self.goruntu_geldi, 10)
        self.create_subscription(
            LaserScan, '/scan', self.scan_geldi, 10)

        cv2.namedWindow('Piksel Kat Tespit')
        cv2.setMouseCallback('Piksel Kat Tespit', self.tiklama_geldi)

        # cv2 pencere olaylarini islemek icin periyodik zamanlayici
        self.create_timer(0.03, self.pencereyi_guncelle)

        self.get_logger().info(
            'Piksel kat tespit hazir. Goruntuye tiklayip test edin.')

    def camera_info_geldi(self, mesaj):
        if self.k_matrisi is None:
            k = mesaj.k
            self.k_matrisi = {'fx': k[0], 'fy': k[4], 'cx': k[2], 'cy': k[5]}
            self.get_logger().info(
                f'Kamera ic parametreleri alindi: fx={k[0]:.1f}, '
                f'fy={k[4]:.1f}, cx={k[2]:.1f}, cy={k[5]:.1f}')

    def goruntu_geldi(self, mesaj):
        self.son_kare = self.bridge.imgmsg_to_cv2(mesaj, desired_encoding='bgr8')

    def scan_geldi(self, mesaj):
        # kamera_kontrol.py / kat_tespit.py ile ayni mantik
        n = len(mesaj.ranges)
        yariyay = int(math.radians(60) / mesaj.angle_increment)
        gecerli = []
        for i in range(-yariyay, yariyay + 1):
            d = mesaj.ranges[i % n]
            if (not math.isinf(d) and not math.isnan(d)
                    and mesaj.range_min < d < mesaj.range_max):
                gecerli.append(d)
        self.mesafe = min(gecerli) if gecerli else None

    def tiklama_geldi(self, event, u, v, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if self.k_matrisi is None:
            self.get_logger().warn('Kamera ic parametreleri henuz gelmedi.')
            return
        if self.mesafe is None:
            self.get_logger().warn('Onumde LIDAR olcumu yok.')
            return

        # --- 1) Piksel -> optik cerceve isin yonu (pinhole model) ---
        fx, fy = self.k_matrisi['fx'], self.k_matrisi['fy']
        cx, cy = self.k_matrisi['cx'], self.k_matrisi['cy']
        x_norm = (u - cx) / fx
        y_norm = (v - cy) / fy
        yerel_yon = np.array([x_norm, y_norm, 1.0, 0.0])  # 4. eleman 0 = yon

        # --- 2) TF: optik cerceveden base_footprint'e donusum ---
        try:
            donusum = self.tf_buffer.lookup_transform(
                'base_footprint', 'camera_rgb_optical_frame', rclpy.time.Time())
        except Exception as e:
            self.get_logger().warn(f'TF alinamadi: {e}')
            return

        q = donusum.transform.rotation
        donusum_matrisi = tf_transformations.quaternion_matrix(
            [q.x, q.y, q.z, q.w])
        yon = donusum_matrisi @ yerel_yon
        yon_x, yon_y, yon_z = yon[0], yon[1], yon[2]

        t = donusum.transform.translation
        kamera_konumu = (t.x, t.y, t.z)

        # --- 3) Isini rafa (duz bir DUZLEM olarak) kesistir ---
        # Varsayim: robot rafa kabaca dik duruyor, LIDAR'in olctugu mesafe
        # robotun ileri (x) ekseninde rafa olan uzakligi veriyor.
        if yon_x < 1e-6:
            self.get_logger().warn('Isin ileri gitmiyor, hesap gecersiz.')
            return
        t_param = (self.mesafe - kamera_konumu[0]) / yon_x
        hedef_z = kamera_konumu[2] + t_param * yon_z

        # --- 4) En yakin kati bul ---
        en_yakin_kat = min(
            self.KAT_YUKSEKLIKLERI,
            key=lambda k: abs(self.KAT_YUKSEKLIKLERI[k] - hedef_z))
        fark = abs(self.KAT_YUKSEKLIKLERI[en_yakin_kat] - hedef_z)

        if fark > self.KAT_TOLERANS:
            self.get_logger().warn(
                f'Piksel ({u},{v}) -> yukseklik {hedef_z:.2f} m, '
                f'hicbir kata yakin degil (en yakini kat {en_yakin_kat}, '
                f'fark {fark:.2f} m).')
        else:
            self.get_logger().info(
                f'Piksel ({u},{v}) -> yukseklik {hedef_z:.2f} m '
                f'-> Kat {en_yakin_kat} (fark {fark:.2f} m)')

        # goruntude isaretle (bir sonraki karede kaybolur, bilgi amacli)
        if self.son_kare is not None:
            gosterim = self.son_kare.copy()
            cv2.circle(gosterim, (u, v), 8, (0, 255, 0), 2)
            cv2.putText(
                gosterim, f'Kat {en_yakin_kat} ({fark:.2f}m)', (u + 12, v),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow('Piksel Kat Tespit', gosterim)
            cv2.waitKey(1500)  # isaretlenmis kareyi bir sure goster

    def pencereyi_guncelle(self):
        if self.son_kare is not None:
            cv2.imshow('Piksel Kat Tespit', self.son_kare)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    dugum = PikselKatTespit()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    cv2.destroyAllWindows()
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()