#!/usr/bin/env python3
"""
Sprint 5 madde 1 - llm_servis (FastAPI) ile ROS 2 arasindaki kopru.

KARAR (PROJE_DOSYASI.md Sprint 4 "KARAR VERILDI"): llm_servis ROS 2'den
bagimsiz kalmaya devam ediyor; koprunun yonu ROS 2 -> FastAPI. Bu node
/komut topicinden dogal dil metnini alir, http://localhost:8000/komut
adresine HTTP POST atar, donen sorguyu (sadece tip:adres) tarama_pozisyonlari.json
ile (x, y, yaw) hedefine cevirip Nav2'ye NavigateToPose action'i olarak
gonderir. Navigasyon basariyla tamamlandiginda sorgudaki kat bilgisi
/hedef_kat topicine yayinlanir (kamera_kontrol.py bunu dinleyip kamerayi
o katin acisina cevirir). tip:arama / tip:sayim sonuclari (navigasyon
gerektirmiyor) sadece loglanir.

llm_servis kendi pip ortaminda calisan ayri bir surec oldugu icin
buradaki JSON ayrisimi pydantic semasini (sorgu_semasi.py) DEGIL, duz
dict.get() kullanir - iki surec birbirinin Python bagimliliklarini
paylasmaz.

BILINCLI SINIR: /komut geldiginde HTTP istegi bu callback icinde
BLOKLAYICI olarak yapiliyor (requests.post). LLM cevabi birkac saniye
surebiliyor, bu sure boyunca dugum baska /komut mesaji islemez. Tekli
interaktif kullanim (bir komut - bir sonuc) icin yeterli, coklu-istemci
senaryosu icin executor/thread onerilir (henuz yapilmadi).
"""

import json
from pathlib import Path

import requests
import rclpy
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Int32, String


class NavigasyonKoprusu(Node):

    LLM_SERVIS_URL = 'http://localhost:8000/komut'
    HTTP_ZAMAN_ASIMI = 30.0  # s - Gemini cevabi bazen birkac saniye surebiliyor

    def __init__(self):
        super().__init__('navigasyon_koprusu')

        self.tarama_pozisyonlari = self._tarama_pozisyonlari_yukle()
        self._son_hedef_kat = None

        self.komut_abone = self.create_subscription(
            String, '/komut', self._komut_geldi, 10)

        self.hedef_kat_yayinci = self.create_publisher(Int32, '/hedef_kat', 10)

        self._action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.get_logger().info('navigate_to_pose action sunucusu bekleniyor...')
        self._action_client.wait_for_server()

        self.get_logger().info(
            "Navigasyon koprusu hazir. /komut topicine dogal dil metni gonderin "
            f"(orn. \"A1'in 3. katina git\"). llm_servis: {self.LLM_SERVIS_URL}")

    def _tarama_pozisyonlari_yukle(self) -> dict:
        yol = Path(get_package_share_directory('depo_robotu')) / 'araclar' / 'tarama_pozisyonlari.json'
        with open(yol) as f:
            return json.load(f)

    def _komut_geldi(self, mesaj: String) -> None:
        metin = mesaj.data
        self.get_logger().info(f'Komut alindi: {metin!r}')

        try:
            yanit = requests.post(
                self.LLM_SERVIS_URL, json={'metin': metin}, timeout=self.HTTP_ZAMAN_ASIMI)
            yanit.raise_for_status()
            sonuc = yanit.json()
        except requests.RequestException as hata:
            self.get_logger().error(f'llm_servis cagrisi basarisiz: {hata}')
            return

        if not sonuc.get('basarili'):
            self.get_logger().error(f"Sorgu cozulemedi: {sonuc.get('hata')}")
            return

        if sonuc.get('belirsiz'):
            self.get_logger().info(
                f"Sorgu belirsiz: {sonuc.get('eslesme_sayisi')} eslesme bulundu, "
                "navigasyon baslatilmadi.")
            return

        sorgu = sonuc.get('sorgu') or {}
        if sorgu.get('tip') != 'adres':
            self.get_logger().info(
                f"'{sorgu.get('tip')}' tipi navigasyon gerektirmiyor, sonuc: {sonuc}")
            return

        raf = sorgu.get('raf')
        kat = sorgu.get('kat')
        if raf not in self.tarama_pozisyonlari:
            self.get_logger().error(f"'{raf}' tarama_pozisyonlari.json'da yok.")
            return

        self.get_logger().info(f"Hedef: raf={raf}, kat={kat} -> Nav2'ye gonderiliyor.")
        self._son_hedef_kat = kat
        self._hedefe_git(self.tarama_pozisyonlari[raf])

    def _hedefe_git(self, pozisyon: dict) -> None:
        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = pozisyon['x']
        goal.pose.position.y = pozisyon['y']
        goal.pose.orientation.z = pozisyon['quat_z']
        goal.pose.orientation.w = pozisyon['quat_w']

        navigate_goal = NavigateToPose.Goal()
        navigate_goal.pose = goal

        gonderim_future = self._action_client.send_goal_async(navigate_goal)
        gonderim_future.add_done_callback(self._hedef_kabul_edildi)

    def _hedef_kabul_edildi(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Hedef Nav2 tarafindan reddedildi.')
            return

        sonuc_future = goal_handle.get_result_async()
        sonuc_future.add_done_callback(self._navigasyon_tamamlandi)

    def _navigasyon_tamamlandi(self, future) -> None:
        durum = future.result().status
        basarili = durum == GoalStatus.STATUS_SUCCEEDED
        self.get_logger().info(
            f"Navigasyon sonucu: {'BASARILI' if basarili else 'BASARISIZ'} (status={durum})")

        if basarili and self._son_hedef_kat is not None:
            self.hedef_kat_yayinci.publish(Int32(data=self._son_hedef_kat))
            self.get_logger().info(f'/hedef_kat yayinlandi: {self._son_hedef_kat}')


def main(args=None):
    rclpy.init(args=args)
    dugum = NavigasyonKoprusu()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
