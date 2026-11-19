package app.vrelio.player

import android.graphics.Bitmap
import android.view.WindowManager
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.vrelio.player.data.VrelioRepository
import app.vrelio.player.sports.Istanbul
import app.vrelio.player.sports.SportsChannels
import app.vrelio.player.sports.SportsGuide
import kotlinx.coroutines.runBlocking
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.time.LocalDate

/** Opt-in verification of the public guide and existing personal IPTV account on Android. */
@RunWith(AndroidJUnit4::class)
class SportsAppProofTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test fun opensRealBroadcastFromGuide() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        assumeTrue("Public sports and real-provider QA requires the sportsProof instrumentation argument.",
            InstrumentationRegistry.getArguments().getString("sportsProof") == "true")
        val repository = VrelioRepository(context)
        assumeTrue("A test account must already be provisioned.", repository.account.value != null)
        rule.runOnUiThread { rule.activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
        val epgUrl = InstrumentationRegistry.getArguments().getString("epgUrl").orEmpty()
        val (events, keys) = runBlocking {
            SportsGuide.load(LocalDate.now(Istanbul), force = false, epgUrl = epgUrl).events to
                repository.liveChannelNames().map { (_, name) -> SportsChannels.key(name) }.toSet()
        }
        val eligible = events.filter { event -> event.channels.any { SportsChannels.key(it) in keys } }
        assumeTrue("The current guide contains no channel from the test account.", eligible.isNotEmpty())
        val event = eligible.firstOrNull { it.league == "UEFA Şampiyonlar Ligi" && it.title.contains("Galatasaray") }
            ?: eligible.first()
        val channel = event.channels.first { SportsChannels.key(it) in keys }
        val play = hasContentDescription("${event.title} · $channel kanalını aç")
        val list = rule.onNodeWithTag("sportsGuide")
        val directory = File(context.getExternalFilesDir(null), "proofs").apply { mkdirs() }
        rule.waitUntil(30_000) { rule.onAllNodesWithText("Rehber").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithText("Rehber").performClick()
        rule.waitUntil(25_000) { rule.onAllNodes(hasSetTextAction()).fetchSemanticsNodes().isNotEmpty() }
        rule.onNode(hasSetTextAction()).performTextInput(event.title)
        rule.waitUntil(35_000) { runCatching { list.performScrollToNode(play) }.isSuccess }
        list.assertIsDisplayed()
        rule.onAllNodes(play).onFirst().assertIsDisplayed()
        capture(directory)
        rule.onAllNodes(play).onFirst().assertIsEnabled().performClick()
        rule.waitUntil(45_000) { rule.onAllNodesWithContentDescription("Duraklat").fetchSemanticsNodes().isNotEmpty() }
        rule.onNodeWithContentDescription("Oynatıcıdan çık").performClick()
        rule.waitUntil(20_000) { rule.onAllNodesWithText("Canlı Yayın & EPG Rehberi").fetchSemanticsNodes().isNotEmpty() }
        File(directory, "sports-app-proof.txt").writeText("${events.size} listings; $channel opened in the native player.")
    }

    private fun capture(directory: File) {
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        try {
            File(directory, "Android-sports-cinema.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 95, it) }
        } finally {
            image.recycle()
        }
    }
}
