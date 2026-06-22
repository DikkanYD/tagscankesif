"""tag-scan-kesif — masaüstü BLE keşif uygulaması.

Tek iş: Bluetooth'lu bu PC'de yakındaki BILINMEYEN tag'leri bulup tag-scan-api
sunucusuna API ile göndermek. Sunucu uzakta (Bluetooth'suz) olabilir; BLE'yi
bu uygulama yapar, sunucuyla yalnızca HTTP üzerinden konuşur.

Akış:
  - GET  {API_URL}/api/v1/kayit-modu   -> kayıt modu açık mı?
  - (açıksa) bleak ile etraf taranır; YETERINCE YAKIN (RSSI >= eşik) cihazlar
  - POST {API_URL}/api/v1/kesif        -> { mac, rssi, ad, kaynak }
  Sunucu zaten KAYITLI tag'leri keşif listesinden eler; uygulama hepsini gönderir,
  aynı MAC'i KESIF_COOLDOWN_SN boyunca tekrar göndermez.

Çalıştırma:  python kesif_app.py   (ayarlar: config.json — ilk açılışta oluşturulur)
Durdurma:    Ctrl+C
"""
import asyncio
import json
import os
import sys
import time

import requests
from bleak import BleakClient, BleakScanner

KOK = os.path.dirname(os.path.abspath(__file__))
CONFIG_YOLU = os.path.join(KOK, "config.json")

# Öttürme (Gigaset keeper / DA1458x) — Immediate Alert servisi 0x1802 / 0x2A06 <- 0x02.
# DIKKAT: 0x2A06 hem Link Loss (1803) hem Immediate Alert (1802)'de var; DOGRU
# servisin (1802) karakteristigini secmek gerek.
IAS_SERVICE = "00001802-0000-1000-8000-00805f9b34fb"
IAS_ALERT_LEVEL = "00002a06-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
FIRMWARE_REV = "00002a26-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"

VARSAYILAN = {
    "api_url": "http://172.16.49.2:5090",   # tag-scan-api adresi (sonunda / olmasın)
    "api_token": "",                         # config.json api.token ile aynı (boş = token yok)
    "rssi_esigi": -60,                       # bundan güçlü (>=) görülen cihazlar keşfe gider
    "tarama_sn": 6,                          # her BLE tarama turu süresi
    "kayit_modu_poll_sn": 10,                # kayıt modu bayrağını yoklama aralığı
    "sadece_kayit_modunda": True,            # True: kayıt modu kapalıyken keşif göndermez
    "kesif_cooldown_sn": 15,                 # aynı MAC'i tekrar göndermeden önce bekleme
    "ottur_saniye": 2.0,                     # öttürme süresi (sonra susturulur)
    "ottur_poll_sn": 2,                      # öttür kuyruğunu yoklama aralığı (boştayken)
}


def config_yukle():
    """config.json'u yükler; yoksa varsayılanla oluşturur. Eksik anahtarları tamamlar."""
    cfg = dict(VARSAYILAN)
    if os.path.exists(CONFIG_YOLU):
        try:
            with open(CONFIG_YOLU, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[UYARI] config.json okunamadı ({e}); varsayılanlar kullanılıyor.")
    else:
        try:
            with open(CONFIG_YOLU, "w", encoding="utf-8") as f:
                json.dump(VARSAYILAN, f, ensure_ascii=False, indent=2)
            print(f"[BILGI] Örnek config.json oluşturuldu: {CONFIG_YOLU}")
        except OSError:
            pass
    return cfg


class KesifUygulamasi:
    def __init__(self, cfg):
        self.api_url = cfg["api_url"].rstrip("/")
        self.token = (cfg.get("api_token") or "").strip()
        self.rssi_esigi = int(cfg["rssi_esigi"])
        self.tarama_sn = float(cfg["tarama_sn"])
        self.kayit_poll_sn = float(cfg["kayit_modu_poll_sn"])
        self.sadece_kayit = bool(cfg["sadece_kayit_modunda"])
        self.cooldown_sn = float(cfg["kesif_cooldown_sn"])
        self.ottur_saniye = float(cfg.get("ottur_saniye", 2.0))
        self.ottur_poll_sn = float(cfg.get("ottur_poll_sn", 2))

        self._son_gonderim = {}        # mac -> son POST zamanı (monotonic)
        self._kayit_modu = False
        self._kayit_yoklandi = 0.0     # son kayıt modu yoklama zamanı

    # -------- HTTP --------
    @property
    def _basliklar(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def kayit_modu_acik(self):
        """Sunucudan kayıt modu bayrağını çeker (hata olursa son bilineni korur)."""
        try:
            r = requests.get(f"{self.api_url}/api/v1/kayit-modu",
                             headers=self._basliklar, timeout=4)
            if r.ok:
                self._kayit_modu = bool(r.json().get("acik", False))
        except requests.RequestException as e:
            print(f"[UYARI] kayıt modu sorgulanamadı: {e}")
        return self._kayit_modu

    def kesif_gonder(self, mac, rssi, ad):
        """Bilinmeyen MAC'i sunucuya bildirir (cooldown'lu)."""
        simdi = time.monotonic()
        son = self._son_gonderim.get(mac)
        if son is not None and simdi - son < self.cooldown_sn:
            return False
        self._son_gonderim[mac] = simdi

        govde = {"mac": mac, "rssi": rssi, "ad": ad or "", "kaynak": "pc-kesif"}
        try:
            r = requests.post(f"{self.api_url}/api/v1/kesif", json=govde,
                              headers=self._basliklar, timeout=5)
            ok = r.ok
        except requests.RequestException as e:
            print(f"[HATA] kesif POST başarısız ({mac}): {e}")
            return False
        durum = "OK" if ok else f"HTTP {r.status_code}"
        print(f"[KESIF] {mac}  '{ad or ''}'  rssi={rssi}  -> {durum}")
        return ok

    def ottur_bekleyenleri_al(self):
        """Sunucudan bekleyen öttür isteklerini çeker (atomik -> 'isleniyor')."""
        try:
            r = requests.get(f"{self.api_url}/api/v1/ottur-bekleyen",
                             headers=self._basliklar, timeout=4)
            if r.ok:
                return r.json().get("istekler", [])
        except requests.RequestException as e:
            print(f"[UYARI] öttür kuyruğu sorgulanamadı: {e}")
        return []

    def ottur_sonuc_gonder(self, istek_id, ok, bilgi, mesaj):
        """Öttür sonucunu sunucuya yazar."""
        govde = {"id": istek_id, "ok": ok, "mesaj": mesaj,
                 "pil": bilgi.get("pil"), "firmware": bilgi.get("firmware"),
                 "model": bilgi.get("model")}
        try:
            requests.post(f"{self.api_url}/api/v1/ottur-sonuc", json=govde,
                          headers=self._basliklar, timeout=5)
        except requests.RequestException as e:
            print(f"[HATA] öttür sonuç gönderilemedi (id={istek_id}): {e}")

    # -------- BLE --------
    async def _bir_tur(self):
        bulunan = await BleakScanner.discover(timeout=self.tarama_sn, return_adv=True)
        gonderilen = 0
        for addr, (dev, adv) in bulunan.items():
            rssi = adv.rssi
            if rssi is None or rssi < self.rssi_esigi:
                continue                      # yeterince yakın değil
            ad = (dev.name or "").strip()[:60]
            if self.kesif_gonder(addr.upper(), rssi, ad):
                gonderilen += 1
        return gonderilen, len(bulunan)

    async def _cihaz_bul(self, mac):
        """MAC'i discover ile bul (seyrek reklam -> birkaç kez dene)."""
        hedef = mac.upper()
        for _ in range(3):
            bulunan = await BleakScanner.discover(timeout=8.0, return_adv=True)
            for addr, (dev, _adv) in bulunan.items():
                if addr.upper() == hedef:
                    return dev
        return None

    async def _ottur_tek(self, mac):
        """Tek tag'i öttür + pil/firmware/model oku. (ok, mesaj, bilgi) döner."""
        dev = await self._cihaz_bul(mac)
        if dev is None:
            return False, "Tag bulunamadı (yakın/uyanık mı?)", {}

        bilgi = {}
        async with BleakClient(dev) as client:
            beep_char = None
            for service in client.services:
                if service.uuid.lower() != IAS_SERVICE:
                    continue
                for char in service.characteristics:
                    if char.uuid.lower() == IAS_ALERT_LEVEL:
                        beep_char = char
                        break
            if beep_char is None:
                return False, "Tag öttürme (Immediate Alert) desteklemiyor.", {}

            await client.write_gatt_char(beep_char, bytearray([0x02]), response=False)
            await asyncio.sleep(self.ottur_saniye)
            try:
                await client.write_gatt_char(beep_char, bytearray([0x00]), response=False)
            except Exception:
                pass

            # Aynı bağlantıda bedava bilgi oku
            for anahtar, uuid in (("pil", BATTERY_LEVEL), ("firmware", FIRMWARE_REV),
                                  ("model", MODEL_NUMBER)):
                try:
                    raw = await client.read_gatt_char(uuid)
                    if anahtar == "pil":
                        bilgi["pil"] = raw[0] if raw else None
                    else:
                        bilgi[anahtar] = bytes(raw).decode("utf-8", "replace").strip()
                except Exception:
                    pass
        return True, "Tag öttürüldü.", bilgi

    async def ottur_kuyrugunu_isle(self):
        """Bekleyen öttür isteklerini sırayla işler (her biri: öttür + sonuç yaz)."""
        for istek in self.ottur_bekleyenleri_al():
            mac = istek.get("mac", "")
            istek_id = istek.get("id")
            print(f"[OTTUR] istek #{istek_id} {mac} ...")
            try:
                ok, mesaj, bilgi = await self._ottur_tek(mac)
            except Exception as e:  # noqa: BLE001
                ok, mesaj, bilgi = False, f"Öttürme hatası: {e}", {}
            print(f"[OTTUR] #{istek_id} -> {'OK' if ok else 'HATA'} {mesaj} {bilgi}")
            self.ottur_sonuc_gonder(istek_id, ok, bilgi, mesaj)

    async def calistir(self):
        try:
            import bleak  # noqa: F401
        except ImportError:
            print("[HATA] bleak kurulu değil. 'pip install -r requirements.txt'")
            return
        print(f"tag-scan-kesif başladı. Sunucu: {self.api_url}  eşik: {self.rssi_esigi} dBm")
        print("Kayıt modunu panelden açın, tag'i bu PC'ye yaklaştırın. (Ctrl+C ile çıkış)\n")
        while True:
            try:
                # 1) Öttür kuyruğu — panelden gelen istekleri her zaman işle (önce bu)
                await self.ottur_kuyrugunu_isle()

                # 2) Kayıt modu bayrağını periyodik yokla
                simdi = time.monotonic()
                if simdi - self._kayit_yoklandi >= self.kayit_poll_sn:
                    self.kayit_modu_acik()
                    self._kayit_yoklandi = simdi

                # 3) Keşif taraması (kayıt modu açıksa); değilse öttür için kısa bekle
                if self.sadece_kayit and not self._kayit_modu:
                    await asyncio.sleep(self.ottur_poll_sn)
                    continue

                gonderilen, toplam = await self._bir_tur()
                if gonderilen:
                    print(f"  ({gonderilen} yakın bilinmeyen gönderildi / {toplam} cihaz görüldü)")
            except Exception as e:  # noqa: BLE001 — saha/BLE hatasını yutup devam et
                print(f"[UYARI] döngü hatası: {e}")
                await asyncio.sleep(5)


def main():
    cfg = config_yukle()
    uygulama = KesifUygulamasi(cfg)
    try:
        asyncio.run(uygulama.calistir())
    except KeyboardInterrupt:
        print("\nÇıkılıyor.")
        sys.exit(0)


if __name__ == "__main__":
    main()
