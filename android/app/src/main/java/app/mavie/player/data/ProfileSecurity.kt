package app.mavie.player.data

import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/**
 * Pure-Kotlin security & parental filter helpers shared between runtime and JVM unit tests.
 */
object AdultContentFilter {
    private val pattern = Regex(
        "(?:^|\\W)(?:\\+18|18\\+)(?=$|\\W)|\\b(?:adult|yetişkin|yetiskin|erotic|erotik|xxx|porn|korku|horror)\\b",
        RegexOption.IGNORE_CASE,
    )

    fun isAdult(name: String, categoryName: String): Boolean =
        pattern.containsMatchIn(name) || pattern.containsMatchIn(categoryName)
}

object ProfilePinHasher {
    private const val ITERATIONS = 100_000
    private const val KEY_LENGTH_BITS = 256
    private val rng = SecureRandom()

    fun hash(pin: String): String {
        val clean = pin.trim()
        if (clean.isEmpty()) return ""
        if (!clean.matches(Regex("^\\d{4,8}$"))) {
            throw IptvException("Profil PIN kodu 4-8 rakamdan oluşmalıdır.", MavieErrorCode.INVALID_INPUT)
        }
        val salt = ByteArray(16).also(rng::nextBytes)
        val digest = pbkdf2(clean, salt)
        return salt.toHex() + ":" + digest.toHex()
    }

    fun verify(pin: String, stored: String): Boolean {
        if (stored.isBlank()) return true
        val parts = stored.split(':', limit = 2)
        if (parts.size != 2) return false
        val salt = parts[0].fromHex() ?: return false
        val expected = parts[1].fromHex() ?: return false
        val actual = pbkdf2(pin.trim(), salt)
        return MessageDigest.isEqual(actual, expected)
    }

    private fun pbkdf2(pin: String, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(pin.toCharArray(), salt, ITERATIONS, KEY_LENGTH_BITS)
        return try {
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
        }
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun String.fromHex(): ByteArray? {
        if (length % 2 != 0 || isEmpty()) return null
        return runCatching {
            ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        }.getOrNull()
    }
}
