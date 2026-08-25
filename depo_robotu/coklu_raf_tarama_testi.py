#!/usr/bin/env python3
"""
Sprint 6 - teleport turu: 9 raf uzerinde tarama_kontrol.py'yi otomatik
kosturup ham raporlari + tur suresini + robotun bilinen dunya pozunu
kaydeder. Bu script UCTEN UCA 3 metrigi (tarama suresi, kat-bazli
dogruluk, konumlandirma hatasi) besleyen HAM VERIYI toplar -- analiz
(kat-bazli dogruluk hesabi, konum_donusum.py ile Oklid mesafesi) AYRI
bir scriptte (offline, ROS gerektirmez) yapilacak, bu ikili ayrim
Sprint 6'daki dogruluk_olcum.py ile ayni desendir (once TOPLA, sonra
ANALIZ ET).

NEDEN TELEPORT, NAV2 DEGIL: Sprint 5 Madde 5 (oracle_algi_karsilastirma.py)
ile AYNI mimari gerekce -- envanter.json WORLD-frame, Nav2/AMCL MAP-frame;
world/map karisikligindan (PROJE_DOSYASI.md SS12 KOK SEBEP) kacinmanin tek
yolu robotu 'gz service set_pose' ile DOGRUDAN WORLD-frame'e teleport
etmek. Yan fayda: NOTLAR.md SORUN 18'e (Nav2 spawn civari sistematik
basarisizlik) hic takilmiyor.

TILT vs SABIT KAMERA: bu script IKI DURUM ICIN DE BIREBIR AYNI calisir --
fark tamamen OPERASYONEL (kamera_kontrol.py'nin o oturumda calisip
calismadigi + 'sabit' turdan once bir kerelik `ros2 topic pub -1
/kamera_acisi std_msgs/msg/Float64 "data: 0.0"`). Script'e bir bayrak
EKLENMEDI cunku kod tarafinda hicbir fark yok; sadece --ros-args -p
etiket:=sabit ile CIKTI DOSYASI ayri tutuluyor (iki turun verisi
birbirini EZMESIN diye).

tarama_kontrol.py'ye HICBIR DEGISIKLIK yapilmadi -- subprocess olarak
navigasyon_koprusu.py'deki AYNI desenle (`_tarama_baslat`) baslatilip
/tarama_raporu dinlenir.

Kullanim:
  ros2 run depo_robotu coklu_raf_tarama_testi                          # 9 raf, etiket=tilt
  ros2 run depo_robotu coklu_raf_tarama_testi --ros-args -p raf:=B2
  ros2 run depo_robotu coklu_raf_tarama_testi --ros-args -p etiket:=sabit
"""

import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String

RAF_YARI_DERINLIK = 0.4   # m - kutu_uret.py RAF_DERINLIK=0.8'in yarisi (oracle_algi_karsilastirma.py ile AYNI)
KORIDOR_PAYI = 1.6        # m - tarama_pozisyonu_hesapla.py D_TARAMA ile AYNI

TUM_RAFLAR = ['A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'C1', 'C2', 'C3']

TELEPORT_Z = 0.01  # m - oracle_algi_karsilastirma.py ile AYNI (gz model -p ile gozlendi)

TARAMA_ZAMAN_ASIMI_SN = 90.0  # bir rafin taranmasi icin ust sinir (3 kat x kilit+yerlesme+toplama, bol payli)


class CokluRafTaramaTesti(Node):

    def __init__(self):
        super().__init__('coklu_raf_tarama_testi')

        self.declare_parameter('raf', '')
        istenen = self.get_parameter('raf').value
        self.raflar = [istenen] if istenen else list(TUM_RAFLAR)

        self.declare_parameter('etiket', 'tilt')
        self.etiket = self.get_parameter('etiket').value

        self.envanter = self._envanter_yukle()
        self._son_rapor = None
        self._beklenen_raf = None
        self._tarama_proc = None

        self.create_subscription(String, '/tarama_raporu', self._tarama_raporu_geldi, 10)

        self.get_logger().info(
            f"Coklu raf tarama testi hazir. Raflar: {self.raflar}, etiket: '{self.etiket}'.")

    def _envanter_yukle(self) -> dict:
        yol = Path(get_package_share_directory('depo_robotu')) / 'araclar' / 'envanter.json'
        with open(yol, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _standoff_pozu_hesapla(raf_x: float, raf_y: float, yon: str):
        """oracle_algi_karsilastirma.py ile BIREBIR AYNI -- DUNYA-cercevesi
        (x, y, yaw) standart tarama duruşu."""
        geri_cekme = RAF_YARI_DERINLIK + KORIDOR_PAYI
        if yon == 'guney':
            return raf_x, raf_y - geri_cekme, math.pi / 2
        return raf_x, raf_y + geri_cekme, -math.pi / 2

    def _teleport_et(self, x: float, y: float, yaw: float) -> None:
        # oracle_algi_karsilastirma.py ile AYNI yontem (ros_gz_bridge servis
        # koprusu bozuk, gz service CLI'si dogrudan kullaniliyor).
        qz = math.sin(yaw / 2)
        qw = math.cos(yaw / 2)
        req = (
            f'name: "waffle_pi" position: {{x: {x}, y: {y}, z: {TELEPORT_Z}}} '
            f'orientation: {{x: 0, y: 0, z: {qz}, w: {qw}}}'
        )
        subprocess.run(
            ['gz', 'service', '-s', '/world/default/set_pose',
             '--reqtype', 'gz.msgs.Pose', '--reptype', 'gz.msgs.Boolean',
             '--timeout', '3000', '--req', req],
            check=True, capture_output=True,
        )

    def _tarama_raporu_geldi(self, mesaj: String) -> None:
        if self._beklenen_raf is None:
            return
        try:
            rapor = json.loads(mesaj.data)
        except json.JSONDecodeError:
            return
        if rapor.get('raf') != self._beklenen_raf:
            return
        self._son_rapor = rapor

    def _tarama_procu_sonlandir(self) -> None:
        """start_new_session=True ile acilan surec GRUBUNUN tamamini oldurur
        (bkz. _raf_tara'daki not) -- tek basina proc.terminate() torun
        tarama_kontrol node'unu yetim birakiyordu."""
        proc = self._tarama_proc
        if proc is None or proc.poll() is not None:
            return
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            os.killpg(pgid, signal.SIGKILL)
            proc.wait(timeout=5.0)
        except ProcessLookupError:
            pass

    def _raf_tara(self, raf: str) -> dict:
        bilgi = self.envanter.get('raf_konumlari', {}).get(raf)
        if bilgi is None:
            self.get_logger().warn(f"'{raf}' envanter.json raf_konumlari'nda yok, atlandi.")
            return {'raf': raf, 'hata': 'raf_konumlari eksik'}

        raf_x, raf_y, yon = bilgi['x'], bilgi['y'], bilgi['yon']
        robot_x, robot_y, yaw = self._standoff_pozu_hesapla(raf_x, raf_y, yon)

        self._teleport_et(robot_x, robot_y, yaw)
        time.sleep(1.0)  # fizigin/LIDAR'in yerlesmesi icin (oracle_algi_karsilastirma.py ile AYNI)

        # navigasyon_koprusu.py'nin _tarama_baslat'i ile AYNI komut.
        # start_new_session=True: 'ros2 run' KENDI ICINDE subprocess.Popen ile
        # bir TORUN surec baslatiyor (exec-replace DEGIL, dogrulandi:
        # ros2run.api.run_executable kaynagi) -- bu yuzden bize sadece
        # 'ros2 run' PID'i doner, gercek tarama_kontrol PID'i degil. Ayri bir
        # sureç grubu acip grubun TAMAMINI (_tarama_procu_sonlandir'da)
        # oldurmezsek, torun yetim kalip ARKA PLANDA CALISMAYA DEVAM EDER
        # (canli testte boyle oldugu 'ros2 node list' ile dogrulandi -- 9
        # rafin hepsinde yetim tarama_kontrol node'u kaldi).
        komut = ['ros2', 'run', 'depo_robotu', 'tarama_kontrol',
                 '--ros-args', '-p', f'raf:={raf}']
        self._son_rapor = None
        self._beklenen_raf = raf
        self._tarama_proc = subprocess.Popen(komut, start_new_session=True)

        baslangic = time.monotonic()
        while self._son_rapor is None and time.monotonic() - baslangic < TARAMA_ZAMAN_ASIMI_SN:
            rclpy.spin_once(self, timeout_sec=0.2)
        sure = time.monotonic() - baslangic

        self._tarama_procu_sonlandir()
        self._beklenen_raf = None

        if self._son_rapor is None:
            self.get_logger().warn(f"'{raf}': /tarama_raporu {TARAMA_ZAMAN_ASIMI_SN}s icinde gelmedi.")
            return {'raf': raf, 'hata': 'zaman asimi', 'sure_saniye': round(sure, 1)}

        self.get_logger().info(f"'{raf}': tarandi, {sure:.1f} s surdu.")
        return {
            'raf': raf,
            'robot_x': robot_x, 'robot_y': robot_y, 'yaw': yaw, 'yon': yon,
            'sure_saniye': round(sure, 1),
            'rapor': self._son_rapor,
        }

    def calistir(self) -> list:
        sonuclar = []
        self.get_logger().info(f'{len(self.raflar)} raf taranacak...')
        for raf in self.raflar:
            sonuclar.append(self._raf_tara(raf))
        return sonuclar

    def sonuclari_kaydet(self, sonuclar: list) -> None:
        yol = (Path(get_package_share_directory('depo_robotu')) / 'araclar'
               / f'coklu_raf_ham_veri_{self.etiket}.json')
        with open(yol, 'w', encoding='utf-8') as f:
            json.dump({
                'etiket': self.etiket,
                'metodoloji': (
                    "Nav2 KULLANILMADI -- her raf icin 'gz service set_pose' ile "
                    'dogrudan WORLD-frame standart tarama pozuna teleport edilip '
                    "gercek tarama_kontrol.py subprocess'i (DEGISTIRILMEDEN) "
                    "calistirildi. 'tilt' etiketi: kamera_kontrol.py normal "
                    "calisirken (dinamik acilandirma). 'sabit' etiketi: "
                    "kamera_kontrol.py CALISTIRILMADAN, /kamera_acisi'ne bir "
                    'kerelik 0.0 yayinlanip acinin sabit kaldigi durum.'
                ),
                'sonuclar': sonuclar,
            }, f, ensure_ascii=False, indent=2)
        self.get_logger().info(f'Sonuclar kaydedildi: {yol}')


def main(args=None):
    rclpy.init(args=args)
    dugum = CokluRafTaramaTesti()
    try:
        sonuclar = dugum.calistir()
        dugum.sonuclari_kaydet(sonuclar)
    except KeyboardInterrupt:
        pass
    finally:
        dugum._tarama_procu_sonlandir()
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
