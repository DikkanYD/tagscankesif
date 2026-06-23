# tag-scan-kesif — masaüstü BLE keşif uygulaması

Bluetooth'lu bir PC'de çalışır; yakındaki **bilinmeyen** BLE tag'lerini bulup
`tag-scan-api` sunucusuna **API ile** gönderir. Sunucu uzakta (Bluetooth'suz)
olabilir — BLE işini bu uygulama yapar, sunucuyla yalnızca HTTP üzerinden konuşur.

## Neden bu var?

Tag'ler operatörün yanında, sunucu rack'te/uzakta. BLE kısa menzilli radyo
olduğundan uzak sunucu tag'leri **göremez**. Bu uygulama, tag'lere yakın PC'nin
Bluetooth'unu kullanarak keşfi yapar ve sonucu panele iletir.

```
Bu PC (bleak)                         tag-scan-api (uzak)
  GET  /api/v1/kayit-modu  ─────────►  kayıt modu açık mı?
  (açıksa) BLE tara, yakın bilinmeyenler
  POST /api/v1/kesif       ─────────►  panelin "Bilinmeyen tag'ler" listesine düşer
```

Panelde (Tag Yönetimi) o tag'e isim verilir → kalıcı tag olur.

## Kurulum

```powershell
cd tag-scan-kesif
python -m venv .venv ; .\.venv\Scripts\Activate.ps1   # (opsiyonel)
pip install -r requirements.txt
python kesif_app.py
```

İlk açılışta yanında bir `config.json` oluşur. Ayarlar:

| Anahtar | Açıklama | Varsayılan |
|---|---|---|
| `api_url` | tag-scan-api adresi (sonunda `/` yok) | `http://172.16.49.2:5090` |
| `api_token` | Sunucu `config.json` `api.token` ile aynı (boş = token yok) | `""` |
| `rssi_esigi` | Bundan güçlü (≥) görülen cihazlar keşfe gider. 0'a yakın = daha yakın olmalı | `-60` |
| `tarama_sn` | Her BLE tarama turu süresi | `6` |
| `kayit_modu_poll_sn` | Kayıt modu bayrağını yoklama aralığı | `10` |
| `sadece_kayit_modunda` | `true`: kayıt modu kapalıyken keşif göndermez | `true` |
| `kesif_cooldown_sn` | Aynı MAC'i tekrar göndermeden önce bekleme | `15` |

## Kullanım

1. Panelde **Tag Yönetimi → Kayıt modu**'nu aç.
2. `python kesif_app.py` çalışırken tag'i **bu PC'ye yaklaştır**.
3. Tag, panelin **"Bilinmeyen tag'ler (keşif)"** listesine düşer.
4. **Çalışan adını** yazıp kaydet → kalıcı tag olur, keşiften düşer.

> Etraftaki telefon/saat de eşiği geçerse listeye düşebilir; panelden "yoksay" ile
> geçersin. Çok düşüyorsa `rssi_esigi`'ni sıkılaştır (örn. `-45`) ve tag'i iyice yaklaştır.

## Sistem tepsisi (system tray) sürümü — `kesif_tray.py`

Konsol penceresi yerine **saatin yanındaki tepsi alanında** sessizce duran sürüm.
Aynı keşif/öttürme mantığını çalıştırır (`kesif_app.KesifUygulamasi`), sadece arayüzü
farklı. Saha PC'si için önerilen budur.

> **Neden servis değil?** BLE/Bluetooth, Windows servisinin koştuğu "Session 0"da
> güvenilmez çalışır (çoğu zaman cihaz göremez, üstelik sessizce). Tepsi uygulaması
> gerçek **kullanıcı oturumunda** çalışır → Bluetooth sorunsuz. "PC açılınca başlasın"
> ihtiyacını da aşağıdaki **Windows açılışında başlat** seçeneği karşılar.

```powershell
pip install -r requirements.txt          # pystray + Pillow dahil
pythonw kesif_tray.py                     # pencere açılmadan tepside başlar
```

Tepsi simgesine **sağ tık** menüsü:

| Öğe | Ne yapar |
|---|---|
| **Durumu göster** | Son log satırını baloncukta gösterir (sol tıkla da çıkar) |
| **Logları aç** | `kesif.log` dosyasını açar (pencere olmadığı için çıktı oraya yazılır) |
| **Windows açılışında başlat** | Oturum açılınca otomatik başlatmayı aç/kapat (`HKCU\…\Run`) |
| **Çıkış** | Uygulamayı kapatır |

- Aynı anda **tek kopya** çalışır (autostart + elle açma çakışmaz).
- Çıktılar `config.json` ile aynı klasördeki `kesif.log`'a gider (1 MB'ı geçince sıfırlanır).

## .exe yapmak (opsiyonel)

Kuruluma gerek kalmadan dağıtmak için:

```powershell
pip install pyinstaller

# Konsollu keşif sürümü:
pyinstaller --onefile --name tag-scan-kesif kesif_app.py

# Tepsi sürümü (pencere açılmaz):
pyinstaller tag-scan-kesif-tray.spec      # -> dist\tag-scan-kesif-tray.exe
# yanına config.json bırak; kesif.log orada oluşur
```

## Notlar

- Bu sürüm yalnız **keşif** yapar; sunucuda değişiklik gerektirmez (`/kesif` ve
  `/kayit-modu` uçları zaten var).
- İleride **öttürme** (panelden "Öttür" → bu uygulama o MAC'i öttürüp pil okur)
  eklenebilir; bunun için sunucuya küçük bir "öttür kuyruğu" ucu gerekir.
