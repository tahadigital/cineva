package app.mavie.player.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal data class SavedAccount(val settings: ConnectionSettings, val info: AccountInfo)

internal interface AccountStore {
    fun load(): SavedAccount?
    fun save(account: SavedAccount)
    fun clear()
}

/** The encryption key cannot be exported from Android's app-specific Keystore. */
internal class CredentialStore(context: Context) : AccountStore {
    private val preferences = context.getSharedPreferences("mavie_private_connection", Context.MODE_PRIVATE)
    private val alias = "mavie.connection.v1"

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(
                KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build()
            )
        }.generateKey()
    }

    override fun save(account: SavedAccount) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val plain = JSONObject()
            .put("host", account.settings.host)
            .put("username", account.settings.username)
            .put("password", account.settings.password)
            .put("sourceType", account.settings.sourceType.key)
            .put("m3uUrl", account.settings.m3uUrl)
            .put("epgUrl", account.settings.epgUrl)
            .put("id", account.info.id)
            .put("name", account.info.name)
            .put("status", account.info.status)
            .put("expiresAt", account.info.expiresAt ?: JSONObject.NULL)
            .put("maxConnections", account.info.maxConnections)
            .toString()
            .toByteArray(Charsets.UTF_8)
        val encrypted = cipher.doFinal(plain)
        plain.fill(0)
        val saved = preferences.edit()
            .putString("iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("payload", Base64.encodeToString(encrypted, Base64.NO_WRAP)).commit()
        if (!saved) throw IptvException("Bağlantı bu cihazda güvenli biçimde kaydedilemedi.")
    }

    override fun load(): SavedAccount? {
        val iv = preferences.getString("iv", null) ?: return null
        val payload = preferences.getString("payload", null) ?: return null
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
            }
            val plain = cipher.doFinal(Base64.decode(payload, Base64.NO_WRAP))
            val data = JSONObject(plain.toString(Charsets.UTF_8))
            plain.fill(0)
            val sourceType = SourceMode.fromKey(data.optString("sourceType", "xtream"))
            val epgUrl = data.optString("epgUrl")
            val settings = ConnectionSettings(
                host = data.optString("host"),
                username = data.optString("username"),
                password = data.optString("password"),
                sourceType = sourceType,
                m3uUrl = data.optString("m3uUrl"),
                epgUrl = epgUrl,
            )
            SavedAccount(
                settings,
                AccountInfo(
                    id = data.getString("id"),
                    username = settings.username,
                    host = settings.host,
                    name = data.optString("name", "Kişisel Kütüphane"),
                    status = data.optString("status", "Active"),
                    expiresAt = data.optLong("expiresAt").takeIf { it > 0 },
                    maxConnections = data.optInt("maxConnections", 1),
                    sourceType = sourceType,
                    epgUrl = epgUrl,
                ),
            )
        } catch (_: Exception) {
            null
        }
    }

    override fun clear() {
        preferences.edit().clear().commit()
    }
}
