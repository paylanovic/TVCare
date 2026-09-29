package com.kilitkoruyucu.tv;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.os.SystemClock;
import java.security.KeyPair;
import java.util.concurrent.atomic.AtomicBoolean;

/** Status checks never enable the guard; only the explicit start action does. */
public final class GuardService extends Service {
    static final String PREFS = "durum";
    static final String CHECK = "com.kilitkoruyucu.tv.CHECK";
    static final String ENABLE = "com.kilitkoruyucu.tv.START";
    private static final String CHANNEL = "koruyucu";
    private static final String DIR = "/data/local/tmp/";
    private static final String SCRIPT = DIR + "kilit-koruyucu.sh";
    private static final AtomicBoolean RUNNING = new AtomicBoolean(false);
    private static final AtomicBoolean ENABLE_PENDING = new AtomicBoolean(false);

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        boolean enable = intent != null && ENABLE.equals(intent.getAction());
        boolean check = intent != null && CHECK.equals(intent.getAction());
        if (enable) ENABLE_PENDING.set(true);
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "TVCare Koruyucu", NotificationManager.IMPORTANCE_LOW));
        startForeground(1, new Notification.Builder(this, CHANNEL).setSmallIcon(R.drawable.banner)
                .setContentTitle("TVCare Koruyucu").setContentText("Bekçi durumu denetleniyor").build());
        if (!RUNNING.compareAndSet(false, true)) return START_NOT_STICKY;
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("busy", true)
                .putString("durum", "Güncel durum kontrol ediliyor…").apply();
        new Thread(() -> {
            String result;
            try {
                result = operate(check && !enable, ENABLE_PENDING.getAndSet(false));
                if (ENABLE_PENDING.getAndSet(false)) result = operate(false, true);
            } catch (Exception e) {
                result = "Durum doğrulanamadı: " + e.getMessage();
            }
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString("durum", result)
                    .putBoolean("busy", false).putLong("zaman", System.currentTimeMillis()).apply();
            RUNNING.set(false);
            stopForeground(true);
            stopSelf();
        }, "tvcare-guard").start();
        return START_NOT_STICKY;
    }

    private String operate(boolean checkOnly, boolean enable) {
        long deadline = SystemClock.elapsedRealtime() + (checkOnly ? 15_000 : 180_000);
        String last = "Bekçi süreci bulunamadı";
        while (SystemClock.elapsedRealtime() < deadline) {
            try {
                KeyPair key = Keys.loadOrCreate(this);
                try (Adb adb = Adb.connect("127.0.0.1", 5555, key, checkOnly ? 8000 : 30_000)) {
                    if (!checkOnly) {
                        // A failed write cannot truncate the installed script.
                        String temp = SCRIPT + ".new";
                        String encoded = temp + ".b64";
                        adb.shell("umask 077; : > " + encoded, 5000);
                        // Keep every shell OPEN command below the legacy 4096-byte ADB limit.
                        for (int offset = 0; offset < Script.B64.length(); offset += 2048) {
                            String chunk = Script.B64.substring(offset, Math.min(offset + 2048, Script.B64.length()));
                            String appended = adb.shell("printf '%s' '" + chunk + "' >> " + encoded + " && echo OK", 5000);
                            if (!appended.trim().equals("OK")) throw new java.io.IOException("Betik aktarımı tamamlanamadı");
                        }
                        String written = adb.shell("umask 077; base64 -d " + encoded + " > " + temp
                                + " && chmod 700 " + temp + " && mv -f " + temp + " " + SCRIPT
                                + " && rm -f " + encoded + " && echo WRITTEN", 15_000);
                        if (!written.contains("WRITTEN")) throw new java.io.IOException("Betik yazılamadı");
                        if (enable) adb.shell("sh " + SCRIPT + " --enable", 5000);
                        adb.shell("setsid nohup sh " + SCRIPT + " > /dev/null 2>&1 < /dev/null &", 5000);
                        SystemClock.sleep(1500);
                    }
                    String current = adb.shell("if [ ! -f " + SCRIPT + " ]; then echo STOPPED; "
                            + "elif head -n 2 " + SCRIPT + " | grep -Fq '# TVCare Guard 1.1.'; then sh "
                            + SCRIPT + " --status; else echo LEGACY; fi", 5000).trim();
                    if (current.equals("LEGACY")) return "Eski bekçi betiği bulundu. Güncel koruma doğrulanamadı.";
                    if (current.startsWith("RUNNING:")) return "Bekçi çalışıyor (PID " + current.substring(8) + ").";
                    if (current.startsWith("STOPPING:")) return "Koruma durduruluyor…";
                    if (current.equals("DISABLED")) return "Koruma devre dışı. Başlat düğmesiyle etkinleştirebilirsiniz.";
                    if (checkOnly) return "Bekçi çalışmıyor. Başlat düğmesini kullanın.";
                    last = "Bekçi süreci başlamadı"; // Retry this too, not only exceptions.
                }
            } catch (Exception e) { last = e.getMessage(); }
            if (checkOnly) break;
            SystemClock.sleep(5000);
        }
        return "Güncel durum doğrulanamadı: " + last
                + "\nADB bağlantısını, TV izin penceresini ve otomatik başlatma iznini kontrol edin.";
    }
}
