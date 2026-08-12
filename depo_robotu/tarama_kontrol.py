#!/usr/bin/env python3
"""
Look-and-Move durum makinesi - Sprint 2E.

Robot rafin onunde sabit durur; bu node kamera_kontrol'u (hedef kat
acisi icin) ve kutu_tespit'i (o kattaki kutular icin) sirayla orkestre
eder. Kendisi ne kamerayi dondurur ne de goruntu isler - sadece var
olan node'lari /hedef_kat, /bakilan_kat, /tespitler topicleri
uzerinden yonetir.

Akis (her kat icin): hedef_kat yayinla -> bakilan_kat'in o kata
kilitlenmesini bekle (N ardisik tutarli okuma) -> kamera/goruntu
oturmasi icin kisa bir yerlesme suresi -> tespitler'i bir pencere
boyunca topla ve pikselde yakin olanlari tekillestir. Uc kat bitince
sonuclari envanter.json'daki ilgili raf ile karsilastirip dogruluk
raporu yayinlar/loglar.
"""

import json

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import Int32, String


class TaramaKontrol(Node):

    KATLAR = [1, 2, 3]
    KILIT_ESIGI = 5          # bakilan_kat'in ust uste kac kez hedefle eslesmesi gerekiyor
    YERLESME_SURESI = 1.5    # s - kilitten sonra goruntunun otursun diye beklenen sure
    TOPLAMA_SURESI = 2.5     # s - tespitler'i dinleme penceresi
    PIKSEL_ESIGI = 40        # px - ayni kutunun tekrarli tespitlerini birlestirmek icin

    def __init__(self):
        super().__init__('tarama_kontrol')

        self.declare_parameter('raf', 'B2')
        self.raf_adi = self.get_parameter('raf').value

        self.envanter = self._envanter_yukle()

        self.hedef_yayinci = self.create_publisher(Int32, '/hedef_kat', 10)
        self.rapor_yayinci = self.create_publisher(String, '/tarama_raporu', 10)

        self.create_subscription(Int32, '/bakilan_kat', self._bakilan_kat_geldi, 10)
        self.create_subscription(String, '/tespitler', self._tespit_geldi, 10)

        self.kat_indeksi = 0
        self.durum = 'KAT_ISTE'
        self.kilit_sayaci = 0
        self.tum_tespitler = {}  # kat -> [tespit, ...] (tekillestirilmis)
        self._kat_tespitleri = []
        self._durum_baslangic = self._simdi()

        self.zamanlayici = self.create_timer(0.2, self._adim)

        self.get_logger().info(
            f"Tarama kontrol hazir. Raf '{self.raf_adi}' icin kat 1/2/3 taranacak.")

    def _envanter_yukle(self):
        yol = get_package_share_directory('depo_robotu') + '/araclar/envanter.json'
        try:
            with open(yol, 'r', encoding='utf-8') as f:
                return json.load(f)
        except OSError as e:
            self.get_logger().warn(f'envanter.json okunamadi ({e}), dogruluk hesabi atlanacak.')
            return None

    def _simdi(self):
        return self.get_clock().now().nanoseconds / 1e9

    def _gecen_sure(self):
        return self._simdi() - self._durum_baslangic

    def _durum_degistir(self, yeni_durum):
        self.durum = yeni_durum
        self._durum_baslangic = self._simdi()

    def _bakilan_kat_geldi(self, mesaj):
        if self.durum != 'KILIT_BEKLE':
            return
        hedef = self.KATLAR[self.kat_indeksi]
        if mesaj.data == hedef:
            self.kilit_sayaci += 1
        else:
            self.kilit_sayaci = 0

    def _tespit_geldi(self, mesaj):
        if self.durum != 'TESPIT_TOPLA':
            return
        try:
            gelen = json.loads(mesaj.data)
        except json.JSONDecodeError:
            return
        self._kat_tespitleri.extend(gelen)

    def _tekillestir(self, tespitler):
        tekil = []
        for t in tespitler:
            u, v = t['piksel']
            eslesme = None
            for mevcut in tekil:
                mu, mv = mevcut['piksel']
                if abs(mu - u) < self.PIKSEL_ESIGI and abs(mv - v) < self.PIKSEL_ESIGI \
                        and mevcut['renk'] == t['renk']:
                    eslesme = mevcut
                    break
            if eslesme is None:
                tekil.append(t)
        return tekil

    def _adim(self):
        if self.durum == 'KAT_ISTE':
            hedef = self.KATLAR[self.kat_indeksi]
            self.hedef_yayinci.publish(Int32(data=hedef))
            self.get_logger().info(f'Kat {hedef} isteniyor...')
            self.kilit_sayaci = 0
            self._durum_degistir('KILIT_BEKLE')

        elif self.durum == 'KILIT_BEKLE':
            if self.kilit_sayaci >= self.KILIT_ESIGI:
                hedef = self.KATLAR[self.kat_indeksi]
                self.get_logger().info(f'Kat {hedef} kilitlendi, yerlesme bekleniyor.')
                self._durum_degistir('YERLES')
            elif self._gecen_sure() > 10.0:
                self.get_logger().warn(
                    f'Kat {self.KATLAR[self.kat_indeksi]} icin kilit zaman asimi, devam ediliyor.')
                self._durum_degistir('YERLES')

        elif self.durum == 'YERLES':
            if self._gecen_sure() > self.YERLESME_SURESI:
                self._kat_tespitleri = []
                self._durum_degistir('TESPIT_TOPLA')

        elif self.durum == 'TESPIT_TOPLA':
            if self._gecen_sure() > self.TOPLAMA_SURESI:
                kat = self.KATLAR[self.kat_indeksi]
                tekil = self._tekillestir(self._kat_tespitleri)
                self.tum_tespitler[kat] = tekil
                self.get_logger().info(f'Kat {kat}: {len(tekil)} kutu tespit edildi.')

                self.kat_indeksi += 1
                if self.kat_indeksi < len(self.KATLAR):
                    self._durum_degistir('KAT_ISTE')
                else:
                    self._durum_degistir('RAPOR')

        elif self.durum == 'RAPOR':
            self._rapor_olustur()
            self._durum_degistir('BITTI')

        elif self.durum == 'BITTI':
            pass

    def _rapor_olustur(self):
        rapor = {'raf': self.raf_adi, 'tespitler': self.tum_tespitler}

        if self.envanter is not None:
            gt_kutular = [k for k in self.envanter['kutular'] if k['raf'] == self.raf_adi]
            eslesen = 0
            fazla = 0
            for kat in self.KATLAR:
                gt_kat = [k for k in gt_kutular if k['kat'] == kat]
                tespit_kat = list(self.tum_tespitler.get(kat, []))
                for gt in gt_kat:
                    for i, t in enumerate(tespit_kat):
                        if t['renk'] == gt['renk']:
                            eslesen += 1
                            del tespit_kat[i]
                            break
                fazla += len(tespit_kat)  # eslesmeyen tespitler - muhtemelen komsu raf/direk
            toplam = len(gt_kutular)
            oran = eslesen / toplam if toplam else 0.0
            rapor['envanter_toplam'] = toplam
            rapor['eslesen'] = eslesen
            rapor['fazla_tespit'] = fazla
            rapor['dogruluk'] = round(oran, 3)
            self.get_logger().info(
                f"'{self.raf_adi}' raporu: {eslesen}/{toplam} eslesme "
                f'(dogruluk %{oran * 100:.1f})')
            if fazla > 0:
                self.get_logger().warn(
                    f'{fazla} tespit envanterle eslesmedi (renk bazli eslesme, raf/konum '
                    f'ayrimi yok - muhtemelen komsu raf FOV icine giriyor, bkz. NOTLAR.md).')
        else:
            self.get_logger().info(f"'{self.raf_adi}' raporu (envanter karsilastirmasi yok).")

        mesaj = String()
        mesaj.data = json.dumps(rapor, ensure_ascii=False)
        self.rapor_yayinci.publish(mesaj)
        self.get_logger().info(f'Rapor /tarama_raporu uzerinde yayinlandi.')


def main(args=None):
    rclpy.init(args=args)
    dugum = TaramaKontrol()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
