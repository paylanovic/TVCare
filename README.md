# TVCare

**Android TV ve Google TV için, kontrolü sana bırakan bakım aracı.** Bilgisayarında çalışır ve tarayıcıda açılır. AI hesabı, abonelik veya bulut bağlantısı gerektirmez.

**1.0.0 Public Preview:** İlk herkese açık ön sürüm. Cihaz desteği ve test kapsamını aşağıda incele.

[İndir](https://github.com/paylanovic/TVCare/releases/tag/v1.0.0) · [Hızlı başlangıç](docs/QUICKSTART.md) · [English](README.en.md)

![TVCare genel bakış ekranı — sentetik örnek cihaz](docs/screenshots/desktop.png)

*Ekran görüntüsündeki cihaz ve ölçümler sentetik demo verisidir; fiziksel TV test sonucu değildir.*

## Üç adımda başla

### 1. İndir ve ZIP’i çıkar

[TVCare 1.0.0 sürümünün **Assets** bölümünü aç](https://github.com/paylanovic/TVCare/releases/tag/v1.0.0). İşletim sistemin ve işlemcinle eşleşen TVCare ZIP dosyasını indir. ZIP içinden çalıştırma; klasörün tamamını çıkar.

| Bilgisayarın | İndirilecek paket | Açılacak dosya |
|---|---|---|
| Windows | `windows` yazan, işlemcine uygun ZIP | `Start-TVCare.cmd` |
| macOS | `darwin` yazan, işlemcine uygun ZIP | `TVCare.command` |
| Linux | `linux` yazan, işlemcine uygun ZIP | `TVCare.sh` |

Hazır paketlerde Python kurmana gerek yok. Yalnızca sürüm sayfasında gerçekten yayımlanmış dosyaları kullan; paket listesi ve test durumu sürüm notlarında belirtilir. macOS paketleri Apple tarafından noter onaylı, Windows paketleri yayıncı sertifikasıyla imzalı değildir.

### 2. ADB’yi yanına koy ve başlat

TVCare’in TV ile iletişim kurması için Google’ın **Android Platform Tools** paketi gerekir. ADB, varsayılan TVCare dağıtımına dahil değildir.

[Resmî Platform Tools sayfasından](https://developer.android.com/tools/releases/platform-tools) kendi işletim sisteminin ZIP dosyasını indir ve çıkar. İçindeki **`platform-tools` klasörünü TVCare uygulamasının yanına koy**:

```text
TVCare/
├── TVCare.exe veya TVCare
├── platform-tools/
│   └── adb.exe veya adb
└── ...diğer paket dosyaları
```

Yukarıdaki tabloda belirtilen başlatıcıyı aç. TVCare, ADB’yi otomatik bulur ve tarayıcıda açılır. Uygulamayı kullanırken terminal penceresi açık kalsın.

### 3. TV’yi bağla, kontrol et, seç

Bilgisayar ve TV aynı yerel ağda olsun. TV’de geliştirici seçeneklerini ve cihazın desteklediği hata ayıklamayı aç. TVCare’de **TV bağlantısı** ekranını takip et, TV ekranında bilgisayarına izin ver ve **Seç ve kontrol et** düğmesine bas.

Bakım seçeneklerini seç → değişiklik planını incele → onayla. İlk kontrol ayarları değiştirmez; bakım seçenekleri önceden seçili gelmez.

**Bağlantı adımları ve sık karşılaşılan sorunlar:** [Hızlı başlangıç rehberi](docs/QUICKSTART.md)

## Neler yapabilirsin?

- Bellek, depolama, açık kalma süresi ve erişilebilen hata göstergelerini incele.
- Menü animasyonlarının süresini ayarla.
- Tanınan isteğe bağlı uygulamaları, etkilerini okuyarak devre dışı bırak veya yeniden etkinleştir.
- TV’de zaten kurulu ana ekran ve ekran koruyucu seçenekleri arasında geçiş yap.
- Her işlemde önceki ve sonraki değerleri gör; işlem geçmişinden geri alma planı oluştur.
- Paylaşmadan önce inceleyebileceğin, hassas alanları azaltılmış JSON destek raporu indir.
- Uyumlu TCL cihazında ilgili hata kanıtı varsa, isteğe bağlı kapanma kilidi koruyucusunun kurulum planını incele.

TVCare rastgele uygulama kaldırmaz, root açmaz veya firmware yüklemez. Yeni ana ekran uygulamalarını TV’nin resmî mağazasından kurup cihazı yeniden kontrol edebilirsin.

## Hangi TV’ler destekleniyor?

**Android TV / Google TV ve izin verilmiş ADB erişimi gerekir. Samsung Tizen ve LG webOS desteklenmez.** Android kullanan her cihazın ağ üzerinden ADB sunması garanti değildir.

Genel bakım, cihazın TV olduğu, kalıcı kimliği ve ana kullanıcı profili doğrulanabildiğinde açılır. Bilinmeyen paketler korunur. Kapanma kilidi koruyucusu yalnızca tanımlı TCL BeyondTV4 / RTD288O / Android 11 profili ve doğrulanmış hata koşulları içindir; tüm TV donmalarını çözmez.

[Destek kapsamı ve koruyucunun sınırları](docs/DEVICE_SUPPORT.md)

## Geri alma ve gizlilik

TVCare, değiştireceği değerleri önce kaydeder ve uygulamadan sonra tekrar okur. **Geri alma yalnızca kaydedilmiş ve mevcut durumu doğrulanabilen değerler içindir; tam cihaz yedeği değildir.** Daha sonra başka şekilde değiştirilen değerlerin üzerine otomatik yazılmaz. Kısmi veya kesilmiş bir işlemin ayrıntılarını işlem geçmişinden inceleyebilirsin.

Arayüz yalnızca bilgisayarında çalışır; telemetri veya otomatik rapor yükleme yoktur. Destek isterken uygulamanın hazırladığı sadeleştirilmiş raporu kullan ve paylaşmadan önce içeriğini kontrol et. Ham logları, cihaz adreslerini, seri numaralarını, bağlantı anahtarlarını veya tüm veri klasörünü paylaşma.

Bu sürümün yeni bakım akışları fiziksel TV’de kabul testinden geçirilmemiştir. Otomatik testler ve demo, gerçek cihaz doğrulamasının yerine geçmez. [Güncel doğrulama durumu](docs/VERIFICATION.md)

## TV olmadan dene

Paket içindeki **Demo-TVCare.command** (macOS), **Demo-TVCare.cmd** (Windows) veya **Demo-TVCare.sh** (Linux) başlatıcısını aç. ADB veya gerçek TV gerekmez.

İstersen terminalden de başlatabilirsin:

```sh
# macOS / Linux
./TVCare --demo
```

```powershell
# Windows PowerShell
.\TVCare.exe --demo
```

Demo sentetik cihaz kullanır ve gerçek ADB bağlantısı kurmaz. Arayüzde belirgin **ÖRNEK MODU** etiketi görünür.

## Kaynak koddan çalıştır

Python **3.10 veya üstü** gerekir. Çalışma zamanı için üçüncü taraf Python bağımlılığı yoktur.

```sh
git clone https://github.com/paylanovic/TVCare.git
cd TVCare
python3 -m tvbakim
```

Windows’ta son komut yerine `py -3 -m tvbakim` kullanabilirsin. Kaynak sürümde `platform-tools` klasörünü bu README ile aynı dizine koy. Demo için komuta `--demo` ekle.

```sh
python3 -m unittest discover -s tests -v
node --check tvbakim/static/app.js
```

[Mimari](docs/ARCHITECTURE.md) · [Dağıtım](docs/DISTRIBUTION.md) · [Hata bildir](https://github.com/paylanovic/TVCare/issues/new/choose)

## Lisans

TVCare [MIT lisansı](LICENSE) ile sunulur. Android Platform Tools gibi ayrı indirilen bileşenler kendi lisanslarına tabidir.
