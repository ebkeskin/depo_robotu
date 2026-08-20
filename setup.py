import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'depo_robotu'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*.sdf')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'araclar'), glob('araclar/envanter.json')),
        (os.path.join('share', package_name, 'araclar'), glob('araclar/adres_veritabani.json')),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ebk',
    maintainer_email='bilalkeskin6728@gmail.com',
    description='Yapay zeka destekli akilli depo robotu',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'kamera_kontrol = depo_robotu.kamera_kontrol:main',
            'kat_tespit = depo_robotu.kat_tespit:main',
            'piksel_kat_tespit = depo_robotu.piksel_kat_tespit:main' ,
            'renk_probu = depo_robotu.renk_probu:main' ,
            'kutu_tespit = depo_robotu.kutu_tespit:main',
            'tarama_kontrol = depo_robotu.tarama_kontrol:main',
            'adres_dogrula = depo_robotu.adres_dogrula:main',
            'konum_yakala = depo_robotu.konum_yakala:main',
        ],
    },
)
