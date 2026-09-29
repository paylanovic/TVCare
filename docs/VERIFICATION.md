# TVCare doğrulama kaydı

Tarih: 29 Eylül 2026. Ortam: macOS / Apple Silicon, Python 3.14.7. Bu kayıt sentetik ve fiziksel kanıtı ayırır.

| Kontrol | Sonuç | Kanıt / kapsam |
| --- | --- | --- |
| Python birim ve entegrasyon testleri | PASS | ADB argümanları, kimlik/profil, CAM kanıtı, işlem günlüğü, kısmi hata, geri alma, guard kurulum/durdurma, HTTP ve rapor gizliliği; aşağıdaki komut |
| JavaScript sözdizimi | PASS | `node --check tvbakim/static/app.js` |
| Chromium uçtan uca | PASS | Gerçek yerel sunucu + açıkça sentetik TV: kontrol, 4-adım plan, açık onay, uygula, exact rollback, JSON indir |
| Tarayıcı yetkilendirme | PASS | Token URL'den temizleniyor; yeni token'sız bağlam API'de 401 alıyor |
| Mobil arayüz | PASS | Chromium 390×844, beş görünümde yatay sayfa taşması yok; ekran görüntüsü incelendi |
| Safari arayüzü | PASS | Masaüstü ve 390×844 görünümü incelendi; sentetik uygulama/geri alma akışını tamamladı |
| Chromium JavaScript / CSP | PASS | Uçtan uca akışta pageerror veya CSP ihlali görülmedi |
| Android koruyucu derleme / imza | PASS | APK 1.1 / versionCode 2, apksigner doğrulaması; projeye özel yayın imzası |
| Gerçek bekçi betiği simülasyonu | PASS | Monotonik beş saniye, geçici/normal durumlar, çoklu koşul, PID tekrar kullanımı, kilit, durdurma, kayıt döndürme, eski süreç |
| macOS arm64 dağıtımı | PASS | PyInstaller yerel derleme; paket ikilisinde sürüm ve izole demo sunucu kontrolü |
| Paket gizliliği | PASS | Özel anahtar / eski yedek / cihaz günlüğü dağıtımda yok; dosya SHA256 manifesti |
| Yeni sürümün gerçek TV testi | NOT_RUN | Bu sürüm için yeni fiziksel TV kabul testi yapılmadı |
| Yeni koruyucunun fiziksel açılış/kapanış testi | NOT_RUN | Fiziksel cihaz testi ayrıca gereklidir |
| Windows / Linux paket çalıştırma | NOT_RUN | Başlatıcı ve CI tarifleri hazır; hedef OS'lerde çalıştırma sonucu yok |
| Uzak CI | NOT_RUN | İş akışı dosyası hazır, repo yayımlanmadı ve CI tetiklenmedi |
| Yayıncı imzası / macOS noter onayı | NOT_RUN | Yerel paket dağıtımı; imzalı kamu yayını yapılmadı |

## Tekrarlama

```sh
python3 -m unittest discover -s tests -v
node --check tvbakim/static/app.js
python scripts/browser_smoke.py
python scripts/build_release.py
```

Tarayıcı komutu ayrı Playwright+Chromium ortamı gerektirir. Android bekçi testleri Windows'ta POSIX kabuk yoksa `SKIP` olur; bu durumda tamamı çalıştırılmış gibi yorumlanmaz. `BUILD.json` derleme ortamı ve APK özetini içerir. `SHA256SUMS` paket içeriğini doğrular.

## Görsel kanıt

- [Masaüstü — sentetik TV](screenshots/desktop.png)
- [Mobil — sentetik TV](screenshots/mobile.png)

Ekranlardaki bellek/depolama değerleri örnek veridir; gerçek TV ölçümü, optimizasyon kazancı veya canlı cihaz testi değildir.
