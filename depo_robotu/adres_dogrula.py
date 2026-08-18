#!/usr/bin/env python3
"""
Sprint 3 - adres_veritabani.json'daki raf hedeflerini Nav2'ye gonderip
gozle dogrulamak icin kullanilan arac.

adres_veritabani.json'daki (x, y, yaw) degerleri depo.sdf TASARIM
koordinatlaridir, SLAM haritasindaki kucuk donuklukten (bkz. dosyanin
"uyari" alani) etkilenip etkilenmedigi bilinmiyor. Bu node NavigateToPose
action'ini dogrudan cagirir (nav2_simple_commander SARMALAYICISI
KULLANILMADI - ogrenme amacli, quaternion donusumu ve action client
akisi elle yazildi), sonucu (basarili/basarisiz, sure) yazdirir. Gercek
dogrulama gozle yapilir: robot rafa dik mi duruyor, uc katta da kamera
tilt sinirlarinin (-0.5..1.2 rad) icinde kaliyor mu.
"""

import math
import time

import rclpy
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


class AdresDogrula(Node):

    def __init__(self):
        super().__init__('adres_dogrula')

        self.declare_parameter('raf', 'A1')
        self.raf_adi = self.get_parameter('raf').value

        self.veritabani = self._veritabani_yukle()
        if self.raf_adi not in self.veritabani['raf_konumlari']:
            self.get_logger().error(
                f"'{self.raf_adi}' adres_veritabani.json'da yok. "
                f"Gecerli rafler: {list(self.veritabani['raf_konumlari'].keys())}")
            raise SystemExit(1)

        self.hedef = self.veritabani['raf_konumlari'][self.raf_adi]
        self._action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

    def _veritabani_yukle(self):
        yol = get_package_share_directory('depo_robotu') + '/araclar/adres_veritabani.json'
        import json
        with open(yol) as f:
            return json.load(f)

    def hedefe_git(self):
        x, y, yaw = self.hedef['x'], self.hedef['y'], self.hedef['yaw_rad']
        self.get_logger().info(
            f"'{self.raf_adi}' hedefine gidiliyor: x={x}, y={y}, "
            f"yaw={yaw:.4f} rad ({math.degrees(yaw):.1f} derece) "
            f"[durum: {self.hedef['durum']}]")

        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = x
        goal.pose.position.y = y
        # Yaw'i quaternion'a cevir: sadece z ekseni etrafinda donus oldugu
        # icin (robot yerde, roll=pitch=0) formul sadelesiyor:
        # qz = sin(yaw/2), qw = cos(yaw/2)
        goal.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.orientation.w = math.cos(yaw / 2.0)

        self.get_logger().info('navigate_to_pose action sunucusu bekleniyor...')
        self._action_client.wait_for_server()

        navigate_goal = NavigateToPose.Goal()
        navigate_goal.pose = goal

        baslangic = time.monotonic()
        gonderim_future = self._action_client.send_goal_async(navigate_goal)
        rclpy.spin_until_future_complete(self, gonderim_future)
        goal_handle = gonderim_future.result()

        if not goal_handle.accepted:
            self.get_logger().error('Hedef Nav2 tarafindan reddedildi.')
            return

        sonuc_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, sonuc_future)
        sure = time.monotonic() - baslangic

        durum = sonuc_future.result().status
        basarili = durum == GoalStatus.STATUS_SUCCEEDED
        self.get_logger().info(
            f"Sonuc: {'BASARILI' if basarili else 'BASARISIZ'} "
            f"(status={durum}), sure={sure:.1f} s")
        self.get_logger().info(
            f"Simdi RViz/Gazebo'da gozle kontrol et: robot '{self.raf_adi}' "
            "rafina dik mi duruyor, kamera tilt ile uc kati da gorebiliyor mu?")


def main(args=None):
    rclpy.init(args=args)
    dugum = AdresDogrula()
    try:
        dugum.hedefe_git()
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
