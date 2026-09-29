package com.kilitkoruyucu.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Her açılışta bekçiyi yeniden başlatır (bekçi yalnızca bir sonraki açılışa kadar yaşar). */
public final class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            context.startForegroundService(new Intent(context, GuardService.class));
        }
    }
}
