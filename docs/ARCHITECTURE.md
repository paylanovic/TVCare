# TVCare mimarisi

## Akış

Yerel tarayıcı → token korumalı HTTP API → tek sıralı iş kuyruğu → işlem motoru → ADB argv çağrıları → seçili TV.

- `adb.py`: Platform Tools bulma, açık cihaz seçimi, IP/port doğrulama, komut süreleri, hata denetimi. Yerel kabuk yoktur (`shell=False`); uzak argümanlar `shlex.join` ile alıntılanır. 8 MiB üzeri çıktı reddedilir; bu sınır mevcut sürümde yakalama sonrasında kontrol edilir.
- `device.py`: salt okunur kimlik, TV/ana profil yeteneği, gerçek paket durumları, sınırlı log ve ölçümler. Eksik ölçüm `null` olur.
- `catalog.py`: açıklamalı izin verilen paketler. Kritik/bilinmeyen paketler kapatılamaz.
- `engine.py`: istemciden serbest komut almaz. Planlarda ayar, değer ve paket izin listeleri; cihaz+firmware bağlama; süre ve replay kontrolü. Guard işlemleri ayrı kapılı plan üretir.
- `store.py`: 0600 geçici dosya + fsync + atomik rename; bir veri klasöründe tek süreç kilidi. Yeniden başlatmada çalışan günlükler kesintiye uğramış olarak işaretlenir.
- `server.py`: yalnızca loopback, token, origin/host doğrulama, 32 KiB istek sınırı, statik dosya izin listesi, dış kaynakları kapatan CSP. Genel internete hizmet vermek için tasarlanmamıştır.
- `report.py`: ham kayıt yerine dar alanlardan destek raporu.
- `demo.py`: gerçek ADB'ye hiç erişmeyen sentetik model; gerçek veri klasöründen ayrı.
- `static/`: derleme veya CDN gerektirmeyen yerel Türkçe arayüz.
- `resources/guard/`: Android companion + tek kaynak bekçi betiği. Özel imza anahtarı proje dışındadır.

## İşlem durumu

Plan: cihaz kimliği, önceki değerler, sonraki değerler, uyarılar, son geçerlilik zamanı. Planlar sadece bellektedir; uygulama yeniden başlatılınca tekrar oluşturulur.

Günlük: `running` → her adım `pending` → `running` → `verified`; hata `partial`; süreç kaybı `interrupted`; bütün adımlar doğrulanınca `succeeded`. Komutun başarı kodu tek başına yeterli değildir: ilgili değer yeniden okunur.

Kayıt bir komuttan önce diske yazılır. TV komutu alıp yanıtı kaybolursa geri alma, TV'deki mevcut değeri eski/yeni değerle karşılaştırarak değişen adımı bulur. Eski değere dönmüş adım atlanır; üçüncü bir değer çakışmadır. Geri alma da ayrı bir günlük tutar.

Guard'ın yeni APK kurulumu sonrası OEM varsayılan AppOps değeri dinamik okunur ve izin yazılmadan önce kaydedilir. Başarısız açılışta companion hâlâ yeniden deniyor olabilir; geri alma, bekçi görünmese bile companion'ı durdurur. Eski guard betiği `--status` tanımadığı için önce sürüm işareti salt okunur kontrol edilir. Eski betiğe durum komutu yürütülmez.

## Bilinen sınırlar

- ADB ölçümleri kontrollü benchmark değildir. Son 500 olay kaydı açılıştan beri toplam değildir.
- TV'nin tüm ayarları veya uygulama verisi yedeklenmez; sadece uygulanacak değişikliğin geri dönüş verisi saklanır.
- Yeni launcher kurulumu ve firmware/root işleri kapsam dışıdır. Mevcut HOME rolü okunamıyorsa değişim kapalıdır.
- Aynı kullanıcı hesabındaki kötü amaçlı yazılıma karşı izolasyon sağlanmaz. Yerel kayıtlar kullanıcıya aittir.
- Kalıcı donanımsal kimlik/firmware okunamayan TV tanı modundadır; yanlış cihaza geri alma için ağ adresine güvenilmez.
- Fiziksel TV kabulü, yeniden açılış davranışı ve diğer OS paketleri ayrı doğrulama gerektirir.
