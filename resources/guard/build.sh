#!/bin/bash
# Kilit Koruyucu APK'sını Gradle'sız derler: aapt2 → javac → d8 → zipalign → apksigner.
# Çıktı: kilit-koruyucu.apk (bu klasörde)
set -euo pipefail
cd "$(dirname "$0")"

SDK="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Library/Android/sdk}}"
BT="$SDK/build-tools/${TVCARE_BUILD_TOOLS:-36.0.0}"
ANDROID_JAR="$SDK/platforms/${TVCARE_ANDROID_PLATFORM:-android-36}/android.jar"
JDK="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export JAVA_HOME="$JDK"
export PATH="$JDK/bin:$PATH"
: "${TVCARE_KEYSTORE:?Set TVCARE_KEYSTORE to your external signing key}"
: "${TVCARE_KEYSTORE_PASSWORD:?Set signing password via environment}"
[ -f "$TVCARE_KEYSTORE" ] || { echo "Signing key missing" >&2; exit 1; }
OUT=build
GEN="$OUT/gen/com/kilitkoruyucu/tv"
mkdir -p "$GEN" "$OUT/classes" "$OUT/dex"

# 1) Bekçi betiğini Java sabitine göm; tek kaynak kilit-koruyucu.sh
B64=$(base64 < kilit-koruyucu.sh | tr -d '\n')
cat > "$GEN/Script.java" <<EOF
package com.kilitkoruyucu.tv;

/** build.sh üretir: kilit-koruyucu.sh içeriği (base64). Elle düzenlemeyin. */
final class Script {
    static final String B64 = "$B64";

    private Script() {
    }
}
EOF

# 2) Kaynaklar ve manifest → R.java + kaynak APK'sı
"$BT/aapt2" compile --dir res -o "$OUT/res.zip"
"$BT/aapt2" link -o "$OUT/app-unsigned.apk" -I "$ANDROID_JAR" --manifest AndroidManifest.xml \
    --java "$OUT/gen" "$OUT/res.zip"

# 3) Java → class → dex
find src "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
"$JDK/bin/javac" --release 11 -encoding UTF-8 -Xlint:-options -classpath "$ANDROID_JAR" \
    -d "$OUT/classes" @"$OUT/sources.txt"
"$BT/d8" --release --min-api 30 --lib "$ANDROID_JAR" --output "$OUT/dex" "$OUT/classes"/com/kilitkoruyucu/tv/*.class

# 4) dex'i ekle, hizala, imzala (özel anahtar proje dışında kalır)
cp "$OUT/app-unsigned.apk" "$OUT/app-unaligned.apk"
(cd "$OUT/dex" && zip -q ../app-unaligned.apk classes.dex)
"$BT/zipalign" -f 4 "$OUT/app-unaligned.apk" "$OUT/app-aligned.apk"
"$BT/apksigner" sign --ks "$TVCARE_KEYSTORE" --ks-pass env:TVCARE_KEYSTORE_PASSWORD --key-pass env:TVCARE_KEYSTORE_PASSWORD \
    --ks-key-alias "${TVCARE_KEY_ALIAS:-kk}" --out kilit-koruyucu.apk "$OUT/app-aligned.apk"
"$BT/apksigner" verify kilit-koruyucu.apk
echo "APK hazır: $(pwd)/kilit-koruyucu.apk ($(wc -c < kilit-koruyucu.apk | tr -d ' ') bayt)"
