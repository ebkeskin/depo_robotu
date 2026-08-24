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

EN YAKINI BUL (Madde 3): sorgu.en_yakin=true ve birden fazla eslesme
varsa, robotun SU ANKI map-frame pozu TF'den (map -> base_footprint)
okunur ve her eslesmeye en_yakin_eslesmeyi_sec ile mesafe hesaplanir.

MIMARI KARAR (mesafe neye gore hesaplanir): eslesmenin KENDI konumuna
(envanter.json'daki dunya/world-frame 'konum') DEGIL, eslesmenin
RAFININ tarama_pozisyonlari.json'daki (Nav2/AMCL icin zaten olculmus,
map-frame) pozuna gore hesaplanir. Sebep: envanter.json world-frame,
TF ise map-frame donuyor -- bu ikisi ayni sayilirsa PROJE_DOSYASI.md
SS12 KOK SEBEP'te iki kez yasanan world/map karisikligi hatasi
tekrarlanir. Raf ici sapma (kat/yanal_konum, <=1.4m) raflar-arasi
mesafenin (metrelerce) yaninda ihmal edilebilir, bu yuzden bu yaklasim
yeterince dogru VE guvenli.

IPTAL/DUR (Madde 6): "dur"/"iptal" gibi bir ifade, Madde 5'teki secim
komutlariyla AYNI SEBEPLE (kapali kume, gecikme kabul edilemez) regex
ile llm_servis'e HIC gidilmeden taninir -- _komut_geldi'nin EN BASINDA
kontrol edilir (secim/en_yakin/adres akislarinin hepsinden once), boylece
bekleyen bir belirsizlik/secim de temizlenmis olur. Hangi surecin iptal
edilecegine karar veren mantik (_iptal_eylemini_belirle) TF/subprocess/
action-client gibi gercek ROS nesnelerinden bagimsiz SAF bir fonksiyon --
gercek iptali yapan _iptali_uygula'dan ayrildi (bkz. Madde 3'teki
_en_yakin_eslesmeyi_sec/_en_yakina_git ayrimiyla ayni desen), ROS'suz
izole test edilebilsin diye.

PASIF ENVANTER MVP (Madde 4, PROJE_DOSYASI.md 1.3 "ozgun fikir (a)"nin
ilk adimi): her tarama_raporu, GERCEKTEN gorulen (envanter.json ground
truth'undan DEGIL, kutu_tespit.py'nin canli tespitlerinden gelen, zaten
raf-kapsamlamasi ve pencereler-arasi tekillestirme uygulanmis) tespitleri
robot_envanteri.json'a raf basina kaydeder -- bir raf tekrar taranirsa
o rafin girdisi YENISIYLE DEGISTIRILIR (ekleme/biriktirme degil), boylece
tekrarlayan taramalarda sinirsiz kopya birikmesi veya YANAL_ESIGI gibi
yeni bir bulaniklik-esigi riski yok. "Ne ogrendin" sorusu (regex, Madde
5/6 ile ayni desen) bu dosyayi ozetleyip raporlar.

MVP KAPSAM SINIRI (bilincli, kullanicinin onayiyla): bu SADECE acikca
tara edilen raflardan ogrenir -- robot "git" ile bir yerden GECERKEN
gordugu kutulari KAYDETMEZ (idea (a)'nin tam hali bunu da yapardi, ama
bu, kutu_tespit.py'nin ham /tespitler'ine surekli abone olup TF ile
dunya-cercevesi konum hesaplamayi gerektirir -- "en yakini bul"daki gibi
yeni bir world/map donusumu riski tasiyan, ayri ve buyuk bir is). Ground
truth aramasindan (tip:arama, envanter.json'a karsi) da KASITLI olarak
AYRI: biri "biliniyor" der, digeri "gordum" der, karistirilmamali.

ENVANTERDEN SORGU (PROJE_DOSYASI.md Sprint 5 RESMI roadmap'inin 3.
maddesi -- NOT: yukaridaki "Madde 3/4/5/6" etiketleri 24 Agustos 2026'da
eklenen AYRI, ek bir ozellik katmanina ait, bu ikisini karistirma):
yukaridaki "ne ogrendin" ailesi (_kendi_envanteri_ifadesi_mi) genisletildi
-- ayni ifadede bir renk/boyut da geciyorsa ("gordugun kirmizi kutu
nerede", "kendi envanterinde mavi var mi") robot_envanteri.json'a karsi
FILTRELI bir arama yapilir (_kendi_envanterini_isle). Filtre yoksa
("duz ne ogrendin") eskisi gibi tam ozet raporlanir -- davranista
GERIYE DONUK degisiklik YOK, sadece dallanma noktasi genisledi.

Renk/boyut cikarimi (_renk_boyut_ayikla) de kapali kume (5 renk x 3 boyut)
oldugu icin AYNI regex-yerel-tanima tercihiyle (LLM'e gitmeden) yapiliyor.
Coklu eslesme durumunda Madde 5'in _son_belirsiz_eslesmeler/"ilkini sec"
altyapisi AYNEN yeniden kullaniliyor -- _robot_envanterinde_ara'nin donduğu
liste zaten uyumlu 'raf'/'kat' anahtarlari tasiyor, ekstra kod gerekmedi.
Ground-truth tip:arama ile PARİTE: tek eslesmede bile navigasyon
BASLATILMAZ, sadece raporlanir (mevcut tip:arama davranisiyla tutarli).

HEDEFE VARINCA GORSEL DOGRULAMA (PROJE_DOSYASI.md Sprint 5 RESMI
roadmap'inin 4. maddesi): _secimi_uygula (Madde 5 -- hem ground-truth
hem kendi-envanteri kaynakli secimler icin ortak) ve _en_yakina_git
("en yakini bul") navigasyona baslamadan once bilinen renk/boyut/kat
bilgisini self._son_dogrulama_beklentisi'ne yazar. Navigasyon basariyla
bitince (_navigasyon_tamamlandi, eylem=='git' dalinda) bu alan doluysa,
_tarama_baslat TEK KATLIK bir cagriyla (katlar=[beklenen_kat]) yeniden
kullanilir -- tarama_kontrol.py'nin kilit/yerlesme/toplama state
makinesi ve raf-kapsamlama filtresi HICBIR degisiklik olmadan aynen
calisir, sifirdan bir orkestrasyon yazilmadi. Duz "X'e git" (LLM'in
tip:adres sorgusu) HER ZAMAN bu alani None'a sifirlar -- dogrulanacak
belirli bir kutu yoktur, tarama hic tetiklenmez (mevcut davranis).

TASARIM KARARI (dogrulama SADECE RENGE bakar, boyuta degil): bu
projede boyut siniflandirmasinin bilinen, belgelenen bir kozmetik
guvenilirlik sorunu var (bkz. PROJE_DOSYASI.md SS12 ACIK MADDE 1
guncellemesi -- "boyut 'kucuk' yanlis siniflandiriliyor, renk
eslesmesini etkilemiyor"). Boyutu "uyusmuyor" kararina dahil etmek,
sirf gurultulu bir boyut tahmini yuzunden dogru olan bir renk
eslesmesini yanlislikla "uyusmuyor" saydirma riski tasirdi. Boyut yine
de log mesajinda bilgi amacli gosterilir.

Doğrulama tarama_raporu'nu da (normal tara gibi) robot_envanteri.json'a
yazar (_robot_envanterini_guncelle, asagidaki BUG DUZELTMESI sayesinde
artik guvenli -- diger katlarin verisini SILMEZ).

BUG DUZELTMESI (24 Agustos 2026, dogrulama ozelligini tasarlarken
bulundu): _robot_envanterini_guncelle eskiden rafin TUM girdisini yeni
raporla DEGISTIRIYORDU. Bu, TEK KATLIK bir tarama (Madde 1'in kismi
"1. katini tara" komutu VEYA bu maddenin dogrulama taramasi) geldiginde,
o rafin ONCEDEN BILINEN diger katlarinin verisini SILIYORDU -- Madde 4
ilk yazildiginda fark edilmemis, bagimsiz bir hata. Duzeltme: rapor'un
'taranan_katlar' alani (Madde 1'de zaten var) kullanilarak sadece o
katlar GUNCELLENIR, diger katlar DOKUNULMADAN kalir.
"""

import datetime
import json
import math
import re
import signal
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
from tf2_ros import Buffer, TransformListener


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

    # Envanterden sorgu: sorgu_semasi.py'deki Renk/Boyut enum'larinin
    # AYNISI -- llm_servis ayri bir Python ortaminda oldugu icin import
    # edilemiyor, RAF_UZUNLUK gibi (bkz. tarama_kontrol.py) bilerek
    # kopyalandi. Deger: metinde gecebilecek kelime -> canonik JSON degeri.
    RENK_KELIMELERI = {
        'kirmizi': 'kirmizi', 'kırmızı': 'kirmizi',
        'yesil': 'yesil', 'yeşil': 'yesil',
        'mavi': 'mavi',
        'sari': 'sari', 'sarı': 'sari',
        'karton': 'karton',
    }
    BOYUT_KELIMELERI = {
        'buyuk': 'buyuk', 'büyük': 'buyuk',
        'orta': 'orta',
        'kucuk': 'kucuk', 'küçük': 'kucuk',
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
        # Madde 6: devam eden navigasyonun goal_handle'i -- iptal icin
        # cancel_goal_async() burada cagirilir. None = navigasyon yok.
        self._son_goal_handle = None
        # Gorsel dogrulama: {'renk','boyut','kat'} veya None. Sadece
        # secim/en_yakin akislarinda doldurulur -- duz "git" HER ZAMAN
        # None'a sifirlar (bkz. modul docstring'i).
        self._son_dogrulama_beklentisi = None

        # Madde 3: "en yakini bul" icin robotun su anki map-frame pozu.
        self._tf_buffer = Buffer()
        self._tf_dinleyici = TransformListener(self._tf_buffer, self)

        # Madde 4: pasif envanter MVP -- onceki oturumlardan kalan
        # robot_envanteri.json varsa yuklenir, yoksa bos baslar.
        self.robot_envanteri = self._robot_envanteri_yukle()

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

        # Madde 6: iptal her seyden once kontrol edilir -- llm_servis'e
        # gitmeden aninda calismali, bekleyen bir belirsizligi de temizler.
        if self._iptal_ifadesi_mi(metin):
            self._iptali_uygula()
            return

        # Madde 4 + Envanterden sorgu: "ne ogrendin" / "gordugun kirmizi
        # kutu nerede" gibi kendi-deneyim sorulari -- llm_servis'e
        # gitmeden, SADECE acikca tarama_kontrol calistirilmis raflardan
        # biriken robot_envanteri.json'a karsi (filtresiz -> tam ozet,
        # filtreli -> arama) cevap verir. Ground truth aramasindan
        # (tip:arama) KASITLI ayri (bkz. modul docstring'i).
        if self._kendi_envanteri_ifadesi_mi(metin):
            self._kendi_envanterini_isle(metin)
            return

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

        sorgu = sonuc.get('sorgu') or {}

        # Madde 3: "en yakini bul" -- belirsiz olsa da olmasa da (tek
        # eslesme icin de gecerli), eslesmeler arasindan robota en yakin
        # olani secip DOGRUDAN navigasyon baslatir. Bu yuzden genel
        # belirsizlik-bekletme akisindan ONCE kontrol ediliyor.
        if sorgu.get('en_yakin') and sonuc.get('eslesmeler'):
            self._en_yakina_git(sonuc.get('eslesmeler'))
            return

        if sonuc.get('belirsiz'):
            self._son_belirsiz_eslesmeler = sonuc.get('eslesmeler')
            self.get_logger().info(
                f"Sorgu belirsiz: {sonuc.get('eslesme_sayisi')} eslesme bulundu, "
                "navigasyon baslatilmadi. \"ilkini/ikincisini/sonuncusunu sec\" "
                "gibi bir komutla secim yapilabilir.")
            return

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
        # Gorsel dogrulama: duz adres sorgusunda dogrulanacak belirli bir
        # kutu yok -- onceki bir secimden kalma bir beklenti varsa SIZMASIN.
        self._son_dogrulama_beklentisi = None
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
        # Gorsel dogrulama: secilen kutunun renk/boyut/kat'i biliniyor --
        # hedefe varinca tek katlik bir dogrulama taramasi tetiklenecek.
        self._son_dogrulama_beklentisi = {
            'renk': secilen.get('renk'), 'boyut': secilen.get('boyut'),
            'kat': secilen.get('kat'),
        }
        self._hedefe_git(self.tarama_pozisyonlari[raf])

    @staticmethod
    def _en_yakin_eslesmeyi_sec(robot_x: float, robot_y: float,
                                 eslesmeler: list, tarama_pozisyonlari: dict):
        """Madde 3: TF/ROS'tan tamamen bagimsiz, saf fonksiyon -- ROS'suz
        izole birim testle dogrulanabilsin diye TF okumasindan ayrildi
        (bkz. _en_yakina_git). robot_x/robot_y map-frame'de, her
        eslesmenin mesafesi KENDI konumuna degil RAFININ tarama_pozisyonlari
        pozuna gore hesaplanir (bkz. modul docstring'i, MIMARI KARAR).

        Returns:
            (secilen_eslesme, mesafe_m) -- gecerli raf konumu bulunamazsa
            (None, None).
        """
        en_yakin = None
        en_yakin_mesafe = None
        for e in eslesmeler:
            poz = tarama_pozisyonlari.get(e.get('raf'))
            if poz is None:
                continue
            mesafe = math.hypot(poz['x'] - robot_x, poz['y'] - robot_y)
            if en_yakin_mesafe is None or mesafe < en_yakin_mesafe:
                en_yakin_mesafe = mesafe
                en_yakin = e
        return en_yakin, en_yakin_mesafe

    def _en_yakina_git(self, eslesmeler: list) -> None:
        try:
            donusum = self._tf_buffer.lookup_transform(
                'map', 'base_footprint', rclpy.time.Time())
        except Exception as e:
            self.get_logger().error(
                f"Robot konumu (map->base_footprint TF) okunamadi, "
                f"'en yakin' cozulemedi: {e}")
            return

        t = donusum.transform.translation
        secilen, mesafe = self._en_yakin_eslesmeyi_sec(
            t.x, t.y, eslesmeler, self.tarama_pozisyonlari)
        if secilen is None:
            self.get_logger().error(
                "'En yakin' icin gecerli raf konumu bulunamadi "
                "(eslesmelerin raflari tarama_pozisyonlari.json'da yok).")
            return

        raf = secilen.get('raf')
        self.get_logger().info(
            f"En yakin: {secilen.get('renk')} {secilen.get('boyut')} kutu, "
            f"raf={raf} (~{mesafe:.2f} m). Navigasyon baslatiliyor "
            "(eylem=git, tarama yok).")
        # Madde 3: secim gibi (Madde 5) SADECE o kutuya goturur, tarama
        # yapmaz -- kutunun rafi/kati zaten ground truth aramasindan
        # biliniyor.
        self._son_hedef_raf = raf
        self._son_hedef_kat = secilen.get('kat')
        self._son_hedef_eylem = 'git'
        self._son_hedef_katlar = None
        # Gorsel dogrulama: bkz. _secimi_uygula'daki ayni yorum.
        self._son_dogrulama_beklentisi = {
            'renk': secilen.get('renk'), 'boyut': secilen.get('boyut'),
            'kat': secilen.get('kat'),
        }
        self._hedefe_git(self.tarama_pozisyonlari[raf])

    @staticmethod
    def _iptal_ifadesi_mi(metin: str) -> bool:
        """Madde 6: saf, ROS'suz string kontrolu. \b sinir kontrolu
        SART -- yoksa "duracak", "durum" gibi kelimeler icindeki "dur"
        yanlislikla eslesir."""
        m = metin.lower()
        return bool(re.search(r'\b(dur|durdur|iptal)\b', m))

    @staticmethod
    def _iptal_eylemini_belirle(navigasyon_suruyor: bool, tarama_suruyor: bool) -> str:
        """Madde 6: hangi surecin iptal edilecegine karar veren SAF
        mantik -- gercek iptal islemini (cancel_goal_async/terminate)
        YAPMAZ, sadece 'ne yapilmali' karar verir (bkz. _iptali_uygula).
        ROS'suz izole test edilebilsin diye TF/subprocess/action-client
        durumundan (bool bayraklara indirgenmis olarak) ayrildi.

        Not: mevcut mimaride (bkz. _navigasyon_tamamlandi) tarama SADECE
        navigasyon basarıyla bittikten SONRA baslar, yani ikisi ayni anda
        surmez -- ama 'ikisi' durumu yine de savunmaci olarak ele alinir.
        """
        if navigasyon_suruyor and tarama_suruyor:
            return 'ikisi'
        if navigasyon_suruyor:
            return 'navigasyon'
        if tarama_suruyor:
            return 'tarama'
        return 'hicbiri'

    def _iptali_uygula(self) -> None:
        navigasyon_suruyor = self._son_goal_handle is not None
        tarama_suruyor = self._tarama_proc is not None and self._tarama_proc.poll() is None
        eylem = self._iptal_eylemini_belirle(navigasyon_suruyor, tarama_suruyor)

        # Iptal, bekleyen bir belirsizligi/secimi de gecersiz kilar.
        self._son_belirsiz_eslesmeler = None

        if eylem in ('navigasyon', 'ikisi'):
            self.get_logger().info('Iptal: devam eden navigasyon durduruluyor.')
            self._son_goal_handle.cancel_goal_async()
            self._son_goal_handle = None
        if eylem in ('tarama', 'ikisi'):
            self.get_logger().info(
                f"Iptal: '{self._beklenen_tarama_raf}' taramasi durduruluyor.")
            self._tarama_proc.terminate()
            self._tarama_proc = None
            self._beklenen_tarama_raf = None
        if eylem == 'hicbiri':
            self.get_logger().info(
                'Iptal komutu alindi ama devam eden bir navigasyon/tarama yok.')

    @staticmethod
    def _kendi_envanteri_ifadesi_mi(metin: str) -> bool:
        """Madde 4 + Envanterden sorgu: saf, ROS'suz string kontrolu.
        "ne ogrendin", "ogrendiklerini soyle", "gordugun kirmizi kutu
        nerede", "kendi envanterinde mavi var mi", "hafizanda ne var"
        gibi robotun KENDI deneyimini (ground truth degil) soran
        ifadeleri tanir. Eskiden _ogrendin_ifadesi_mi idi -- filtresiz
        "ne ogrendin" davranisi AYNEN korunuyor, sadece kapsam genisledi
        (bkz. modul docstring'i, "ENVANTERDEN SORGU")."""
        m = metin.lower()
        if 'öğren' in m or 'ogren' in m:
            return True
        if 'gördü' in m or 'gordu' in m:
            return True
        if 'hafıza' in m or 'hafiza' in m:
            return True
        return 'envanter' in m

    @staticmethod
    def _renk_boyut_ayikla(metin: str):
        """Envanterden sorgu: saf, ROS'suz -- metinde gecen bilinen bir
        renk ve/veya boyut kelimesini (varsa) canonik JSON degerine
        cevirir. Ikisi de bulunamazsa (None, None) doner -- cagiran taraf
        (_kendi_envanterini_isle) bu durumda filtresiz "ne ogrendin"
        akisina duser.

        BILINEN SINIR: renk/boyut kelimeleri sadece CEKIMSIZ (sifat
        halinde, orn. "kirmizi kutu") taniniyor -- bu zaten projedeki
        HAKIM kullanim kalibi (bkz. tum ornekler: "kirmizi kutuyu bul",
        "buyuk mavi kutu"). Kelimenin isim gibi cekimlendigi durumlar
        (orn. "kartondan olani") YAKALANMAZ -- tam Turkce morfolojisi
        cozmek bu MVP'nin kapsami disi, SIRA_KELIMELERI'ndeki gibi
        sadece dogal/sik gecen formlar elle listeleniyor.
        """
        m = metin.lower()
        renk = None
        for kelime, kanonik in NavigasyonKoprusu.RENK_KELIMELERI.items():
            if re.search(r'\b' + kelime + r'\b', m):
                renk = kanonik
                break
        boyut = None
        for kelime, kanonik in NavigasyonKoprusu.BOYUT_KELIMELERI.items():
            if re.search(r'\b' + kelime + r'\b', m):
                boyut = kanonik
                break
        return renk, boyut

    @staticmethod
    def _robot_envanterinde_ara(envanter: dict, renk: str = None, boyut: str = None) -> list:
        """Envanterden sorgu: robot_envanteri.json (dict) icinde renk/boyut
        filtresine uyan tespitleri, raf/kat bilgisiyle zenginlestirilmis
        DUZ bir liste olarak doner -- dosya/ROS erisiminden bagimsiz saf
        fonksiyon. Donen ogeler Madde 5'in _son_belirsiz_eslesmeler/
        _secimi_uygula altyapisiyla DOGRUDAN uyumlu (ayni 'raf'/'kat'
        anahtarlarini tasir) -- coklu eslesmede "ilkini sec" ek kod
        gerekmeden calisir.
        """
        sonuc = []
        for raf, veri in envanter.get('raflar', {}).items():
            for kat_str, tespitler in veri.get('tespitler', {}).items():
                for t in tespitler:
                    if renk is not None and t.get('renk') != renk:
                        continue
                    if boyut is not None and t.get('boyut') != boyut:
                        continue
                    sonuc.append({**t, 'raf': raf, 'kat': int(kat_str)})
        return sonuc

    def _kendi_envanterini_isle(self, metin: str) -> None:
        """Envanterden sorgu: _kendi_envanteri_ifadesi_mi tetiklendiginde
        cagrilir. Mesajda ayrica bir renk/boyut GECIYORSA filtrelenmis
        arama yapar; gecmiyorsa (duz "ne ogrendin") Madde 4'un tam ozetine
        duser -- davranista geriye donuk degisiklik yok.
        """
        renk, boyut = self._renk_boyut_ayikla(metin)
        if renk is None and boyut is None:
            self._ogrendiklerini_raporla()
            return

        if not self.robot_envanteri.get('raflar'):
            self.get_logger().info(
                'Kendi gorduklerim: Henuz hicbir raf taramadim, bu yuzden bilmiyorum.')
            return

        eslesmeler = self._robot_envanterinde_ara(self.robot_envanteri, renk, boyut)
        if not eslesmeler:
            nitelik = ' '.join(x for x in (renk, boyut) if x)
            self.get_logger().info(
                f'Kendi gorduklerim: taradigim raflarda {nitelik} bir kutu gormedim.')
            return

        if len(eslesmeler) == 1:
            e = eslesmeler[0]
            self.get_logger().info(
                f"Kendi gorduklerimde: {e.get('renk')} {e.get('boyut')} kutu, "
                f"raf={e.get('raf')}, kat={e.get('kat')}.")
            return

        # Coklu eslesme: Madde 5 ile AYNI belirsizlik-bekletme mekanizmasi
        # -- "ilkini/ikincisini/sonuncusunu sec" burada da calisir.
        self._son_belirsiz_eslesmeler = eslesmeler
        self.get_logger().info(
            f'Kendi gorduklerimde {len(eslesmeler)} eslesme var, navigasyon '
            'baslatilmadi. "ilkini/ikincisini/sonuncusunu sec" gibi bir '
            'komutla secim yapilabilir.')

    @staticmethod
    def _ogrenilen_ozet_metni(envanter: dict) -> str:
        """Madde 4: robot_envanteri.json icerigini (dict) insan-okunur bir
        ozet metnine cevirir -- TAMAMEN saf, dosya/ROS erisimi yok, ROS'suz
        izole test edilebilsin diye _ogrendiklerini_raporla'dan (dosya
        okuma + loglama) ayrildi (bkz. Madde 3/6'daki ayni desen).
        """
        raflar = envanter.get('raflar', {})
        if not raflar:
            return 'Henuz hicbir raf taramadim, ogrendigim bir sey yok.'

        raf_ozetleri = []
        toplam_kutu = 0
        for raf in sorted(raflar):
            tespitler = raflar[raf].get('tespitler', {})
            raf_toplam = sum(len(v) for v in tespitler.values())
            toplam_kutu += raf_toplam
            raf_ozetleri.append(f'{raf}: {raf_toplam} kutu')

        return (
            f'{len(raflar)} raf taradim ({", ".join(sorted(raflar))}), '
            f'toplam {toplam_kutu} kutu gordum. {", ".join(raf_ozetleri)}.'
        )

    def _robot_envanteri_yolu(self) -> Path:
        return Path(get_package_share_directory('depo_robotu')) / 'araclar' / 'robot_envanteri.json'

    def _robot_envanteri_yukle(self) -> dict:
        try:
            with open(self._robot_envanteri_yolu(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {'raflar': {}}

    def _robot_envanterini_kaydet(self) -> None:
        try:
            with open(self._robot_envanteri_yolu(), 'w', encoding='utf-8') as f:
                json.dump(self.robot_envanteri, f, ensure_ascii=False, indent=2)
        except OSError as e:
            self.get_logger().error(f'robot_envanteri.json yazilamadi: {e}')

    @staticmethod
    def _birlesmis_tespitler(mevcut_tespitler: dict, rapor: dict) -> dict:
        """BUG DUZELTMESI (24 Agustos 2026, bkz. modul docstring'i): rapor'un
        SADECE 'taranan_katlar' alanindaki katlarini gunceller,
        mevcut_tespitler'deki DIGER katlara DOKUNMAZ -- saf, deterministik
        fonksiyon (dosya/saat erisimi yok), ROS'suz izole test edilebilsin
        diye _robot_envanterini_guncelle'den ayrildi.

        'taranan_katlar' rapor'da yoksa (eski format ihtimaline karsi
        savunma) rapor'daki tum katlar taranmis sayilir -- eski (hatali
        ama zararsiz, cunku o zaman TUM katlar zaten rapor'daydi) davranisa
        geriye donuk uyumlu.
        """
        taranan_katlar = rapor.get('taranan_katlar')
        if taranan_katlar is None:
            taranan_katlar = list(rapor.get('tespitler', {}).keys())

        yeni = dict(mevcut_tespitler)
        rapor_tespitleri = rapor.get('tespitler', {})
        for kat in taranan_katlar:
            yeni[str(kat)] = rapor_tespitleri.get(str(kat), [])
        return yeni

    def _robot_envanterini_guncelle(self, rapor: dict) -> None:
        """Madde 4: bir /tarama_raporu geldiginde o rafin SADECE taranan
        katlarini gunceller -- eskiden rafin TUM girdisini degistiriyordu,
        bu da kismi (tek kat) bir tarama geldiginde o rafin onceden
        bilinen diger katlarini SILIYORDU (bkz. modul docstring'i, BUG
        DUZELTMESI)."""
        raf = rapor.get('raf')
        if raf is None:
            return
        mevcut = self.robot_envanteri.setdefault('raflar', {}).get(raf, {'tespitler': {}})
        self.robot_envanteri['raflar'][raf] = {
            'son_tarama_zamani': datetime.datetime.now().isoformat(timespec='seconds'),
            'tespitler': self._birlesmis_tespitler(mevcut.get('tespitler', {}), rapor),
        }
        self._robot_envanterini_kaydet()

    def _ogrendiklerini_raporla(self) -> None:
        ozet = self._ogrenilen_ozet_metni(self.robot_envanteri)
        self.get_logger().info(f'Ogrendiklerim: {ozet}')

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

        # Madde 6: iptal edilebilmesi icin saklaniyor.
        self._son_goal_handle = goal_handle
        sonuc_future = goal_handle.get_result_async()
        sonuc_future.add_done_callback(self._navigasyon_tamamlandi)

    def _navigasyon_tamamlandi(self, future) -> None:
        durum = future.result().status
        basarili = durum == GoalStatus.STATUS_SUCCEEDED
        self.get_logger().info(
            f"Navigasyon sonucu: {'BASARILI' if basarili else 'BASARISIZ'} (status={durum})")
        # Madde 6: navigasyon (basarili/basarisiz/iptal, farketmez) bitti --
        # artik iptal edilecek bir sey yok.
        self._son_goal_handle = None

        # Madde 1: eylem=='git' ise SADECE navigasyon isteniyor demektir --
        # kamera donmez, tarama tetiklenmez. Sadece eylem=='tara' tarama
        # baslatir. Istisna: eylem=='git' AMA bir dogrulama beklentisi
        # varsa (secim/en_yakin akislari), TEK KATLIK bir dogrulama
        # taramasi tetiklenir (bkz. modul docstring'i).
        if basarili and self._son_hedef_raf is not None and self._son_hedef_eylem == 'tara':
            self._tarama_baslat(self._son_hedef_raf, self._son_hedef_katlar)
        elif basarili and self._son_hedef_eylem == 'git' and self._son_dogrulama_beklentisi is not None:
            self._dogrulama_taramasini_baslat(self._son_hedef_raf, self._son_dogrulama_beklentisi)
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

    def _dogrulama_taramasini_baslat(self, raf: str, beklenti: dict) -> None:
        kat = beklenti.get('kat')
        if kat is None:
            self.get_logger().warn(
                'Dogrulama beklentisinde kat bilgisi yok, dogrulama atlandi.')
            self._son_dogrulama_beklentisi = None
            return
        self.get_logger().info(
            f"Hedefe varildi -- dogrulama icin raf={raf} kat={kat} taraniyor "
            f"(beklenen: {beklenti.get('renk')} {beklenti.get('boyut')})...")
        self._tarama_baslat(raf, katlar=[kat])

    @staticmethod
    def _dogrulama_sonucunu_belirle(beklenti: dict, gorulen_tespitler: list) -> str:
        """Gorsel dogrulama: TF/subprocess/dosya erisiminden bagimsiz saf
        karar mantigi -- Madde 3/6'daki ayni ayrim deseni (bkz.
        _en_yakin_eslesmeyi_sec/_iptal_eylemini_belirle). SADECE RENGE
        bakar (bkz. modul docstring'i, TASARIM KARARI).

        Returns: 'dogrulandi' | 'uyusmuyor' | 'gorulemedi'
        """
        if not gorulen_tespitler:
            return 'gorulemedi'
        for t in gorulen_tespitler:
            if t.get('renk') == beklenti.get('renk'):
                return 'dogrulandi'
        return 'uyusmuyor'

    def _dogrulamayi_raporla(self, rapor: dict, beklenti: dict) -> None:
        raf = rapor.get('raf')
        kat = beklenti.get('kat')
        gorulenler = rapor.get('tespitler', {}).get(str(kat), [])
        durum = self._dogrulama_sonucunu_belirle(beklenti, gorulenler)

        if durum == 'dogrulandi':
            self.get_logger().info(
                f"Dogrulandi: {raf} kat {kat}'te {beklenti.get('renk')} bir kutu "
                f"goruldu (beklenen boyut: {beklenti.get('boyut')}).")
        elif durum == 'uyusmuyor':
            gorulen_renkler = ', '.join(sorted({g.get('renk') for g in gorulenler if g.get('renk')}))
            self.get_logger().warn(
                f"Uyusmuyor: {raf} kat {kat}'te {beklenti.get('renk')} "
                f"bekleniyordu, bunun yerine {gorulen_renkler or 'baska bir sey'} goruldu.")
        else:
            self.get_logger().warn(
                f"Gorulemedi: {raf} kat {kat}'te beklenen {beklenti.get('renk')} "
                'kutu tespit edilemedi.')

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

        # Madde 4: pasif envanter MVP -- bu taramanin GERCEKTEN gordugu
        # (ground truth degil) kutular robot_envanteri.json'a kaydedilir.
        # Dogrulama taramalari da (tek katlik) buraya dahildir -- artik
        # SADECE taranan_katlar guncellenir, diger katlar SILINMEZ.
        self._robot_envanterini_guncelle(rapor)

        # Gorsel dogrulama: bu bir dogrulama taramasiysa sonucu raporla.
        if self._son_dogrulama_beklentisi is not None:
            self._dogrulamayi_raporla(rapor, self._son_dogrulama_beklentisi)
            self._son_dogrulama_beklentisi = None

        self._tarama_proc.terminate()
        self._tarama_proc = None
        self._beklenen_tarama_raf = None


def main(args=None):
    rclpy.init(args=args)
    dugum = NavigasyonKoprusu()

    # Sprint 5 madde 6 test oturumunda bulundu (bkz. NOTLAR.md SORUN 8 ek
    # notu, 24 Agustos 2026): duz `pkill`/`kill` (imzasiz, yani SIGTERM)
    # Python'da varsayilan olarak sureci ANINDA sonlandirir, asagidaki
    # `except KeyboardInterrupt` bloğu HIC calismaz -- bu da tarama_kontrol
    # alt surecini yetim birakiyordu. SIGTERM'i SIGINT gibi KeyboardInterrupt'a
    # cevirip AYNI temizlik yoluna sokuyoruz. NOT: `kill -9` (SIGKILL) hicbir
    # sinyal isleyicisi tarafindan yakalanamaz -- ona karsi tek koruma disaridan
    # (CLAUDE.md/NOTLAR.md/PROJE_DOSYASI.md temizlik komutlarina tarama_kontrol'u
    # de eklemek) saglanabilir, kod tarafinda degil.
    def _sigterm_isleyici(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _sigterm_isleyici)

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
