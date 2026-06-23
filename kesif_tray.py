r"""tag-scan-kesif — sistem tepsisi (system tray) sürümü.

Aynı keşif/öttürme mantığını çalıştırır (kesif_app.KesifUygulamasi), ama konsol
penceresi yerine saatin yanındaki tepsi alanında bir simge olarak durur.

Neden tepsi (servis değil)?
  BLE/Bluetooth, Windows servisinin çalıştığı "Session 0"da güvenilmez çalışır.
  Tepsi uygulaması gerçek kullanıcı oturumunda koşar -> Bluetooth sorunsuz.
  "PC açılınca otomatik başla" işini de tepsi menüsündeki "Windows açılışında
  başlat" seçeneği (HKCU\...\Run) ile veririz; servise gerek kalmaz.

Simgeye sağ tık -> menü:
  - Durumu göster : son log satırını baloncukta gösterir
  - Logları aç    : kesif.log dosyasını açar (pencere olmadığı için çıktı oraya gider)
  - Windows açılışında başlat : oturum açılınca otomatik başlatmayı aç/kapat
  - Çıkış

Çalıştırma:  pythonw kesif_tray.py   (veya tag-scan-kesif-tray.exe)
"""
import asyncio
import os
import socket
import sys
import threading
from datetime import datetime

import pystray
from PIL import Image, ImageDraw
from pystray import Menu, MenuItem as Oge

from kesif_app import KOK, KesifUygulamasi, config_yukle

LOG_YOLU = os.path.join(KOK, "kesif.log")
RUN_ANAHTARI = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_ADI = "tag-scan-kesif"
TEK_ORNEK_PORT = 50595          # ikinci kopyayı engellemek için localhost kilidi


class LogYazici:
    """print() çıktısını bir dosyaya yazar ve son satırı tepsi için saklar.

    Tepside konsol yok; kesif_app içindeki print'ler buraya akar (sys.stdout
    buna yönlendirilir). Dosya çok büyürse başında bir kez sıfırlanır.
    """

    def __init__(self, yol):
        self.son_satir = "başlıyor..."
        self._kilit = threading.Lock()
        try:
            if os.path.exists(yol) and os.path.getsize(yol) > 1_000_000:
                open(yol, "w", encoding="utf-8").close()
        except OSError:
            pass
        self._f = open(yol, "a", encoding="utf-8", buffering=1)

    def write(self, metin):
        with self._kilit:
            self._f.write(metin)
            kirpik = metin.strip()
            if kirpik:
                self.son_satir = kirpik
        return len(metin)

    def flush(self):
        try:
            self._f.flush()
        except OSError:
            pass


def tek_ornek_kilidi():
    """Tek bir kopya çalışsın diye localhost portunu tutar.

    Bağlanamazsa (port dolu) zaten bir kopya çalışıyordur -> None döner.
    Dönen soketi açık tutmak gerekir (process boyunca referansı saklayın).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", TEK_ORNEK_PORT))
        return s
    except OSError:
        s.close()
        return None


def ikon_yap(renk=(0, 150, 60)):
    """Basit, dosyasız bir tepsi ikonu (yeşil daire) üretir."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ciz = ImageDraw.Draw(img)
    ciz.ellipse((6, 6, 58, 58), fill=renk)
    ciz.ellipse((24, 24, 40, 40), fill=(255, 255, 255))
    return img


# -------- Windows açılışında başlat (HKCU\...\Run) --------
def _calistirma_komutu():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    # pythonw -> konsol penceresi açılmaz
    pyw = sys.executable
    if pyw.lower().endswith("python.exe"):
        pyw = pyw[:-len("python.exe")] + "pythonw.exe"
    return f'"{pyw}" "{os.path.abspath(__file__)}"'


def acilista_mi():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_ANAHTARI) as k:
            deger, _ = winreg.QueryValueEx(k, RUN_ADI)
            return bool(deger)
    except (FileNotFoundError, OSError):
        return False


def acilis_ayarla(ac):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_ANAHTARI, 0,
                        winreg.KEY_SET_VALUE) as k:
        if ac:
            winreg.SetValueEx(k, RUN_ADI, 0, winreg.REG_SZ, _calistirma_komutu())
        else:
            try:
                winreg.DeleteValue(k, RUN_ADI)
            except FileNotFoundError:
                pass


def _arka_plan(uygulama):
    """BLE keşif/öttürme döngüsünü ayrı bir thread'de çalıştırır."""
    try:
        asyncio.run(uygulama.calistir())
    except Exception as e:  # noqa: BLE001
        print(f"[HATA] arka plan döngüsü durdu: {e}")


def main():
    kilit = tek_ornek_kilidi()
    if kilit is None:
        # Zaten bir kopya çalışıyor; sessizce çık (autostart + elle açma çakışmasın).
        return

    log = LogYazici(LOG_YOLU)
    sys.stdout = log
    sys.stderr = log
    print(f"[TRAY] tag-scan-kesif tepsi sürümü başladı "
          f"{datetime.now():%Y-%m-%d %H:%M:%S}")

    cfg = config_yukle()
    uygulama = KesifUygulamasi(cfg)
    threading.Thread(target=_arka_plan, args=(uygulama,), daemon=True).start()

    def loglari_ac(icon, item):
        try:
            os.startfile(LOG_YOLU)  # noqa: S606 (Windows)
        except OSError as e:
            print(f"[UYARI] log açılamadı: {e}")

    def durum_goster(icon, item):
        icon.notify(log.son_satir[:180], "tag-scan-kesif")

    def acilis_degistir(icon, item):
        try:
            acilis_ayarla(not acilista_mi())
        except OSError as e:
            print(f"[UYARI] açılış ayarı değiştirilemedi: {e}")
        icon.update_menu()

    def cik(icon, item):
        print("[TRAY] çıkılıyor.")
        icon.stop()

    menu = Menu(
        Oge("tag-scan-kesif", None, enabled=False),
        Oge(lambda item: f"Sunucu: {uygulama.api_url}", None, enabled=False),
        Menu.SEPARATOR,
        Oge("Durumu göster", durum_goster, default=True),
        Oge("Logları aç", loglari_ac),
        Oge("Windows açılışında başlat", acilis_degistir,
            checked=lambda item: acilista_mi()),
        Menu.SEPARATOR,
        Oge("Çıkış", cik),
    )

    icon = pystray.Icon("tag-scan-kesif", ikon_yap(), "tag-scan-kesif", menu)
    icon.run()
    # Menüden Çıkış -> icon.run() döner. Daemon thread'i kesin kapatmak için:
    os._exit(0)


if __name__ == "__main__":
    main()
