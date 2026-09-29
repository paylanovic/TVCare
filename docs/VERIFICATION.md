# TVCare doğrulama kaydı

Bu kayıt sentetik, otomatik CI ve fiziksel cihaz kanıtını ayırır.

## 1.0.1 Windows gereksinim kurulumu

Yeni Windows ilk açılış akışı; mevcut ADB'yi kullanmayı veya kullanıcının lisans kabulü sonrası resmî Google Platform Tools paketini sabit SHA-256 özetiyle doğrulayarak kullanıcı hesabına kurmayı amaçlar. Her sürüm paketinin otomatik test kanıtı, ilgili commit’in CI sonucu ve sürüm ekindeki raporlarıdır. Önceki sürümün testleri bu yeni yolun kanıtı değildir; temiz Windows kullanıcı akışı ayrıca değerlendirilir.

| Kontrol | Sonuç | Kapsam |
| --- | --- | --- |
| Yerel 1.0.1 birim / entegrasyon ve regresyon testleri | PASS | 111 test başarılı; yaklaşık 8,9 saniye. Kurulum testleri dahil, Windows etkileşimli kullanıcı testi değildir |
| Windows hedefinde CI test ve paket kontrolü | Sürüm raporuna bak | İlgili commit’in [CI sonucu](https://github.com/paylanovic/TVCare/actions/workflows/ci.yml), paketteki `BUILD.json` ve sürüm ekindeki `*-setup-smoke.json` |
| `Start-TVCare.cmd` çift tıklama → kurulum → arayüz | NOT_RUN | Etkileşimli Windows başlatıcı zinciri; yalnızca EXE smoke testi bu yolun kanıtı değildir |
| `Install-Requirements.cmd` çift tıklama | NOT_RUN | Etkileşimli Windows başlatıcı yolu; komut dosyası statik testi kullanıcı akışının yerine geçmez |
| Lisans reddi / indirme hatası / SHA-256 uyuşmazlığı | PASS | Yerel birim ve entegrasyon testleri. Hedef Windows paket kanıtı için ilgili commit CI sonucu ve `*-setup-smoke.json`; yalnızca raporlanan senaryoları kapsar |
| Demo: ağ / indirme / gerçek ADB olmadan açılış | Sürüm raporuna bak | İlgili commit CI sonucu ve sürüm ekindeki smoke raporları; `.cmd` çift tıklama ayrıca yukarıda belirtilir |
| ADB / Python / winget olmayan temiz Windows sanal makinesi | NOT_RUN | İlk kurulum internetli; sonraki açılış kullanılabilir ADB ile çevrimdışı |
| 1.0.1 gerçek TV kabulü | NOT_RUN | Fiziksel cihaz ve bakım/geri alma doğrulaması yapılmadı |

Otomatik Windows CI başarılı olsa bile temiz Windows sanal makinesinde kullanıcı akışı ve fiziksel TV kabulü ayrı kalır. Windows paketi yayıncı sertifikasıyla imzalı değildir; macOS noter onayı yoktur.

## 1.0.0 doğrulama tabanı

Tarih: 29 Eylül 2026. Ortam: macOS / Apple Silicon, Python 3.14.7. Aşağıdaki sonuçlar önceki sürümün mevcut kanıtıdır; 1.0.1 kurulum yoluna otomatik olarak aktarılmaz.

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
| Yayıncı imzası / macOS noter onayı | NOT_RUN | Windows yayıncı sertifikası ve Apple noter onayı yok |

## Paket kanıtlarını okumak

Windows, Linux, macOS Apple Silicon ve macOS Intel paketleri için ilgili sürüm/commit hedef platform test ve derleme sonuçları [GitHub Actions](https://github.com/paylanovic/TVCare/actions/workflows/ci.yml) kayıtlarında bulunur. Her pakette `BUILD.json` çalıştırılan/atlanan test sayılarını, `SMOKE.json` sentetik paket kontrolünü gösterir. Sürüm ekindeki `*-smoke.json` gerçek ZIP çıkarılarak yapılan kontrolü de içerir. Windows’ta POSIX bekçi testleri atlanabilir; bu atlamalar gizlenmez. Paket testi fiziksel TV kabulü değildir.

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
