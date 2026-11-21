package app.mavie.player.player

import android.graphics.Bitmap
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.mavie.player.MainActivity
import app.mavie.player.ui.MavieTheme
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import okio.Buffer
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.net.InetAddress
import java.io.File
import java.util.concurrent.ConcurrentLinkedQueue

/** Exercises actual LibVLC HTTP range playback and Compose controls using a synthetic video. */
@RunWith(AndroidJUnit4::class)
class EpisodeTransitionTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun oneTimelineCanSeekToTheEndAndTheNextEpisodeCanBeCancelledOrOpened() = withPlayer { requests ->
        val timeline = rule.onNodeWithContentDescription("İçerikte ileri geri sar")
        waitForPlaying()
        rule.onAllNodesWithContentDescription("İçerikte ileri geri sar").assertCountEquals(1)
        timeline.assertIsEnabled().performSemanticsAction(SemanticsActions.SetProgress) { seek -> assertTrue(seek(.82f)) }
        waitForText("Sonraki bölümü oynat")
        captureNextPrompt()
        rule.onNodeWithText("Şimdi değil").performClick()
        rule.onNodeWithText("Sonraki bölümü oynat").assertDoesNotExist()
        assertTrue(requests.none { it == "/episode-2.mp4" })
        timeline.assertIsEnabled().performSemanticsAction(SemanticsActions.SetProgress) { seek -> assertTrue(seek(.2f)) }
        waitForPlaying()
        timeline.performSemanticsAction(SemanticsActions.SetProgress) { seek -> assertTrue(seek(.84f)) }
        waitForText("Sonraki bölümü oynat")
        rule.onNodeWithText("Sonraki bölümü oynat").performClick()
        waitForSecondPlayerTitle()
        rule.waitUntil(15_000) { requests.any { it == "/episode-2.mp4" } }
        rule.onAllNodesWithContentDescription("İçerikte ileri geri sar").assertCountEquals(1)
    }

    @Test fun naturalEndStartsNextEpisodeAfterCountdown() = withPlayer { requests ->
        waitForPlaying()
        waitForText("Sonraki bölümü oynat")
        rule.waitUntil(20_000) { requests.any { it == "/episode-2.mp4" } }
        waitForSecondPlayerTitle()
    }

    private fun waitForText(text: String) = rule.waitUntil(20_000) {
        rule.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
    }

    private fun waitForPlaying() = rule.waitUntil(20_000) {
        rule.onAllNodesWithContentDescription("Duraklat").fetchSemanticsNodes().isNotEmpty()
    }

    private fun waitForSecondPlayerTitle() = rule.waitUntil(20_000) {
        rule.onAllNodes(hasTestTag("player-title") and hasText("İkinci bölüm"), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    }

    private fun captureNextPrompt() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val screenshot = rule.onRoot().captureToImage().asAndroidBitmap()
        val directory = File(instrumentation.targetContext.getExternalFilesDir(null), "proofs").apply { mkdirs() }
        try {
            File(directory, "Android-next-episode.png").outputStream().use { screenshot.compress(Bitmap.CompressFormat.PNG, 100, it) }
        } finally {
            screenshot.recycle()
        }
    }

    private fun withPlayer(test: (ConcurrentLinkedQueue<String>) -> Unit) {
        val fixture = InstrumentationRegistry.getInstrumentation().context.assets.open("episode-qa.mp4").use { it.readBytes() }
        val requests = ConcurrentLinkedQueue<String>()
        MockWebServer().use { server ->
            server.dispatcher = object : Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val path = request.path.orEmpty()
                    if (path !in listOf("/episode-1.mp4", "/episode-2.mp4")) return MockResponse().setResponseCode(404)
                    requests.add(path)
                    val range = request.getHeader("Range")?.let { Regex("bytes=(\\d+)-(\\d*)").matchEntire(it) }
                    val start = range?.groupValues?.get(1)?.toIntOrNull() ?: 0
                    val end = range?.groupValues?.get(2)?.toIntOrNull()?.coerceAtMost(fixture.lastIndex) ?: fixture.lastIndex
                    if (start !in 0..end) return MockResponse().setResponseCode(416)
                    val response = MockResponse().setHeader("Content-Type", "video/mp4").setHeader("Accept-Ranges", "bytes")
                    if (request.method != "HEAD") response.setBody(Buffer().write(fixture, start, end - start + 1))
                    response.setHeader("Content-Length", end - start + 1)
                    return if (range == null) response else response.setResponseCode(206)
                        .setHeader("Content-Range", "bytes $start-$end/${fixture.size}")
                }
            }
            server.start(InetAddress.getByName("127.0.0.1"), 0)
            val serverRoot = "http://127.0.0.1:${server.port}"
            rule.runOnUiThread {
                rule.activity.setContent {
                    MavieTheme {
                        var episode by remember { mutableIntStateOf(1) }
                        PlayerScreen(
                            title = if (episode == 1) "İlk bölüm" else "İkinci bölüm",
                            sourceUrl = "$serverRoot/episode-$episode.mp4",
                            nextEpisode = if (episode == 1) UpNextEpisode("İkinci bölüm", 1, 2, "") else null,
                            onNextEpisode = { episode = 2 },
                            onProgress = { _, _ -> },
                            onBack = {},
                        )
                    }
                }
            }
            try {
                test(requests)
            } finally {
                rule.activityRule.scenario.close()
            }
        }
    }
}
