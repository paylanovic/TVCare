# TVCare ürün ve uygulama planı

TVCare, yapay zekâ veya bulut hesabı gerektirmeden Android/Google TV bakımını kullanıcının bilgisayarından yürütür. Tanı otomatik değişiklik uygulamaz; her bakım ayrı bir onaylı planla yürütülür.

## Teslim edilecek kapsam

1. Türkçe yerel web arayüzü: bağlantı yardımı, cihaz seçimi, teşhis, seçmeli bakım, işlem inceleme, geçmiş, geri alma, rapor.
2. ADB keşfi: kurulu veya paketle açıkça sağlanan Platform Tools; USB/ağ cihaz listesi, IP bağlantısı, desteklenen TV'lerde kablosuz eşleştirme. Kullanıcının RSA onayı atlanmaz.
3. Cihaz yetenekleri ve profilleri: TV dışı cihazda müdahale engeli, bilinmeyen modellerde yalnızca genel doğrulanabilir işlemler, modele özel katalog.
4. Ölçüm: bilinmeyen alanlar sıfır gibi gösterilmez; log tamponundan alınan sayılar açılıştan beri toplam olarak sunulmaz. Bağımsız kontrollü performans iddiası yapılmaz.
5. İşlem motoru: ön inceleme, sabit cihaz kimliği, süreli tek kullanımlık plan, adım öncesi diske kayıt, uygulama sonrası okuma, kısmi başarısızlık ve kesinti kurtarma.
6. Geri alma: ayarın bulunmaması dahil tam eski değer; paket etkinlik durumunu aynen geri yükleme. Sonradan farklı değişmiş alanlarda çakışma bildirimi. Rastgele eski kaydı başka cihaza uygulama yok.
7. Seçenekler: animasyonlar, katalogdaki isteğe bağlı paketler, cihazda kurulu ana ekran ve ekran koruyucu seçimi. Yeni launcher için resmî mağaza üzerinden kullanıcı kurulumu; rastgele APK indirme yok.
8. TCL/Realtek koruyucu: özel profil + hata kanıtı; sınırlandırılmış tanı, monotonik zaman, kontrollü durdurma, güncel durum, geri alınabilir yeni kurulum. Mevcut koruyucu APK'sını yedeksiz yükseltme yok.
9. Güvenlik: loopback dinleme, oturum anahtarı, Host/Origin doğrulama, sabit API eylemleri, shell=False, çıktı/zaman sınırları, dış kaynak/CDN/telemetri yok. Yerel sunucu internete açılmaz.
10. Dağıtım: kaynak çalıştırıcıları, işletim sistemine özel paketleme tarifi, SHA256 manifesti, özel anahtar/yedek/kişisel log hariç. Hazır paket için platformda derleme ve test kanıtı ayrı tutulur.

## Kalite kapıları

- Birim testleri: komut enjeksiyonu, cihaz ayrımı, eksik çıktı, paket koruması, exact restore, stale plan, replay, bağlantı kopması, crash recovery.
- HTTP testleri: token, origin, host, gövde boyutu, bilinmeyen rota, hata yanıtı.
- Demo uçtan uca: tanı → plan → uygulama → doğrulama → geri alma, sentetik olduğu sürekli görünür.
- Tarayıcı: masaüstü/mobil, klavye, hata/boş/yükleniyor durumları, ekran taşması.
- APK: derleme, imza doğrulaması; yeni sürüm için canlı TV testi ayrıca NOT_RUN olarak raporlanır.
- Platform: bu Mac'te gerçek çalıştırma; Windows/Linux için yerel çalıştırma veya CI olmadan PASS iddiası yok.

## Kapsam sınırı

Root, bootloader, firmware yazma, fabrika sıfırlama, uygulama verisi silme, otomatik cihaz reboot/kapatma ve bilinmeyen paket temizliği sunulmaz. Koruyucunun donma anında kapatma davranışı yalnızca açık kurulum planında onaylanır. Ürün tam iş akışları içerir; tüm TV modellerinde aynı hatayı düzelttiği iddia edilmez.
