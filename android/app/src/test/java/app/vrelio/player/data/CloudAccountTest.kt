package app.vrelio.player.data

import android.content.SharedPreferences
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

private class InMemorySharedPreferences : SharedPreferences {
    private val store = linkedMapOf<String, Any?>()

    override fun getAll(): MutableMap<String, *> = LinkedHashMap(store)
    override fun getString(key: String?, defValue: String?): String? = store[key] as? String ?: defValue
    @Suppress("UNCHECKED_CAST")
    override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? =
        (store[key] as? Set<String>)?.toMutableSet() ?: defValues
    override fun getInt(key: String?, defValue: Int): Int = store[key] as? Int ?: defValue
    override fun getLong(key: String?, defValue: Long): Long = store[key] as? Long ?: defValue
    override fun getFloat(key: String?, defValue: Float): Float = store[key] as? Float ?: defValue
    override fun getBoolean(key: String?, defValue: Boolean): Boolean = store[key] as? Boolean ?: defValue
    override fun contains(key: String?): Boolean = store.containsKey(key)
    override fun registerOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}
    override fun unregisterOnSharedPreferenceChangeListener(listener: SharedPreferences.OnSharedPreferenceChangeListener?) {}

    override fun edit(): SharedPreferences.Editor = object : SharedPreferences.Editor {
        private val pending = linkedMapOf<String, Any?>()
        private val removals = linkedSetOf<String>()
        private var clearAll = false

        override fun putString(key: String?, value: String?) = apply { if (key != null) pending[key] = value }
        override fun putStringSet(key: String?, values: MutableSet<String>?) = apply { if (key != null) pending[key] = values?.toSet() }
        override fun putInt(key: String?, value: Int) = apply { if (key != null) pending[key] = value }
        override fun putLong(key: String?, value: Long) = apply { if (key != null) pending[key] = value }
        override fun putFloat(key: String?, value: Float) = apply { if (key != null) pending[key] = value }
        override fun putBoolean(key: String?, value: Boolean) = apply { if (key != null) pending[key] = value }
        override fun remove(key: String?) = apply { if (key != null) removals.add(key) }
        override fun clear() = apply { clearAll = true }
        override fun commit(): Boolean { apply(); return true }
        override fun apply() {
            if (clearAll) store.clear()
            removals.forEach { store.remove(it) }
            pending.forEach { (k, v) -> if (v == null) store.remove(k) else store[k] = v }
        }
    }
}

class CloudAccountTest {
    @Test
    fun normalizesValidHttpsAndHttpUrls() {
        assertEquals("https://vrelio.app", CloudUrlValidator.normalize("vrelio.app/"))
        assertEquals("http://127.0.0.1:8899", CloudUrlValidator.normalize("http://127.0.0.1:8899/"))
    }

    @Test(expected = IptvException::class)
    fun rejectsEmptyOrCredentialEmbeddedUrls() {
        CloudUrlValidator.normalize("https://user:pass@vrelio.app")
    }

    @Test
    fun registerLoginUnverifiedAndVerifyEmailActivatesThreeDayProTrial() = runBlocking {
        MockWebServer().use { server ->
            server.start()
            val base = server.url("").toString().trimEnd('/')
            val client = CloudClient(InMemorySharedPreferences())

            // 1. Register returns 201 without token (verificationRequired = true)
            server.enqueue(
                MockResponse().setResponseCode(201).setBody(
                    JSONObject()
                        .put("ok", true)
                        .put("verificationRequired", true)
                        .put("emailVerified", false)
                        .put("deliveryMode", "outbox")
                        .put("user", JSONObject().put("id", "usr_1").put("email", "ali@vrelio.app").put("displayName", "Ali").put("emailVerified", false).put("plan", "normal"))
                        .toString(),
                ),
            )
            val regState = client.register(base, "Ali@Vrelio.app", "Secret123!", "Ali")
            assertFalse(regState.signedIn)
            assertFalse(regState.emailVerified)
            assertEquals("ali@vrelio.app", regState.pendingVerificationEmail)
            val regReq = server.takeRequest()
            assertEquals("/api/v1/auth/register", regReq.path)

            // 2. Unverified login throws CloudApiException(EMAIL_NOT_VERIFIED)
            server.enqueue(
                MockResponse().setResponseCode(403).setBody(
                    JSONObject()
                        .put("error", "E-posta doğrulaması gerekli.")
                        .put("code", "EMAIL_NOT_VERIFIED")
                        .put("verificationRequired", true)
                        .put("email", "ali@vrelio.app")
                        .toString(),
                ),
            )
            try {
                client.login(base, "ali@vrelio.app", "Secret123!")
                fail("Expected EMAIL_NOT_VERIFIED")
            } catch (ex: CloudApiException) {
                assertEquals("EMAIL_NOT_VERIFIED", ex.code)
                assertEquals(403, ex.httpStatus)
                assertEquals("ali@vrelio.app", ex.email)
            }
            server.takeRequest()

            // 3. Resend verification
            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true,"deliveryMode":"outbox"}"""))
            assertEquals("outbox", client.resendVerification(base, "ali@vrelio.app"))
            assertEquals("/api/v1/auth/resend-verification", server.takeRequest().path)

            // 4. Verify email issues token, activates 3-day Pro trial, and registers device
            val proTrialUser = JSONObject()
                .put("id", "usr_1")
                .put("email", "ali@vrelio.app")
                .put("displayName", "Ali")
                .put("emailVerified", true)
                .put("plan", "pro")
                .put("effectivePlan", "pro")
                .put("isPro", true)
                .put("trialActive", true)
                .put("trialStartedAt", "2026-11-19T00:00:00Z")
                .put("trialEndsAt", "2026-11-22T00:00:00Z")
                .put("expiresAt", "2026-11-22T00:00:00Z")
                .put("maxDevices", 5)
                .put("features", JSONObject().put("cloudSync", true).put("unlimitedProfiles", true).put("maxDevices", 5))
            server.enqueue(
                MockResponse().setResponseCode(200).setBody(
                    JSONObject()
                        .put("ok", true)
                        .put("token", "jwt-token-1")
                        .put("trialActivated", true)
                        .put("user", proTrialUser)
                        .toString(),
                ),
            )
            server.enqueue(
                MockResponse().setResponseCode(200).setBody(
                    JSONObject().put(
                        "devices",
                        JSONArray().put(
                            JSONObject().put("id", "and_123").put("name", "Pixel Test").put("platform", "android").put("lastSeenAt", "2026-11-19T00:01:00Z"),
                        ),
                    ).toString(),
                ),
            )
            val (verifiedState, trialActivated) = client.verifyEmail(base, "ali@vrelio.app", "123456")
            assertTrue(trialActivated)
            assertTrue(verifiedState.signedIn)
            assertTrue(verifiedState.emailVerified)
            assertTrue(verifiedState.isPro)
            assertTrue(verifiedState.trialActive)
            assertEquals(5, verifiedState.maxDevices)
            assertEquals(1, verifiedState.devices.size)
            assertEquals("and_123", verifiedState.devices.first().id)
            assertEquals("/api/v1/auth/verify-email", server.takeRequest().path)
            assertEquals("/api/v1/devices/register", server.takeRequest().path)
        }
    }

    @Test
    fun passwordResetRedeemAndDeviceRemovalWorkAgainstApi() = runBlocking {
        MockWebServer().use { server ->
            server.start()
            val base = server.url("").toString().trimEnd('/')
            val client = CloudClient(InMemorySharedPreferences())

            // Forgot -> Verify Reset Code -> Reset Password
            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true,"deliveryMode":"outbox","message":"Kod gönderildi."}"""))
            assertEquals("Kod gönderildi.", client.forgotPassword(base, "ali@vrelio.app"))
            assertEquals("/api/v1/auth/forgot-password", server.takeRequest().path)

            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true,"valid":true}"""))
            assertTrue(client.verifyResetCode(base, "ali@vrelio.app", "654321"))
            assertEquals("/api/v1/auth/verify-reset-code", server.takeRequest().path)

            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true}"""))
            client.resetPassword(base, "ali@vrelio.app", "654321", "NewSecret99!")
            assertEquals("/api/v1/auth/reset-password", server.takeRequest().path)

            // Login as Normal user
            val normalUser = JSONObject()
                .put("id", "usr_1")
                .put("email", "ali@vrelio.app")
                .put("displayName", "Ali")
                .put("emailVerified", true)
                .put("plan", "normal")
                .put("effectivePlan", "normal")
                .put("isPro", false)
                .put("trialActive", false)
                .put("maxDevices", 1)
                .put("devices", JSONArray().put(JSONObject().put("id", "dev_1").put("name", "Eski Telefon").put("platform", "android")))
            server.enqueue(MockResponse().setResponseCode(200).setBody(JSONObject().put("ok", true).put("token", "tok2").put("user", normalUser).toString()))
            server.enqueue(MockResponse().setResponseCode(403).setBody("""{"error":"Limit doldu","code":"DEVICE_LIMIT_REACHED"}"""))
            val loggedIn = client.login(base, "ali@vrelio.app", "NewSecret99!")
            assertFalse(loggedIn.isPro)
            assertEquals(1, loggedIn.maxDevices)
            assertEquals(1, loggedIn.devices.size)
            assertEquals("/api/v1/auth/login", server.takeRequest().path)
            assertEquals("/api/v1/devices/register", server.takeRequest().path)

            // Self-service device removal
            server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true,"devices":[]}"""))
            val afterRm = client.removeDevice("dev_1")
            assertTrue(afterRm.devices.isEmpty())
            val delReq = server.takeRequest()
            assertEquals("DELETE", delReq.method)
            assertEquals("/api/v1/devices/dev_1", delReq.path)

            // Redeem VRELIO-* license upgrades Normal -> Pro
            val upgradedUser = JSONObject()
                .put("id", "usr_1")
                .put("email", "ali@vrelio.app")
                .put("displayName", "Ali")
                .put("emailVerified", true)
                .put("plan", "pro")
                .put("effectivePlan", "pro")
                .put("isPro", true)
                .put("trialActive", false)
                .put("maxDevices", 5)
            server.enqueue(MockResponse().setResponseCode(200).setBody(JSONObject().put("ok", true).put("user", upgradedUser).toString()))
            val upgraded = client.redeemLicense("VRELIO-ABCD-EFGH-IJKL")
            assertTrue(upgraded.isPro)
            assertEquals("pro", upgraded.effectivePlan)
            assertEquals(5, upgraded.maxDevices)
            assertEquals("/api/v1/licenses/redeem", server.takeRequest().path)
        }
    }
}
