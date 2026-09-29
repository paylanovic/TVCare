package com.kilitkoruyucu.tv;

import android.util.Base64;

import java.io.ByteArrayOutputStream;
import java.io.Closeable;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.math.BigInteger;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.PrivateKey;
import java.security.interfaces.RSAPublicKey;

import javax.crypto.Cipher;

/**
 * TV'nin kendi adbd'sine (127.0.0.1:5555) bağlanan en küçük ADB istemcisi.
 * Protokol: system/core/adb/protocol.txt. Yalnızca CNXN, AUTH ve tek yönlü "shell:" akışı.
 */
final class Adb implements Closeable {
    private static final int A_CNXN = 0x4e584e43;
    private static final int A_AUTH = 0x48545541;
    private static final int A_OPEN = 0x4e45504f;
    private static final int A_OKAY = 0x59414b4f;
    private static final int A_CLSE = 0x45534c43;
    private static final int A_WRTE = 0x45545257;

    private static final int AUTH_TOKEN = 1;
    private static final int AUTH_SIGNATURE = 2;
    private static final int AUTH_RSAPUBLICKEY = 3;

    private static final int VERSION = 0x01000000;
    private static final int MAX_DATA = 4096;
    private static final int KEY_BYTES = 256; // adbd yalnızca 2048 bit RSA kabul eder

    // adbd, 20 baytlık token'ı SHA-1 özeti gibi imzalatır: PKCS#1 v1.5 DigestInfo(SHA-1) öneki
    private static final byte[] SHA1_PREFIX = {
            0x30, 0x21, 0x30, 0x09, 0x06, 0x05, 0x2b, 0x0e, 0x03, 0x02, 0x1a, 0x05, 0x00, 0x04, 0x14};

    private final Socket socket;
    private final DataInputStream in;
    private final OutputStream out;
    private int nextLocalId = 1;

    private static final class Msg {
        int cmd;
        int arg0;
        int arg1;
        byte[] data;
    }

    private Adb(Socket socket) throws IOException {
        this.socket = socket;
        this.in = new DataInputStream(socket.getInputStream());
        this.out = socket.getOutputStream();
    }

    /**
     * Bağlanır ve kimlik doğrular. Anahtar TV'de henüz tanınmıyorsa ekranda izin penceresi çıkar;
     * kullanıcı onaylayana kadar en fazla approvalTimeoutMs beklenir.
     */
    static Adb connect(String host, int port, KeyPair key, int approvalTimeoutMs)
            throws IOException, GeneralSecurityException {
        Socket s = new Socket();
        s.connect(new InetSocketAddress(host, port), 3000);
        s.setSoTimeout(10000);
        Adb adb = new Adb(s);
        try {
            adb.send(A_CNXN, VERSION, MAX_DATA, "host::\0".getBytes(StandardCharsets.US_ASCII));
            boolean signed = false;
            boolean publicKeySent = false;
            while (true) {
                Msg m = adb.read();
                if (m.cmd == A_CNXN) {
                    s.setSoTimeout(10000);
                    return adb;
                }
                if (m.cmd != A_AUTH || m.arg0 != AUTH_TOKEN || publicKeySent) {
                    throw new IOException("ADB kimlik doğrulaması reddedildi");
                }
                if (!signed) {
                    adb.send(A_AUTH, AUTH_SIGNATURE, 0, sign(key.getPrivate(), m.data));
                    signed = true;
                } else {
                    // İmza tanınmadı: açık anahtarı gönder, TV ekranındaki onayı bekle
                    s.setSoTimeout(approvalTimeoutMs);
                    adb.send(A_AUTH, AUTH_RSAPUBLICKEY, 0, publicKeyPayload((RSAPublicKey) key.getPublic()));
                    publicKeySent = true;
                }
            }
        } catch (IOException | GeneralSecurityException | RuntimeException e) {
            adb.close();
            throw e;
        }
    }

    /** "shell:" servisinde komutu çalıştırır ve komut bitene kadar çıktısını toplar. */
    String shell(String command, int timeoutMs) throws IOException {
        int localId = nextLocalId++;
        socket.setSoTimeout(timeoutMs);
        send(A_OPEN, localId, 0, ("shell:" + command + "\0").getBytes(StandardCharsets.UTF_8));
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        while (true) {
            Msg m = read();
            if (m.arg1 != localId) {
                continue; // başka akışa ait (olmaması gerekir)
            }
            if (m.cmd == A_WRTE) {
                output.write(m.data);
                send(A_OKAY, localId, m.arg0, null);
            } else if (m.cmd == A_CLSE) {
                return new String(output.toByteArray(), StandardCharsets.UTF_8);
            }
        }
    }

    @Override
    public void close() {
        try {
            socket.close();
        } catch (IOException ignored) {
            // kapatırken hata önemsiz
        }
    }

    private void send(int cmd, int arg0, int arg1, byte[] data) throws IOException {
        int length = data == null ? 0 : data.length;
        int checksum = 0;
        for (int i = 0; i < length; i++) {
            checksum += data[i] & 0xff;
        }
        ByteBuffer header = ByteBuffer.allocate(24).order(ByteOrder.LITTLE_ENDIAN);
        header.putInt(cmd).putInt(arg0).putInt(arg1).putInt(length).putInt(checksum).putInt(~cmd);
        out.write(header.array());
        if (length > 0) {
            out.write(data);
        }
        out.flush();
    }

    private Msg read() throws IOException {
        byte[] header = new byte[24];
        in.readFully(header);
        ByteBuffer b = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN);
        Msg m = new Msg();
        m.cmd = b.getInt();
        m.arg0 = b.getInt();
        m.arg1 = b.getInt();
        int length = b.getInt();
        if (length < 0 || length > 1024 * 1024) {
            throw new IOException("geçersiz ADB paketi");
        }
        m.data = new byte[length];
        in.readFully(m.data);
        return m;
    }

    /** PKCS#1 v1.5 tip 1 dolgusunu elle kurup ham RSA ile imzalar (Android'de en taşınabilir yol). */
    private static byte[] sign(PrivateKey key, byte[] token) throws GeneralSecurityException {
        byte[] block = new byte[KEY_BYTES];
        int payload = SHA1_PREFIX.length + token.length;
        block[0] = 0x00;
        block[1] = 0x01;
        for (int i = 2; i < KEY_BYTES - payload - 1; i++) {
            block[i] = (byte) 0xff;
        }
        block[KEY_BYTES - payload - 1] = 0x00;
        System.arraycopy(SHA1_PREFIX, 0, block, KEY_BYTES - payload, SHA1_PREFIX.length);
        System.arraycopy(token, 0, block, KEY_BYTES - token.length, token.length);
        Cipher cipher = Cipher.getInstance("RSA/ECB/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        return cipher.doFinal(block);
    }

    /** adbd'nin beklediği açık anahtar biçimi (android_pubkey_encode) + " kullanıcı@makine\0". */
    private static byte[] publicKeyPayload(RSAPublicKey pub) {
        BigInteger n = pub.getModulus();
        BigInteger r32 = BigInteger.ONE.shiftLeft(32);
        BigInteger n0inv = r32.subtract(n.mod(r32).modInverse(r32)); // -1 / n[0] mod 2^32
        BigInteger rr = BigInteger.ONE.shiftLeft(KEY_BYTES * 8).modPow(BigInteger.valueOf(2), n); // R^2 mod n
        ByteBuffer b = ByteBuffer.allocate(4 + 4 + KEY_BYTES + KEY_BYTES + 4).order(ByteOrder.LITTLE_ENDIAN);
        b.putInt(KEY_BYTES / 4);
        b.putInt(n0inv.intValue());
        b.put(littleEndian(n));
        b.put(littleEndian(rr));
        b.putInt(pub.getPublicExponent().intValue());
        String text = Base64.encodeToString(b.array(), Base64.NO_WRAP) + " kilitkoruyucu@tv\0";
        return text.getBytes(StandardCharsets.US_ASCII);
    }

    private static byte[] littleEndian(BigInteger value) {
        byte[] big = value.toByteArray();
        byte[] little = new byte[KEY_BYTES];
        for (int i = 0; i < KEY_BYTES && i < big.length; i++) {
            little[i] = big[big.length - 1 - i];
        }
        return little;
    }
}
