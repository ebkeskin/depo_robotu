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

        self.get_logger().info('Kamera kontrol hazir. /hedef_kat topicine 1, 2 veya 3 gonderin.')

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
            f'aci {aci:.3f} rad ({math.degrees(aci):.1f} derece)'
        )


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