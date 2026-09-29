package com.kilitkoruyucu.tv;

import android.content.Context;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

/** Uygulamaya özel ADB anahtarı: ilk çalıştırmada üretilir, TV bir kez onaylar, sonra hep aynısı kullanılır. */
final class Keys {
    private Keys() {
    }

    static synchronized KeyPair loadOrCreate(Context context) throws GeneralSecurityException, IOException {
        File privateFile = new File(context.getFilesDir(), "adbkey.pk8");
        File publicFile = new File(context.getFilesDir(), "adbkey.x509");
        KeyFactory factory = KeyFactory.getInstance("RSA");
        if (privateFile.exists() && publicFile.exists()) {
            return new KeyPair(
                    factory.generatePublic(new X509EncodedKeySpec(Files.readAllBytes(publicFile.toPath()))),
                    factory.generatePrivate(new PKCS8EncodedKeySpec(Files.readAllBytes(privateFile.toPath()))));
        }
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();
        Files.write(privateFile.toPath(), pair.getPrivate().getEncoded());
        Files.write(publicFile.toPath(), pair.getPublic().getEncoded());
        return pair;
    }
}
