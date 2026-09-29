"""Conservative opt-in catalogue. Unknown and critical packages are never eligible."""
TCL_PROFILE = "tcl_beyondtv4_rtd288o_a11"
PROTECTED = frozenset({
    "android", "com.android.systemui", "com.android.settings", "com.android.shell",
    "com.android.providers.settings", "com.android.providers.media", "com.android.bluetooth",
    "com.android.packageinstaller", "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller", "com.android.permissioncontroller",
    "com.google.android.gms", "com.google.android.gsf", "com.android.vending",
    "com.google.android.katniss", "com.google.android.inputmethod.latin",
    "com.google.android.tv.remote.service", "com.google.android.apps.tv.launcherx",
    "com.google.android.tvlauncher", "com.google.android.tungsten.setupwraith",
    "com.android.tv", "com.android.providers.tv", "com.tcl.tv", "com.tcl.tvinput",
    "com.kilitkoruyucu.tv",
})

# Metadata describes losses of functionality, not promises of performance gain.
CATALOG = {
    "com.google.android.youtube.tvmusic": ("YouTube Music", "TV'deki ayrı YouTube Music uygulaması kapanır.", "media", None),
    "com.google.android.play.games": ("Google Play Oyunlar", "Play Oyunlar uygulaması ve bağlı oyun özellikleri kullanılamayabilir.", "games", None),
    "com.tcl.browser": ("TCL Tarayıcı", "TV'nin yerleşik internet tarayıcısı kapanır.", "optional", TCL_PROFILE),
    "com.tcl.magiconnectfree": ("MagiConnect", "Telefonla TV kontrolü ve içerik aktarımı kullanılamayabilir.", "casting", TCL_PROFILE),
    "com.tcl.miracast": ("Miracast", "Kablosuz ekran yansıtma kapanır.", "casting", TCL_PROFILE),
    "com.tcl.gamebar": ("TCL Game Bar", "Oyun araç çubuğu kapanır.", "games", TCL_PROFILE),
    "com.tcl.ocean.instructions": ("TCL Kullanım Kılavuzu", "TV üzerindeki kullanım kılavuzu kapanır.", "optional", TCL_PROFILE),
    "com.tcl.esticker": ("TCL Tanıtım Etiketi", "Mağaza tanıtım etiketleri kapanır.", "optional", TCL_PROFILE),
    "com.tcl.overseasappshow": ("TCL Uygulama Önerileri", "TCL uygulama öneri yüzeyi kapanır.", "recommendations", TCL_PROFILE),
    "com.tcl.waterfall.overseas": ("TCL İçerik Önerileri", "TCL içerik keşfi ve önerileri kullanılamayabilir.", "recommendations", TCL_PROFILE),
}


def metadata(package, profile):
    row = CATALOG.get(package)
    if package in PROTECTED:
        return {"label": package, "description": "Temel sistem, giriş, ses veya ana ekran bileşeni.", "category": "protected", "eligible": False, "reason": "Korunan sistem bileşeni."}
    if not row:
        return {"label": package, "description": "Bu paket için doğrulanmış bakım profili bulunmuyor.", "category": "unknown", "eligible": False, "reason": "Katalog dışı paket; otomatik değişiklik yapılamaz."}
    label, description, category, required = row
    eligible = required is None or profile == required
    return {"label": label, "description": description, "category": category, "eligible": eligible, "reason": "" if eligible else "Paket yalnızca eşleşen TCL cihaz profilinde desteklenir."}
