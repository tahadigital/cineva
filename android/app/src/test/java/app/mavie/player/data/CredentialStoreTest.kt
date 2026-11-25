package app.mavie.player.data

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.util.Base64
import javax.crypto.AEADBadTagException

class CredentialStoreTest {
    @Test
    fun loadFromReturnsEmptyWhenBothIvAndPayloadAreNull() {
        var cleared = false
        val result = CredentialStore.loadFrom(
            iv = null,
            payload = null,
            decrypt = { _, _ -> fail("decrypt must not be called") as ByteArray },
            clearCorrupt = { cleared = true },
        )
        assertEquals(CredentialLoadResult.Empty, result)
        assertFalse(cleared)
    }

    @Test
    fun loadFromReturnsLoadedForValidEncryptedJsonWithoutClearing() {
        var cleared = false
        val json = JSONObject()
            .put("host", "https://tv.example.test")
            .put("username", "demo_u")
            .put("password", "demo_p")
            .put("sourceType", "xtream")
            .put("m3uUrl", "")
            .put("epgUrl", "https://epg.example.test/g.xml")
            .put("id", "acc123")
            .put("name", "Test")
            .put("status", "Active")
            .put("expiresAt", 1800000000L)
            .put("maxConnections", 2)
            .toString()
            .toByteArray(Charsets.UTF_8)

        val ivB64 = Base64.getEncoder().encodeToString(byteArrayOf(1, 2, 3, 4))
        val payloadB64 = Base64.getEncoder().encodeToString(byteArrayOf(5, 6, 7, 8))
        val result = CredentialStore.loadFrom(
            iv = ivB64,
            payload = payloadB64,
            decrypt = { ivBytes, payloadBytes ->
                assertArrayEquals(byteArrayOf(1, 2, 3, 4), ivBytes)
                assertArrayEquals(byteArrayOf(5, 6, 7, 8), payloadBytes)
                json
            },
            clearCorrupt = { cleared = true },
        )

        assertTrue(result is CredentialLoadResult.Loaded)
        val loaded = (result as CredentialLoadResult.Loaded).account
        assertEquals("https://tv.example.test", loaded.settings.host)
        assertEquals("demo_u", loaded.settings.username)
        assertEquals("https://epg.example.test/g.xml", loaded.settings.epgUrl)
        assertEquals("acc123", loaded.info.id)
        assertEquals(2, loaded.info.maxConnections)
        assertFalse(cleared)
    }

    @Test
    fun loadFromReturnsKeystoreErrorAndClearsCorruptOnMissingHalfDecryptFailureOrBadJson() {
        // 1. Half-written preferences (iv present, payload blank)
        var clearedHalf = false
        val halfResult = CredentialStore.loadFrom(
            iv = "AAAA",
            payload = "  ",
            decrypt = { _, _ -> fail("decrypt must not run") as ByteArray },
            clearCorrupt = { clearedHalf = true },
        )
        assertTrue(halfResult is CredentialLoadResult.Failed)
        assertEquals(MavieErrorCode.KEYSTORE_ERROR, (halfResult as CredentialLoadResult.Failed).error.code)
        assertTrue(clearedHalf)

        // 2. Keystore AEADBadTagException
        var clearedTag = false
        val tagResult = CredentialStore.loadFrom(
            iv = Base64.getEncoder().encodeToString(byteArrayOf(1, 2)),
            payload = Base64.getEncoder().encodeToString(byteArrayOf(3, 4)),
            decrypt = { _, _ -> throw AEADBadTagException("Tag mismatch") },
            clearCorrupt = { clearedTag = true },
        )
        assertTrue(tagResult is CredentialLoadResult.Failed)
        assertEquals(MavieErrorCode.KEYSTORE_ERROR, (tagResult as CredentialLoadResult.Failed).error.code)
        assertTrue(clearedTag)

        // 3. Decrypted non-JSON payload
        var clearedJson = false
        val badJsonResult = CredentialStore.loadFrom(
            iv = Base64.getEncoder().encodeToString(byteArrayOf(1, 2)),
            payload = Base64.getEncoder().encodeToString(byteArrayOf(3, 4)),
            decrypt = { _, _ -> "not-json".toByteArray(Charsets.UTF_8) },
            clearCorrupt = { clearedJson = true },
        )
        assertTrue(badJsonResult is CredentialLoadResult.Failed)
        assertEquals(MavieErrorCode.KEYSTORE_ERROR, (badJsonResult as CredentialLoadResult.Failed).error.code)
        assertTrue(clearedJson)
    }
}
