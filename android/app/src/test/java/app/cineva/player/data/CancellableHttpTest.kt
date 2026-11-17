package app.cineva.player.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class CancellableHttpTest {
    @Test(timeout = 10_000) fun cancellingWhileAwaitingHeadersStopsTheCall() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val call = OkHttpClient().newCall(Request.Builder().url(server.url("/headers")).build())
            val job = launch(Dispatchers.IO) { call.readCancellable { it.body!!.string() } }
            assertNotNull(server.takeRequest(3, TimeUnit.SECONDS))
            withTimeout(2_000) { job.cancelAndJoin() }
            assertTrue(call.isCanceled())
        }
    }

    @Test(timeout = 10_000) fun cancellingWhileReadingAnIncompleteBodyStopsTheCall() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("{").setHeader("Content-Length", 100_000))
            val reading = CountDownLatch(1)
            val call = OkHttpClient().newCall(Request.Builder().url(server.url("/body")).build())
            val job = launch(Dispatchers.IO) {
                call.readCancellable { response ->
                    reading.countDown()
                    response.body!!.string()
                }
            }
            assertTrue(reading.await(3, TimeUnit.SECONDS))
            withTimeout(2_000) { job.cancelAndJoin() }
            assertTrue(call.isCanceled())
        }
    }

    @Test(timeout = 10_000) fun successfulReadClosesTheResponseEvenWithoutConsumingItsBody() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("response"))
            var captured: Response? = null
            val result = OkHttpClient().newCall(Request.Builder().url(server.url("/success")).build())
                .readCancellable { response -> captured = response; response.code }
            assertEquals(200, result)
            try {
                captured!!.body!!.source().readByte()
                fail("The response body must be closed after parsing.")
            } catch (_: IllegalStateException) {
                // Okio rejects reads from the closed response source.
            }
        }
    }
}
