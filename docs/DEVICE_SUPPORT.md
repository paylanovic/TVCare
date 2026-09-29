# TVCare cihaz desteği ve doğrulama sınırları

TVCare, ADB erişimi olan Android TV / Google TV cihazları için yerel bakım aracıdır. Samsung Tizen, LG webOS ve Android çalıştırmayan TV'lerde çalışmaz. Modelin Android olması her işlemin o modelde doğrulandığı anlamına gelmez.

| Yetenek | Koşul | Bu sürümün kanıtı |
| --- | --- | --- |
| Cihaz tanıma ve raporlama | ADB yetkilendirmesi, gerekli salt okunur komutlar | Sahte ADB / birim testleri; yeni canlı TV testi yapılmadı |
| Animasyon ve desteklenen ayarlar | Ayar okunabilir, işlem sonunda değer tekrar okunur | Önceki değer günlüğü ve geri alma testleri |
| Seçmeli paket devre dışı bırakma | Katalogda tanınan paket, açık kullanıcı seçimi | Paket durumu işlemden önce ve sonra kontrol edilir |
| Alternatif ana ekran | Kurulu, Android HOME etkinliği sağlayan uygulama | Cihaza bağlı; otomatik harici APK indirme yok |
| TVCare Koruyucu 1.1 | Android 11/API 30+, profille uyumlu TCL/Realtek, belirli CI CAM kapanma hatası, yerel ADB 5555 | APK derleme/imza kontrolü ve gerçek betikle yerel simülasyon; yeni APK canlı cihazda denenmedi |
| Kablosuz ADB eşleştirme | Cihazın Android kablosuz hata ayıklama desteği | Modele göre değişir; her Android TV bu arayüzü sunmaz |

## Koruyucunun davranışı

Koruyucu genel performans artırıcı değildir. `rtk.hal.cam_suspend=start`, `sys.tcl.powerstatus=suspend` ve `rtk.hal.CICam_State!=true` birlikte en az 5 saniye sürerse kapatma ister. Süre `/proc/uptime` üzerinden ölçülür. Müdahaleden hemen önce koşullar yeniden okunur. Normal açılışta veya CAM yanıtı gelmişken kapatma istenmez.

`reboot -p` ve gerekirse `svc power shutdown` komutları 3 saniyelik `timeout` ile sınırlıdır. Timeout aracı yoksa komut çalıştırılmaz ve durum kayda yazılır. Başarısız dönüşte 60 saniye beklenir. Tanı için bloklayabilecek `dumpsys` veya `sync` kullanılmaz. Kayıt 64 KiB eşiğinde tek önceki dosyaya döner. Bu yaklaşım firmware hatasını düzeltmez; belirli kapanma takılmasından kurtarma girişimidir.

Uygulama `com.kilitkoruyucu.tv`, sürüm 1.1 / kod 2 kimliğini korur. Minimum ve hedef API 30'dur. Yeni Android sürümlerinin arka plan/ön plan hizmeti kuralları için ayrıca cihaz testi gerekir; her Android 11+ cihaz destekli ilan edilmez.

## Cihaz üstündeki dosyalar ve komutlar

Tüm çalışma dosyaları `/data/local/tmp/` altında `kilit-koruyucu` önekini kullanır:

- `kilit-koruyucu.sh`: çalıştırılan betik.
- `kilit-koruyucu.pid`, `kilit-koruyucu.lock/pid` ve `kilit-koruyucu.flock`: süreç kimliği ve çekirdek kilidiyle tek kopya denetimi. `flock` yoksa bekçi başlatılmaz.
- `kilit-koruyucu.log`, `kilit-koruyucu.log.1`: sınırlı yerel kayıtlar.
- `kilit-koruyucu.disabled`: korumayı durdurur ve yeniden açılışta da durdurulmuş tutar.

```sh
sh /data/local/tmp/kilit-koruyucu.sh --status
sh /data/local/tmp/kilit-koruyucu.sh --stop
# Yalnızca kullanıcının açık etkinleştirme isteğiyle:
am start-foreground-service -a com.kilitkoruyucu.tv.START -n com.kilitkoruyucu.tv/.GuardService
```

Durum çıktısı `RUNNING:<pid>`, `STOPPING:<pid>`, `STOPPED`, `DISABLED` veya `LEGACY` olur. `--status` PID'nin sadece mevcut olmasına değil, komut satırındaki betik yoluna da bakar. `--stop` süreç sonlanana kadar normalde bir tur bekler; başlamış bir kapatma isteğini geri çeviremez. Çalışan eski bir bekçi güncel sürüm gibi raporlanmaz; otomatik öldürülmez veya ikinci kopyası başlatılmaz. TV uygulamasına dönmek sadece güncel kontrol yapar; korumayı kendiliğinden yeniden etkinleştirmez. TV'deki Başlat düğmesi açık etkinleştirmedir. Son kontrol zamanı gösterilir; bu sürekli uzak canlı izleme değildir.

## Yeni model doğrulama

Yeni cihaz desteği için gerçek marka/model, Android API, donanım, firmware/build fingerprint ve hata günlüğü birlikte kaydedilmelidir. Genel özellikler ile modele özel koruma ayrı değerlendirilmelidir. Donma örneği, normal kapanış, CAM hazır durumu, yeniden başlatma sonrası bekçi, devre dışı bırakma sonrası yeniden başlatma ve geri alma gerçek cihazda sınanmalıdır. Başarı tarihini ve firmware kimliğini saklayın; farklı firmware'e otomatik genellemeyin.

Bu sürüm için fiziksel TV kabul testi henüz yapılmadı. Birim ve paket testleri gerçek cihaz testi yerine geçmez.
