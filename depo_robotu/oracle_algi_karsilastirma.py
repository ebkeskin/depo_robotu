#!/usr/bin/env python3
"""
Sprint 5 roadmap madde 5 - Oracle vs algi mesafe karsilastirmasi.

BULGU (24 Agustos 2026, bu ozelligi planlarken): PROJE_DOSYASI.md SS7
"2C" tablosunda "Mesafe: oracle modu" ve "Mesafe: algi modu (line
fitting)" satirlarinin IKISI de isaretsizdi (bilincli erteleme, bkz.
SS12) -- projede fiilen calisan TEK mesafe kaynagi, kamera_kontrol.py/
kat_tespit.py/kutu_tespit.py/piksel_kat_tespit.py'de tekrarlanan tek-nokta
LIDAR minimum'u (self.mesafe). Kullanicinin onayladigi kapsam: oracle
modu burada YENI yazildi; "algi" tarafi icin sifirdan bir cizgi uydurma
(line fitting) YAZILMADI -- zaten var olan LIDAR-minimum yaklasimi
kullanildi (asagidaki ALGI MESAFESI bolumune bkz., bu bilinçli bir
sadelestirme, "line fitting" diye ABARTILMIYOR).

NEDEN TELEPORT, NAV2 DEGIL (mimari zorunluluk, sadece kolaylik degil):
envanter.json'un raf_konumlari alani Gazebo WORLD-frame (tasarim)
koordinatlaridir. Nav2/AMCL ise MAP-frame'de calisir. Nav2 ile gidip
sonra oracle mesafeyi envanter.json'a karsi hesaplamak, PROJE_DOSYASI.md
SS12 KOK SEBEP'te iki kez yasanan world/map karisikligi hatasini bir
kez daha tekrarlardi. Bu yuzden robot `gz service set_pose` ile
DOGRUDAN WORLD-frame'e teleport edilir (Sprint 2E'nin 9-raf testiyle
ayni yontem) -- boylece oracle hesabi ile envanter.json AYNI cercevede
kalir, donusum riski yok. Yan fayda: NOTLAR.md SORUN 18'deki (Nav2
planlayicisinin spawn noktasi civarinda sistematik basarisizligi)
sorununa hic takilmiyor.

ORACLE MESAFESI: robotun (teleport ile BILINEN, olculmemis) dunya-cercevesi
pozu ile rafin on yuzu arasindaki GEOMETRIK hesap -- RAF_YARI_DERINLIK
sabiti kutu_uret.py/haritadan_adres_cikar.py ile AYNI (0.4 m).

ALGI MESAFESI -- BILINEN SINIR (rapor bunu acikca belirtir): bu bir
cizgi uydurma (line fitting) DEGIL. kat_tespit.py'deki scan_geldi ile
BIREBIR AYNI mantik (on +-60 derece, TEK NOKTA minimum) -- kod tekrari
BILINCLI (bkz. CLAUDE.md "intentional convention"). Ayni x=mesafe duzlem
varsayiminin (PROJE_DOSYASI.md SS12) tasidigi mimari sinirlamayi bu da
tasir: yandaki bir kutu/direk "raf" sanilabilir, gercek bir yuzeye
uydurma degildir.

Kullanim:
  ros2 run depo_robotu oracle_algi_karsilastirma                    # 9 raf
  ros2 run depo_robotu oracle_algi_karsilastirma --ros-args -p raf:=B2
"""

import json
import math
import subprocess
import time
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

RAF_YARI_DERINLIK = 0.4   # m - kutu_uret.py RAF_DERINLIK=0.8'in yarisi
KORIDOR_PAYI = 1.6        # m - tarama_pozisyonu_hesapla.py D_TARAMA ile ayni

TUM_RAFLAR = ['A1', 'A2', 'A3', 'B1', 'B2', 'B3', 'C1', 'C2', 'C3']

TELEPORT_Z = 0.01  # m - robotun dogal durus yuksekligi (gz model -p ile gozlendi)


class OracleAlgiKarsilastirma(Node):

    def __init__(self):
        super().__init__('oracle_algi_karsilastirma')

        self.declare_parameter('raf', '')
        istenen = self.get_parameter('raf').value
        self.raflar = [istenen] if istenen else list(TUM_RAFLAR)

        self.envanter = self._envanter_yukle()
        self._son_scan = None
        self.create_subscription(LaserScan, '/scan', self._scan_geldi, 10)

        self.get_logger().info(
            f'Oracle vs algi karsilastirmasi hazir. Raflar: {self.raflar}')

    def _envanter_yukle(self) -> dict:
        yol = Path(get_package_share_directory('depo_robotu')) / 'araclar' / 'envanter.json'
        with open(yol, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _scan_geldi(self, mesaj: LaserScan) -> None:
        self._son_scan = mesaj

    @staticmethod
    def _algi_mesafe_hesapla(mesaj: LaserScan):
        """kat_tespit.py'deki scan_geldi ile BIREBIR AYNI mantik (bkz.
        modul docstring'i, ALGI MESAFESI -- BILINEN SINIR)."""
        n = len(mesaj.ranges)
        yariyay = int(math.radians(60) / mesaj.angle_increment)
        gecerli = []
        for i in range(-yariyay, yariyay + 1):
            d = mesaj.ranges[i % n]
            if (not math.isinf(d) and not math.isnan(d)
                    and mesaj.range_min < d < mesaj.range_max):
                gecerli.append(d)
        return min(gecerli) if gecerli else None

    @staticmethod
    def _oracle_mesafe_hesapla(robot_y: float, raf_y: float, yon: str) -> float:
        """Saf fonksiyon: robotun BILINEN (teleport ile set edilmis)
        dunya-cercevesi y'si ile rafin on yuzu arasindaki geometrik
        mesafe -- olcum degil, hesap. Raflar sadece kuzey/guney bakiyor
        (bkz. CLAUDE.md "Row C shelves face north, rows A/B face south"),
        yani fark sadece y ekseninde.
        """
        if yon == 'guney':
            on_yuz_y = raf_y - RAF_YARI_DERINLIK
            return on_yuz_y - robot_y
        on_yuz_y = raf_y + RAF_YARI_DERINLIK
        return robot_y - on_yuz_y

    @staticmethod
    def _standoff_pozu_hesapla(raf_x: float, raf_y: float, yon: str):
        """Standart tarama duruşuna (RAF_YARI_DERINLIK+KORIDOR_PAYI) gore
        DUNYA-cercevesi (x,y,yaw) hedefi -- tarama_pozisyonu_hesapla.py
        ile AYNI sabitler, ama WORLD frame'de (bu script Nav2 KULLANMIYOR,
        bkz. modul docstring'i)."""
        geri_cekme = RAF_YARI_DERINLIK + KORIDOR_PAYI
        if yon == 'guney':
            return raf_x, raf_y - geri_cekme, math.pi / 2
        return raf_x, raf_y + geri_cekme, -math.pi / 2

    def _teleport_et(self, x: float, y: float, yaw: float) -> None:
        # ros_gz_bridge'in /world/default/set_pose servis koprusu bozuk
        # (bkz. NOTLAR.md/PROJE_DOSYASI.md, Sprint 2E'de bulunan bir
        # onceki sorun) -- gz service CLI'si dogrudan kullaniliyor,
        # ayni Sprint 2E'de dogrulanan yontem.
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

    def _algi_mesafe_olc(self, ornek_sayisi: int = 5, zaman_asimi: float = 5.0):
        """LIDAR'in yerlesmesi icin birkac okuma toplar, ortalamasini doner."""
        self._son_scan = None
        olcumler = []
        baslangic = time.monotonic()
        while len(olcumler) < ornek_sayisi and time.monotonic() - baslangic < zaman_asimi:
            rclpy.spin_once(self, timeout_sec=0.2)
            if self._son_scan is not None:
                d = self._algi_mesafe_hesapla(self._son_scan)
                if d is not None:
                    olcumler.append(d)
                self._son_scan = None
        if not olcumler:
            return None
        return sum(olcumler) / len(olcumler)

    def calistir(self) -> dict:
        sonuclar = {}
        self.get_logger().info(f'{len(self.raflar)} raf taranacak...')
        for raf in self.raflar:
            bilgi = self.envanter.get('raf_konumlari', {}).get(raf)
            if bilgi is None:
                self.get_logger().warn(f"'{raf}' envanter.json raf_konumlari'nda yok, atlandi.")
                continue
            raf_x, raf_y, yon = bilgi['x'], bilgi['y'], bilgi['yon']

            x, y, yaw = self._standoff_pozu_hesapla(raf_x, raf_y, yon)
            self._teleport_et(x, y, yaw)
            time.sleep(1.0)  # fizigin/LIDAR'in yerlesmesi icin kisa bekleme

            oracle = self._oracle_mesafe_hesapla(y, raf_y, yon)
            algi = self._algi_mesafe_olc()

            if algi is None:
                self.get_logger().warn(f"'{raf}': algi mesafesi olculemedi (LIDAR verisi yok).")
                sonuclar[raf] = {
                    'oracle_m': round(oracle, 3), 'algi_m': None,
                    'fark_m': None, 'fark_yuzde': None,
                }
                continue

            fark = algi - oracle
            fark_yuzde = (fark / oracle) * 100 if oracle else None
            sonuclar[raf] = {
                'oracle_m': round(oracle, 3),
                'algi_m': round(algi, 3),
                'fark_m': round(fark, 3),
                'fark_yuzde': round(fark_yuzde, 1) if fark_yuzde is not None else None,
            }
            self.get_logger().info(
                f"'{raf}': oracle={oracle:.3f} m, algi={algi:.3f} m, "
                f"fark={fark:+.3f} m ({fark_yuzde:+.1f}%)")

        return sonuclar

    def sonuclari_kaydet(self, sonuclar: dict) -> None:
        yol = Path(get_package_share_directory('depo_robotu')) / 'araclar' / 'oracle_algi_karsilastirma.json'
        with open(yol, 'w', encoding='utf-8') as f:
            json.dump({
                'metodoloji': (
                    "Nav2 KULLANILMADI -- robot her raf icin 'gz service set_pose' ile "
                    'dogrudan WORLD-frame standart tarama pozuna teleport edildi '
                    '(RAF_YARI_DERINLIK=0.4 + KORIDOR_PAYI=1.6). Oracle mesafe: bu '
                    'bilinen pozdan rafin on yuzune GEOMETRIK hesap (olcum degil). '
                    'Algi mesafe: /scan on +-60 derece TEK NOKTA minimum (5 okumanin '
                    'ortalamasi) -- cizgi uydurma (line fitting) DEGIL, kutu_tespit.py '
                    "ve kardes node'lerin kullandigi ayni x=mesafe duzlem varsayiminin "
                    '(bkz. PROJE_DOSYASI.md SS12) bagimsiz bir kopyasi.'
                ),
                'sonuclar': sonuclar,
            }, f, ensure_ascii=False, indent=2)
        self.get_logger().info(f'Sonuclar kaydedildi: {yol}')


def main(args=None):
    rclpy.init(args=args)
    dugum = OracleAlgiKarsilastirma()
    try:
        sonuclar = dugum.calistir()
        dugum.sonuclari_kaydet(sonuclar)
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
