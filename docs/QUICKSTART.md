# TVCare hızlı başlangıç

Bu rehber hazır TVCare paketini ilk kez kullanmak içindir. **Android TV veya Google TV** gerekir; Samsung Tizen ve LG webOS desteklenmez. AI hesabına ihtiyacın yok.

TVCare 1.0.0 **Public Preview**, herkese açık ön sürümdür. Hazır paket, belirli bir TV’de bakımın doğrulandığı anlamına gelmez. [Test kapsamı](VERIFICATION.md)

## 1. Paketi indir ve çıkar

[TVCare 1.0.0 indirme sayfasını aç](https://github.com/paylanovic/TVCare/releases/tag/v1.0.0). **Assets** bölümündeki TVCare ZIP dosyalarından işletim sistemin ve işlemcinle eşleşeni seç. GitHub’ın otomatik **Source code** arşivleri hazır uygulama değildir.

| Sistem | Paket adında ara | Başlatıcı |
|---|---|---|
| Windows | `windows` ve uygun işlemci türü | `Start-TVCare.cmd` |
| macOS | `darwin` ve uygun işlemci türü | `TVCare.command` |
| Linux | `linux` ve uygun işlemci türü | `TVCare.sh` |

Paketin tamamını bir klasöre çıkar. İçindeki dosyaları birbirinden ayırma; ZIP içinden başlatma. Yalnızca indirme sayfasında mevcut olan işletim sistemi paketlerini kullan. Hazır paket için Python kurulumu gerekmez.

Mac’te **Bu Mac Hakkında**, Windows’ta **Ayarlar → Sistem → Hakkında** ekranından işlemci türünü görebilirsin. Apple Silicon genellikle `arm64`, Intel/AMD 64 bit bilgisayarlar `x86_64` veya `AMD64` olarak adlandırılır.

## 2. TV bağlantı aracını ekle

TVCare, TV ile **ADB** üzerinden iletişim kurar. Varsayılan paket ADB içermez; Google’ın resmî paketini bir kez indirmen gerekir.

1. [Android Platform Tools indirme sayfasını aç](https://developer.android.com/tools/releases/platform-tools).
2. Kendi işletim sisteminin ZIP dosyasını indir ve çıkar.
3. Çıkan **`platform-tools` klasörünün tamamını** TVCare çalıştırılabilir dosyasının yanına taşı. Yalnızca `adb` dosyasını kopyalama; paketteki yardımcı dosyalar da gerekebilir.

```text
TVCare/
├── TVCare.exe veya TVCare
├── Start-TVCare.cmd, TVCare.command veya TVCare.sh
├── platform-tools/
│   ├── adb.exe veya adb
│   └── ...Google paketinin diğer dosyaları
└── ...TVCare paketinin diğer dosyaları
```

TVCare bu konumu otomatik bulur. Daha önce kurulmuş ve erişilebilir Android SDK / PATH konumları da desteklenir. Paketli sürümde `_internal/platform-tools`, kaynak sürümde proje kökündeki `platform-tools` klasörü de kullanılabilir.

## 3. TVCare’i aç

İşletim sistemine uygun başlatıcıyı çalıştır. Tarayıcıda TVCare açılır. Terminal penceresi uygulamanın çalışmasını sağlar; bakım bitene kadar açık bırak.

Linux’ta dosya yöneticisi başlatıcıyı çalıştırmıyorsa, çıkardığın TVCare klasöründe terminal aç:

```sh
chmod +x TVCare TVCare.sh
./TVCare.sh
```

macOS paketi Apple noter onaylı değildir; Windows paketi yayıncı sertifikasıyla imzalı değildir. Sistem uygulamayı engellerse yayın sayfasındaki açıklamaları ve kaynağı kontrol et. Güvenlik korumalarını topluca kapatma.

Tarayıcı otomatik açılmazsa terminalde gösterilen **tam yerel bağlantıyı** aç. Bağlantıdaki oturum anahtarı erişimi korur; paylaşma.

## 4. TV’de ilk bağlantıyı hazırla

1. Bilgisayar ile TV’yi aynı yerel ağa bağla. TV açık kalsın.
2. TV’de **Ayarlar → Sistem / Cihaz tercihleri → Hakkında** bölümünü aç. **Derleme** satırına 7 kez basarak geliştirici seçeneklerini etkinleştir. Menü adları modele göre değişebilir.
3. **Geliştirici seçenekleri** içinde cihazın sunduğu **USB hata ayıklama**, **ağ hata ayıklama** veya **kablosuz hata ayıklama** seçeneğini aç.
4. TVCare’de **TV bağlantısı** sayfasını aç.

### IP adresiyle bağlantı

TV’nin ağ ayarlarında gösterilen adresi ve desteklenen bağlantı portunu kullan. Örneğin `192.0.2.10:5555` yalnızca örnek yazımdır; **kendi TV’nin gerçek adresini girmelisin**. `5555` her cihazda çalışmaz; TV farklı port gösteriyorsa onu kullan.

**Bağlan** düğmesine bas. TV’de bilgisayarın için izin ekranı çıkarsa onayla. Ardından cihaz listesini yenile ve **Seç ve kontrol et** düğmesine bas.

### Eşleştirme kodu isteyen TV

TV’nin kablosuz hata ayıklama ekranından **eşleştirme koduyla cihaz eşleştirme** seçeneğini aç. TVCare’de **Eşleştirme kodu isteyen TV’ler** bölümüne TV’nin gösterdiği eşleştirme adresini, portunu ve 6 haneli kodunu gir.

Eşleştirmeden sonra TV’nin normal **bağlantı adresi ve portuyla** bağlan. Eşleştirme portu ile bağlantı portu farklı olabilir.

Bazı TV’ler ağ üzerinden ADB sunmaz. Böyle bir cihazı adres tahmin ederek bağlamaya çalışmak işe yaramaz. [Android’in resmî ADB bağlantı açıklamaları](https://developer.android.com/tools/adb)

## 5. Önce kontrol et, sonra bakım seç

**Seç ve kontrol et** yalnızca cihaz bilgilerini okur. Bellek veya boş alan ölçümünün alınamaması “sıfır” ya da “arıza yok” anlamına gelmez; arayüz eksik bilgiyi belirtir.

**Bakım seçenekleri** sayfasında ihtiyacın olan değişiklikleri seç. Her uygulamanın ne işe yaradığını ve kapatılınca hangi özelliğin etkileneceğini oku. **Değişiklikleri incele** ekranında önceki ve sonraki değerleri kontrol et; yalnızca onayladığında uygulanır.

TV ana kullanıcı profilinde olmalıdır. Cihaz kimliği, TV türü veya ana profil doğrulanamıyorsa araç yalnızca tanı sunar. Korumalı veya tanınmayan paketler seçilemez.

## 6. Sonucu kontrol et ve gerekirse geri al

TV’de kumanda, ses, görüntü ve kullandığın uygulamaları kontrol et. Ardından **İşlem geçmişi** üzerinden sonuçları incele.

Geri dönmek için aynı TV’yi seç, ilgili kaydın **Geri alma planını incele** düğmesine bas ve planı onayla. Bu işlem yalnızca kaydedilmiş ve mevcut durumu doğrulanabilen değerleri geri getirir; tam TV yedeği değildir. Sonradan başka şekilde değiştirdiğin ayarlar çakışma yaratabilir; üzerine otomatik yazılmaz.

**Kısmen tamamlandı** veya **Kesintiye uğradı** gördüğünde işlemi yeniden körlemesine başlatma. Kaydı ve hata açıklamasını incele; gerekirse ilk bakım kaydından geri alma planı oluştur.

## Kapanma kilidi koruyucusu

Bu seçenek yalnızca desteklenen TCL profili ve ilgili hata kanıtı varsa kullanılabilir. Genel bir donma çözümü değildir. Koruyucu, belirli kalıcı kapanış beklemesinde TV’yi tamamen kapatır; sonraki açılış normal beklemeden uyanmaya göre daha uzun sürebilir.

Koruyucunun çalışması için hata ayıklama açık kalmalı ve TV’de koruyucunun ayrı ADB izni onaylanmalıdır. Koruyucu kurulu değilse, bakım bitince hata ayıklamayı kapatabilirsin. [Destek koşulları](DEVICE_SUPPORT.md)

## Sık karşılaşılan durumlar

| Ekrandaki durum | Yapılacak işlem |
|---|---|
| **ADB bulunamadı** | İşletim sistemine uygun `platform-tools` klasörünün doğru yerde olduğundan emin ol; TVCare’i yeniden başlat. |
| **Unauthorized / izin bekleniyor** | TV ekranındaki bilgisayar iznini onayla ve cihaz listesini yenile. |
| **Offline / çevrimdışı** | TV’nin açık olduğunu, ağını ve adres/port bilgisini kontrol et. |
| **Bağlantı zaman aşımı** | Aynı yerel ağda olduğunu ve TV’nin ağ ADB’sini desteklediğini doğrula. |
| **Oturum anahtarı geçersiz** | Çalışan TVCare terminalinin gösterdiği tam bağlantıyı aç. Eski bir yer imini kullanma. |
| **Değiştirilecek ayar yok** | Seçilen değerler zaten uygulanmış olabilir; cihazı yeniden kontrol et. |

## TV bağlamadan denemek

Çıkardığın paket klasöründe terminal aç:

```sh
# macOS / Linux
./TVCare --demo
```

```powershell
# Windows PowerShell
.\TVCare.exe --demo
```

**ÖRNEK MODU** sentetik cihaz kullanır; gerçek TV’ye bağlanmaz. Demo sonuçları fiziksel test kanıtı değildir.

## Destek isterken

Uygulamadaki **rapor indir** düğmesini kullan ve dosyayı paylaşmadan önce incele. [Hata bildirim formunda](https://github.com/paylanovic/TVCare/issues/new/choose) işletim sistemini, TV modelini, beklediğin davranışı ve gördüğün hatayı yaz.

**Ham log, IP adresi, seri numarası, yerel kullanıcı yolu, bağlantı anahtarı, ADB özel anahtarı veya tüm veri klasörünü paylaşma.** Ekran görüntülerindeki bu alanları da kapat. Yalnızca sorunu anlatmak için gereken bilgiyi paylaş.

[README’ye dön](../README.md)
