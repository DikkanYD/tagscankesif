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

## .exe yapmak (opsiyonel)

Kuruluma gerek kalmadan dağıtmak için:

```powershell
pip install pyinstaller
pyinstaller --onefile --name tag-scan-kesif kesif_app.py
# dist\tag-scan-kesif.exe + yanına config.json
```

## Notlar

- Bu sürüm yalnız **keşif** yapar; sunucuda değişiklik gerektirmez (`/kesif` ve
  `/kayit-modu` uçları zaten var).
- İleride **öttürme** (panelden "Öttür" → bu uygulama o MAC'i öttürüp pil okur)
  eklenebilir; bunun için sunucuya küçük bir "öttür kuyruğu" ucu gerekir.
