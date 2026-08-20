#!/usr/bin/env python3
"""
Bir rafin onune elle (teleop ile) surulduktan sonra, AMCL'in o anda
inandigi GERCEK map-frame pose'unu (map -> base_link TF) okuyup
adres_veritabani.json'a yazan arac.

KOK SEBEP (bkz. PROJE_DOSYASI.md SS12): adres_veritabani.json'daki ilk 9
deger depo.sdf'teki GERCEK DUNYA (Gazebo world frame) koordinatlarindan
hesaplanmisti. Ama Nav2 hedefleri "map" frame'inde yorumlanir, ve SLAM
haritalamasi robot spawn noktasindan basladigi icin map frame'in kendi
origini gercek dunya originiyle CAKISMAZ (bkz. maps/depo_haritasi.yaml
origin alani). Bu yuzden burada HESAPLAMA degil OLCUM yapiliyor: robot
rafin tam onune elle surulur, o anda TF'in soyledigi pose dogrudan
kaydedilir.

Kullanim:
  ros2 run depo_robotu konum_yakala --ros-args -p raf:=A1
"""

import math
import time
from datetime import datetime

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from tf2_ros import Buffer, TransformListener

from depo_robotu.adres_veritabani_araclari import girdi_guncelle

# AMCL x/y kovaryansi (m^2) bu esigin ustundeyse lokalizasyon supheli
# sayilir - kesin bir fizik degil, deneme-yanilmayla secilmis kaba bir
# uyari esigi.
KOVARYANS_ESIGI = 0.05


class KonumYakala(Node):

    def __init__(self):
        super().__init__('konum_yakala')

        self.declare_parameter('raf', 'A1')
        self.raf_adi = self.get_parameter('raf').value

        # TF dinleyicisi: kat_tespit.py'deki ayni desen - Buffer gecmis
        # donusumleri tutar, TransformListener /tf ve /tf_static'i
        # dinleyip Buffer'i gunceller. Ikisi de node yasadigi surece
        # ayakta kalmali (self. ile referans tutuluyor).
        self.tf_buffer = Buffer()
        self.tf_dinleyici = TransformListener(self.tf_buffer, self)

        self.amcl_pose_abone = self.create_subscription(
            PoseWithCovarianceStamped, '/amcl_pose', self._amcl_pose_geldi, 10)
        self._son_kovaryans = None

    def _amcl_pose_geldi(self, mesaj):
        # 6x6 kovaryans matrisi satir-major duzlestirilmis: [0]=xx, [7]=yy.
        self._son_kovaryans = (mesaj.pose.covariance[0], mesaj.pose.covariance[7])

    def _kovaryans_kontrol(self):
        baslangic = time.monotonic()
        while self._son_kovaryans is None and time.monotonic() - baslangic < 3.0:
            rclpy.spin_once(self, timeout_sec=0.2)

        if self._son_kovaryans is None:
            self.get_logger().warn(
                "/amcl_pose mesaji gelmedi, lokalizasyon kalitesi kontrol "
                "edilemedi. Yine de devam ediliyor.")
            return

        xx, yy = self._son_kovaryans
        if xx > KOVARYANS_ESIGI or yy > KOVARYANS_ESIGI:
            self.get_logger().warn(
                f"AMCL kovaryansi yuksek (xx={xx:.4f}, yy={yy:.4f} m^2) - "
                "lokalizasyon belirsiz olabilir. Robotun rafin tam onunde "
                "ve dogru yonde oldugundan GOZLE emin ol. Yine de devam "
                "ediliyor - karar senin.")
        else:
            self.get_logger().info(
                f"AMCL kovaryansi iyi (xx={xx:.4f}, yy={yy:.4f} m^2).")

    def yakala(self):
        self._kovaryans_kontrol()

        self.get_logger().info(
            f"'{self.raf_adi}' icin map->base_link TF bekleniyor. Robotun "
            "rafin tam onunde ve dogru yonde durdugundan emin ol.")

        donusum = None
        baslangic = time.monotonic()
        while donusum is None and time.monotonic() - baslangic < 5.0:
            try:
                donusum = self.tf_buffer.lookup_transform(
                    'map', 'base_link', rclpy.time.Time())
            except Exception:
                rclpy.spin_once(self, timeout_sec=0.2)

        if donusum is None:
            self.get_logger().error(
                "map->base_link TF alinamadi (5 sn icinde denendi). "
                "AMCL/Nav2 calisiyor mu?")
            return

        x = donusum.transform.translation.x
        y = donusum.transform.translation.y

        # Quaternion -> yaw. adres_dogrula.py'de yaw -> quaternion donusumu
        # (robot yerde, roll=pitch=0 oldugu icin sadelesmis hali) soyle
        # yapiliyordu: qz = sin(yaw/2), qw = cos(yaw/2). Burada bunun
        # TERSI gerekiyor. tan(yaw/2) = qz/qw oldugundan yaw = 2*atan2(qz,
        # qw). Duz bolme (qz/qw) yerine atan2 kullanmamizin sebebi: qw=0
        # olan durumlarda (yaw = ±pi, robot tam geriye donuk) bolme sifira
        # bolme hatasi verir, atan2 bu durumu sorunsuz cozer. Ayni kisayol
        # NOTLAR.md SORUN 6'da da kullaniliyor.
        q = donusum.transform.rotation
        yaw = 2.0 * math.atan2(q.z, q.w)

        tarih = datetime.now().strftime('%Y-%m-%d')
        not_metni = f"elle surulup tf'den yakalandi, {tarih}"

        girdi_guncelle(self.raf_adi, 'dogrulandi', not_metni=not_metni,
                        x=x, y=y, yaw=yaw)

        self.get_logger().info(
            f"{self.raf_adi} icin yakalanan pose: x={x:.3f}, y={y:.3f}, "
            f"yaw={yaw:.4f} rad ({math.degrees(yaw):.1f} derece). Kaydedildi.")


def main(args=None):
    rclpy.init(args=args)
    dugum = KonumYakala()
    try:
        dugum.yakala()
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
