#!/usr/bin/env python3
"""
Sprint 5 madde 1 - llm_servis (FastAPI) ile ROS 2 arasindaki kopru.

KARAR (PROJE_DOSYASI.md Sprint 4 "KARAR VERILDI"): llm_servis ROS 2'den
bagimsiz kalmaya devam ediyor; koprunun yonu ROS 2 -> FastAPI. Bu node
/komut topicinden dogal dil metnini alir, http://localhost:8000/komut
adresine HTTP POST atar, donen sorguyu (sadece tip:adres) tarama_pozisyonlari.json
ile (x, y, yaw) hedefine cevirip Nav2'ye NavigateToPose action'i olarak
gonderir. Navigasyon basariyla tamamlandiginda tarama_kontrol.py'nin
sagladigi Look-and-Move akisi (3 kati sirayla tara, kutulari tespit et)
bir SUBPROCESS olarak tetiklenir - tip:arama / tip:sayim sonuclari
(navigasyon gerektirmiyor) sadece loglanir.

tarama_kontrol.py NEDEN SUBPROCESS: kendisi 'raf' adini yalnizca kendi
ROS parametresinden okuyan, constructor'da baslayip bitince kendini
KAPATMAYAN bagimsiz bir node (bkz. dosyanin kendi docstring'i). Farkli
bir rafi taramasi icin yeniden baslatilmasi gerekiyor - dinamik "simdi
X'i tara" tetiklemesi yok. Bu yuzden onu her navigasyon basarisinda
`ros2 run depo_robotu tarama_kontrol -p raf:=<raf>` ile YENIDEN
baslatiyoruz, /tarama_raporu mesaji gelince sonlandiriyoruz.
tarama_kontrol.py'nin kendisinde HICBIR degisiklik yapilmadi.

llm_servis kendi pip ortaminda calisan ayri bir surec oldugu icin
buradaki JSON ayrisimi pydantic semasini (sorgu_semasi.py) DEGIL, duz
dict.get() kullanir - iki surec birbirinin Python bagimliliklarini
paylasmaz.

BILINCLI SINIRLAR:
- /komut geldiginde HTTP istegi bu callback icinde BLOKLAYICI olarak
  yapiliyor (requests.post). LLM cevabi birkac saniye surebiliyor, bu
  sure boyunca dugum baska /komut mesaji islemez. Tekli interaktif
  kullanim (bir komut - bir sonuc) icin yeterli, coklu-istemci
  senaryosu icin executor/thread onerilir (henuz yapilmadi).
- tarama_kontrol subprocess'i icin bir zaman asimi/saglik kontrolu yok -
  surec cokerse veya /tarama_raporu hic gelmezse dugum sonsuza dek
  "tarama devam ediyor" sanip yeni istekleri reddeder (bkz.
  _tarama_baslat). Manuel mudahale (dugumu yeniden baslatmak) gerekir.

BELIRSIZLIK TAKIBI (Madde 5): llm_servis bir arama/sayim sorgusunu
birden fazla kutuyla eslestirirse (belirsiz:true) donen eslesmeler
listesi burada self._son_belirsiz_eslesmeler'de saklanir. Bir sonraki
/komut mesaji "ilkini/ikincisini/sonuncusunu sec" gibi bir SIRA ifadesi
ICERIYORSA, llm_servis'e HIC gidilmeden (bkz. asagidaki tasarim karari)
saklanan listeden ilgili kutu secilip navigasyona baslanir.

TASARIM KARARI (secim tanima neden regex, LLM degil): bu ifadeler kapali
bir kume (sirali sayilar + "ilk"/"son"), gercek bir dogal dil belirsizligi
tasimiyor. LLM'e gitmek hem gecikme (1-3s) hem API bagimliligi ekler --
ozellikle "dur"/"iptal" gibi ANINDA calismasi gereken komutlarla (Madde 6)
ayni ailede oldugu icin bu tutarlilik tercih edildi (kullanicinin onayiyla).
"""

import json
import re
import subprocess
from pathlib import Path

import requests
import rclpy
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


class NavigasyonKoprusu(Node):

    LLM_SERVIS_URL = 'http://localhost:8000/komut'
    HTTP_ZAMAN_ASIMI = 30.0  # s - Gemini cevabi bazen birkac saniye surebiliyor

    # Madde 5: sira ifadesi -> saklanan eslesmeler listesindeki indeks.
    # -1 = sonuncusu (listenin sonundan sayilir, bkz. _secim_indeksini_coz).
    SIRA_KELIMELERI = {
        'ilkini': 0, 'ilki': 0, 'birincisini': 0, 'birinciyi': 0, 'birini': 0,
        'ikincisini': 1, 'ikinciyi': 1,
        'ucuncusunu': 2, 'üçüncüsünü': 2, 'ucuncuyu': 2, 'üçüncüyü': 2,
        'dorduncusunu': 3, 'dördüncüsünü': 3, 'dorduncuyu': 3, 'dördüncüyü': 3,
        'besincisini': 4, 'beşincisini': 4, 'besinciyi': 4, 'beşinciyi': 4,
        'altincisini': 5, 'altıncısını': 5, 'altinciyi': 5, 'altıncıyı': 5,
        'yedincisini': 6, 'yedinciyi': 6,
        'sekizincisini': 7, 'sekizinciyi': 7,
        'dokuzuncusunu': 8, 'dokuzuncuyu': 8,
        'onuncusunu': 9, 'onuncuyu': 9,
        'sonuncusunu': -1, 'sonuncuyu': -1, 'sonunu': -1, 'sonu': -1,
    }

    def __init__(self):
        super().__init__('navigasyon_koprusu')

        self.tarama_pozisyonlari = self._tarama_pozisyonlari_yukle()
        self._son_hedef_raf = None
        self._son_hedef_kat = None
        # Madde 1: navigasyon basarili olunca tarama tetiklenip
        # tetiklenmeyecegine bu iki alan karar veriyor.
        self._son_hedef_eylem = None
        self._son_hedef_katlar = None
        self._tarama_proc = None
        self._beklenen_tarama_raf = None
        # Madde 5: llm_servis'in belirsiz:true donerken verdigi eslesme
        # listesi, bir sonraki "ilkini/ikincisini... sec" komutu icin.
        self._son_belirsiz_eslesmeler = None

        self.komut_abone = self.create_subscription(
            String, '/komut', self._komut_geldi, 10)

        self.create_subscription(String, '/tarama_raporu', self._tarama_raporu_geldi, 10)

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

        # Madde 5: bekleyen bir belirsizlik varsa ve bu komut bir sira
        # ifadesiyse, llm_servis'e HIC gitmeden burada cozulur.
        if self._son_belirsiz_eslesmeler is not None:
            indeks = self._secim_indeksini_coz(metin)
            if indeks is not None:
                self._secimi_uygula(indeks)
                return

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
            self._son_belirsiz_eslesmeler = sonuc.get('eslesmeler')
            self.get_logger().info(
                f"Sorgu belirsiz: {sonuc.get('eslesme_sayisi')} eslesme bulundu, "
                "navigasyon baslatilmadi. \"ilkini/ikincisini/sonuncusunu sec\" "
                "gibi bir komutla secim yapilabilir.")
            return

        sorgu = sonuc.get('sorgu') or {}
        if sorgu.get('tip') != 'adres':
            self.get_logger().info(
                f"'{sorgu.get('tip')}' tipi navigasyon gerektirmiyor, sonuc: {sonuc}")
            return

        raf = sorgu.get('raf')
        kat = sorgu.get('kat')
        eylem = sorgu.get('eylem')
        katlar = sorgu.get('katlar')
        if raf not in self.tarama_pozisyonlari:
            self.get_logger().error(f"'{raf}' tarama_pozisyonlari.json'da yok.")
            return

        self.get_logger().info(
            f"Hedef: raf={raf}, kat={kat}, eylem={eylem}, katlar={katlar} "
            "-> Nav2'ye gonderiliyor.")
        self._son_hedef_raf = raf
        self._son_hedef_kat = kat
        self._son_hedef_eylem = eylem
        self._son_hedef_katlar = katlar
        self._hedefe_git(self.tarama_pozisyonlari[raf])

    def _secim_indeksini_coz(self, metin: str):
        """Madde 5: "ilkini sec", "2. yi sec" gibi bir sira ifadesini
        self._son_belirsiz_eslesmeler icindeki 0-tabanli indekse cevirir.

        Yanlis pozitifi azaltmak icin metinde "sec" koku ARANMASI SART --
        yoksa "A2'nin 2. katini tara" gibi normal bir komuttaki "2." de
        yanlislikla secim sanilabilirdi.
        """
        m = metin.lower()
        if 'seç' not in m and 'sec' not in m:
            return None
        # \b sinir kontrolu SART -- yoksa "sonuncusunu" gibi bir kelime,
        # icinde substring olarak barindirdigi "onuncusunu" (10.) ile
        # yanlislikla eslesebilir.
        for kelime, indeks in self.SIRA_KELIMELERI.items():
            if re.search(r'\b' + re.escape(kelime) + r'\b', m):
                return indeks
        rakam = re.search(r'\b(\d+)\b', m)
        if rakam:
            return int(rakam.group(1)) - 1
        return None

    def _secimi_uygula(self, indeks: int) -> None:
        eslesmeler = self._son_belirsiz_eslesmeler
        self._son_belirsiz_eslesmeler = None

        gercek_indeks = indeks if indeks >= 0 else len(eslesmeler) + indeks
        if not eslesmeler or not (0 <= gercek_indeks < len(eslesmeler)):
            self.get_logger().warn(
                f"Secim indeksi gecersiz ({indeks}), {len(eslesmeler or [])} "
                'eslesme vardi. Belirsizlik iptal edildi, yeniden arayin.')
            return

        secilen = eslesmeler[gercek_indeks]
        raf = secilen.get('raf')
        if raf not in self.tarama_pozisyonlari:
            self.get_logger().error(
                f"Secilen kutunun rafi '{raf}' tarama_pozisyonlari.json'da yok.")
            return

        self.get_logger().info(
            f"Secim: #{gercek_indeks + 1} -> {secilen.get('renk')} "
            f"{secilen.get('boyut')} kutu, raf={raf}, kat={secilen.get('kat')}. "
            "Navigasyon baslatiliyor (eylem=git, tarama yok).")
        # Madde 5: secim SADECE o kutuya goturur, tarama yapmaz -- kutunun
        # zaten hangi rafta/katta oldugu biliniyor (ground truth aramasindan
        # geldi), tekrar taramaya gerek yok. Bkz. Madde 1 eylem semantigi.
        self._son_hedef_raf = raf
        self._son_hedef_kat = secilen.get('kat')
        self._son_hedef_eylem = 'git'
        self._son_hedef_katlar = None
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

        # Madde 1: eylem=='git' ise SADECE navigasyon isteniyor demektir --
        # kamera donmez, tarama tetiklenmez. Sadece eylem=='tara' tarama
        # baslatir.
        if basarili and self._son_hedef_raf is not None and self._son_hedef_eylem == 'tara':
            self._tarama_baslat(self._son_hedef_raf, self._son_hedef_katlar)
        elif basarili and self._son_hedef_eylem == 'git':
            self.get_logger().info("eylem='git' -- tarama tetiklenmedi.")

    def _tarama_baslat(self, raf: str, katlar: list = None) -> None:
        if self._tarama_proc is not None and self._tarama_proc.poll() is None:
            self.get_logger().warn(
                f"'{self._beklenen_tarama_raf}' icin tarama zaten devam ediyor, "
                f"'{raf}' istegi yoksayildi.")
            return

        self.get_logger().info(f"'{raf}' icin Look-and-Move taramasi baslatiliyor...")
        self._beklenen_tarama_raf = raf
        komut = [
            'ros2', 'run', 'depo_robotu', 'tarama_kontrol',
            '--ros-args', '-p', f'raf:={raf}',
        ]
        if katlar:
            komut += ['-p', f"katlar:={','.join(str(k) for k in katlar)}"]
        self._tarama_proc = subprocess.Popen(komut)

    def _tarama_raporu_geldi(self, mesaj: String) -> None:
        if self._tarama_proc is None:
            return

        try:
            rapor = json.loads(mesaj.data)
        except json.JSONDecodeError:
            self.get_logger().error('/tarama_raporu JSON olarak ayrıştırılamadı.')
            return

        if rapor.get('raf') != self._beklenen_tarama_raf:
            return

        self.get_logger().info(
            f"'{rapor.get('raf')}' taramasi tamamlandi: "
            f"{rapor.get('eslesen')}/{rapor.get('envanter_toplam')} eslesme "
            f"(dogruluk %{rapor.get('dogruluk', 0) * 100:.1f}).")

        self._tarama_proc.terminate()
        self._tarama_proc = None
        self._beklenen_tarama_raf = None


def main(args=None):
    rclpy.init(args=args)
    dugum = NavigasyonKoprusu()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    if dugum._tarama_proc is not None and dugum._tarama_proc.poll() is None:
        dugum._tarama_proc.terminate()
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
