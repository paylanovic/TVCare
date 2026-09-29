package com.kilitkoruyucu.tv;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.format.DateFormat;
import android.util.TypedValue;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Kumandayla kullanılabilen tek ekran: durum ve "başlat / kontrol et" düğmesi. */
public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private long requestedAt;

    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            showStatus();
            handler.postDelayed(this, 2000);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(48);
        root.setPadding(padding, padding, padding, padding);
        root.setBackgroundColor(0xFF1B2A3A);

        root.addView(text("TVCare Koruyucu", 34));
        root.addView(text("TV kapanırken TCL'in CI CAM beklemesinde kilitlenmesini algılar. "
                + "Uyumlu TV kapanış durumunda en az 5 saniye takılırsa kapatma ister. Her açılışta başlatmayı dener.", 18));
        Button start = new Button(this);
        start.setText("Bekçiyi başlat / kontrol et");
        start.setOnClickListener(v -> {
            requestedAt = System.currentTimeMillis();
            showStatus();
            startForegroundService(new Intent(this, GuardService.class).setAction(GuardService.ENABLE));
        });
        root.addView(start);
        status = text("", 18);
        root.addView(status);
        setContentView(root);
        start.requestFocus();
    }

    @Override
    protected void onResume() {
        super.onResume();
        requestedAt = System.currentTimeMillis();
        status.setText("Güncel durum kontrol ediliyor…");
        startForegroundService(new Intent(this, GuardService.class).setAction(GuardService.CHECK));
        handler.post(refresh);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(refresh);
    }

    private void showStatus() {
        SharedPreferences prefs = getSharedPreferences(GuardService.PREFS, MODE_PRIVATE);
        long at = prefs.getLong("zaman", 0);
        if (requestedAt > at || prefs.getBoolean("busy", false)) {
            status.setText("Kontrol ediliyor / başlatılıyor… TV'de izin sorulursa \"Bu bilgisayardan her zaman izin ver\" "
                    + "kutusunu işaretleyip Tamam'a basın.");
        } else if (at == 0) {
            status.setText("Henüz başlatılmadı.");
        } else {
            status.setText(prefs.getString("durum", "") + "\n\n("
                    + "Son kontrol: " + DateFormat.format("dd.MM.yyyy HH:mm:ss", at) + ")");
        }
    }

    private TextView text(String value, int sp) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(0xFFFFFFFF);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        view.setPadding(0, dp(8), 0, dp(8));
        return view;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
