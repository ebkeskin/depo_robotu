#!/usr/bin/env python3
"""
Renk kalibrasyon araci - goruntuye tikladigin pikselin gercek HSV
degerini terminale yazdirir. kutu_tespit.py'nin HSV esiklerini
tahmin yerine GERCEK degerlerle ayarlamak icin kullanilir.

Kullanim: farkli renkteki kutulara VE raf govdesine (mavi direkler,
turuncu tablalar) tikla, degerleri not al - boylece "mavi kutu" ile
"mavi raf direkleri", "karton kutu" ile "turuncu raf" birbirinden
ayrilabiliyor mu gorebiliriz.
"""

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image


class RenkProbu(Node):

    def __init__(self):
        super().__init__('renk_probu')
        self.bridge = CvBridge()
        self.son_kare = None

        self.create_subscription(
            Image, '/camera/image_raw', self.goruntu_geldi, 10)

        cv2.namedWindow('Renk Probu')
        cv2.setMouseCallback('Renk Probu', self.tiklama_geldi)
        self.create_timer(0.03, self.pencereyi_guncelle)

        self.get_logger().info('Renk probu hazir. Farkli renklere tiklayip HSV degerlerini gorun.')

    def goruntu_geldi(self, mesaj):
        self.son_kare = self.bridge.imgmsg_to_cv2(mesaj, desired_encoding='bgr8')

    def tiklama_geldi(self, event, u, v, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN or self.son_kare is None:
            return
        bgr = self.son_kare[v, u]
        hsv = cv2.cvtColor(np.uint8([[bgr]]), cv2.COLOR_BGR2HSV)[0][0]
        self.get_logger().info(
            f'Piksel ({u},{v}) -> BGR={tuple(int(x) for x in bgr)}  '
            f'HSV=(H={hsv[0]}, S={hsv[1]}, V={hsv[2]})')

    def pencereyi_guncelle(self):
        if self.son_kare is not None:
            cv2.imshow('Renk Probu', self.son_kare)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    dugum = RenkProbu()
    try:
        rclpy.spin(dugum)
    except KeyboardInterrupt:
        pass
    cv2.destroyAllWindows()
    dugum.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()