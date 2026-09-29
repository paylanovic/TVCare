# TVCare dağıtımı

TVCare'in çalışma zamanında AI, bulut hesabı veya Python paketi indirmesi gerekmez. Kaynaktan çalıştırma Python 3.10+ gerektirir. Tek klasör dağıtımı Python yorumlayıcısını içerir. İlk dağıtım konsol penceresiyle çalışır; yerel tarayıcı arayüzü açılır. macOS'ta `TVCare.command`, Windows'ta `Start-TVCare.cmd` çift tıklanabilir başlatıcıdır; hata olursa pencere açık kalır. Program çalışırken terminali açık tutun; kapatmak için Ctrl+C kullanın. macOS paketi noter onaylı `.app` değildir.

## Mevcut makine için paket

İzole derleme ortamında `python -m pip install -r requirements-build.txt` ile derleme bağımlılıklarını yükledikten sonra proje kökünde:

```sh
python scripts/build_release.py
```

Betik önce testleri çalıştırır, sonra `packaging/tvcare.spec` üzerinden mevcut işletim sistemi/mimariye özgü `dist/TVCare/` ve ZIP üretir. Kendisi ağdan bağımlılık indirmez. Python sürümü, hedef mimari, APK özeti ve test kapsamı `BUILD.json` içine yazılır. Dosya özetleri `SHA256SUMS` dosyasındadır. `--skip-tests` kullanılırsa test sonucu `NOT_RUN` olarak kaydedilir.

Windows paketi Windows'ta, macOS paketi macOS'ta, Linux paketi Linux'ta ayrı oluşturulup denenmelidir. PyInstaller'ın çıktısı derleme işletim sistemi ve Python mimarisine özeldir. [PyInstaller resmi açıklaması](https://pyinstaller.org/en/stable/operating-mode.html)

Bu depoda bir hedef için derleme yapmış olmak diğer işletim sistemlerinde çalıştığını kanıtlamaz. macOS noter onayı / Apple Developer imzası ve Windows yayıncı imzası ayrıca sağlanmalıdır. İmzalanmamış paketleri imzalı yayın gibi tanıtmayın.

## ADB

Varsayılan dağıtım Android Platform Tools içermez. Kullanıcı resmi Platform Tools paketini kurabilir veya `TVCARE_ADB` ile mevcut `adb` dosyasını seçebilir. [Android'in resmi indirme sayfası](https://developer.android.com/tools/releases/platform-tools)

İçeriği ve dağıtım hakkı ayrıca kontrol edilmiş yerel bir Platform Tools dizinini açıkça dahil etmek için:

```sh
python scripts/build_release.py --platform-tools /path/to/platform-tools
```

Bu seçenek host `adb` ikilisini, ilgili dinamik kütüphaneleri, `NOTICE`/`LICENSE` dosyalarını ve varsa `source.properties` bilgisini taşır. Bildirim/lisans dosyası bulunmazsa derleme durur. `adbkey`, kullanıcı yetki anahtarları ve diğer kullanıcı verileri kopyalanmaz. SDK sözleşmesi ile açık kaynak bileşenlerin koşulları aynı değildir; SDK sözleşmesinin 3.4 ve 3.5 maddeleri bu ayrımı yapar. Bildirim dosyası bulunması tek başına her ikilinin yeniden dağıtım iznini kanıtlamaz. [Android SDK koşulları](https://developer.android.com/studio/terms)

## Android koruyucu APK'sı

`resources/guard/build.sh` kaynak Java, Android kaynakları ve tek kaynak bekçi betiğinden APK üretir. Gereksinimler Android SDK build-tools 36.0.0, android-36 platform JAR'ı ve JDK'dır. `ANDROID_SDK_ROOT`, `JAVA_HOME`, `TVCARE_BUILD_TOOLS`, `TVCARE_ANDROID_PLATFORM` ile yollar/sürümler değiştirilebilir.

```sh
export TVCARE_KEYSTORE=/secure/outside-repository/release.keystore
# Parolayı güvenli ortam değişkeni olarak sağlayın; kaynak koda veya komut geçmişine yazmayın.
export TVCARE_KEY_ALIAS=kk
bash resources/guard/build.sh
```

`TVCARE_KEYSTORE_PASSWORD` ortam değişkeni zorunludur. Anahtar/parola verilmezse betik durur; otomatik anahtar üretmez. Kaynak depoya veya dağıtım paketine özel anahtar konmaz. Mevcut kurulumu güncellemek aynı imza anahtarını gerektirir. Yayımlanan APK, TVCare projesine özel yayın anahtarıyla imzalanır. Farklı bir anahtarla imzalanmış önceki kurulumu güncellemez; mevcut koruyucunun üzerine otomatik kurulum yapılmaz.

APK kurulumu ve cihaz üzerindeki çalışması ayrı kontrollerdir. `apksigner verify` APK imzasını doğrular; canlı TV'de başlatma/kapama testinin yerine geçmez.

## Yayın kabulü

- Her hedef paketi temiz kullanıcı hesabında açın; tanı, demo ve eksik ADB yollarını deneyin.
- Gerçek TV'de her değişiklik için önceki durumu ve geri almayı doğrulayın.
- Koruyucuyu gerçek uyumlu firmware üzerinde ayrı sınayın.
- ZIP içeriğinde özel anahtar, kullanıcı raporu, eski `yedek/` veya çalışma günlükleri bulunmadığını doğrulayın.
- Son ZIP'in SHA-256 özetini ve gerçek test sonuçlarını paylaşın.

Yayın veya yükleme bu derleme betiğinin parçası değildir.

## Otomasyon

`.github/workflows/ci.yml` Windows, macOS ve Linux üzerinde test ve paket işlerini tanımlar. Bu dosyanın varlığı CI çalıştığı anlamına gelmez: uzak CI sonucu bu çalışma kapsamında `NOT_RUN` durumundadır. İş akışı canlı ADB cihazı kullanmaz; koruyucu APK'sını kaynaklara dahil edilmiş imzalı dosyadan taşır. Özel APK imza anahtarı CI'a veya kaynaklara eklenmez.
