package app.clipo.shared

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import app.cash.sqldelight.driver.android.AndroidSqliteDriver
import app.clipo.shared.auth.TokenStore
import app.clipo.shared.db.ClipoDatabase
import io.ktor.client.engine.okhttp.OkHttp
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

private class AndroidTokenStore(
    context: Context,
) : TokenStore {
    private val preferences = context.getSharedPreferences("clipo_session", Context.MODE_PRIVATE)
    private val alias = "clipo_refresh_v1"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator
            .getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply {
                init(
                    KeyGenParameterSpec
                        .Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .build(),
                )
            }.generateKey()
    }

    override fun read(): String? {
        val encoded = preferences.getString("refresh", null) ?: return null
        return try {
            val data = Base64.decode(encoded, Base64.NO_WRAP)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, data.copyOfRange(0, 12)))
            cipher.doFinal(data.copyOfRange(12, data.size)).toString(Charsets.UTF_8)
        } catch (_: Exception) {
            clear()
            null
        }
    }

    override fun write(value: String): Boolean {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val encrypted = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        return preferences.edit().putString("refresh", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit()
    }

    override fun clear(): Boolean = preferences.edit().clear().commit()
}

fun createAndroidClient(context: Context): ClipoClient {
    val driver = AndroidSqliteDriver(ClipoDatabase.Schema, context.applicationContext, "clipo.db")
    driver.execute(null, "PRAGMA foreign_keys = ON", 0)
    return ClipoClient(driver, OkHttp.create(), AndroidTokenStore(context.applicationContext))
}
