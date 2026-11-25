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

internal sealed interface CredentialLoadResult {
    data object Empty : CredentialLoadResult
    data class Loaded(val account: SavedAccount) : CredentialLoadResult
    data class Failed(val error: IptvException) : CredentialLoadResult
}

internal interface AccountStore {
    fun load(): SavedAccount?
    fun loadResult(): CredentialLoadResult = when (val acc = load()) {
        null -> CredentialLoadResult.Empty
        else -> CredentialLoadResult.Loaded(acc)
    }
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
        val (ivEncoded, payloadEncoded) = try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
            val encrypted = cipher.doFinal(plain)
            Base64.encodeToString(cipher.iv, Base64.NO_WRAP) to Base64.encodeToString(encrypted, Base64.NO_WRAP)
        } catch (err: Exception) {
            throw IptvException("Bağlantı bu cihazda güvenli biçimde kaydedilemedi.", MavieErrorCode.KEYSTORE_ERROR, err)
        } finally {
            plain.fill(0)
        }
        val saved = preferences.edit()
            .putString("iv", ivEncoded)
            .putString("payload", payloadEncoded)
            .commit()
        if (!saved) {
            throw IptvException("Bağlantı bu cihazda güvenli biçimde kaydedilemedi.", MavieErrorCode.STORAGE_ERROR)
        }
    }

    override fun loadResult(): CredentialLoadResult {
        val iv = preferences.getString("iv", null)
        val payload = preferences.getString("payload", null)
        return loadFrom(
            iv = iv,
            payload = payload,
            decodeBase64 = { Base64.decode(it, Base64.NO_WRAP) },
            decrypt = { ivBytes, payloadBytes ->
                val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, ivBytes))
                }
                cipher.doFinal(payloadBytes)
            },
            clearCorrupt = {
                preferences.edit().remove("iv").remove("payload").commit()
            },
        )
    }

    override fun load(): SavedAccount? = (loadResult() as? CredentialLoadResult.Loaded)?.account

    override fun clear() {
        preferences.edit().clear().commit()
    }

    internal companion object {
        fun loadFrom(
            iv: String?,
            payload: String?,
            decodeBase64: (String) -> ByteArray = { java.util.Base64.getDecoder().decode(it) },
            decrypt: (ByteArray, ByteArray) -> ByteArray,
            clearCorrupt: () -> Unit,
        ): CredentialLoadResult {
            if (iv == null && payload == null) return CredentialLoadResult.Empty
            if (iv.isNullOrBlank() || payload.isNullOrBlank()) {
                runCatching { clearCorrupt() }
                return CredentialLoadResult.Failed(
                    IptvException(
                        "Kayıtlı oturum anahtarı okunamadı. Güvenlik nedeniyle yeniden giriş yap.",
                        MavieErrorCode.KEYSTORE_ERROR,
                    )
                )
            }
            return try {
                val plain = decrypt(decodeBase64(iv), decodeBase64(payload))
                try {
                    val data = JSONObject(plain.toString(Charsets.UTF_8))
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
                    CredentialLoadResult.Loaded(
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
                    )
                } finally {
                    plain.fill(0)
                }
            } catch (err: Exception) {
                runCatching { clearCorrupt() }
                CredentialLoadResult.Failed(
                    IptvException(
                        "Kayıtlı oturum anahtarı okunamadı. Güvenlik nedeniyle yeniden giriş yap.",
                        MavieErrorCode.KEYSTORE_ERROR,
                        err,
                    )
                )
            }
        }
    }
}
