package app.mavie.player.player

import android.os.Build
import android.os.SystemClock
import android.view.WindowManager
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.LargeTest
import androidx.test.platform.app.InstrumentationRegistry
import app.mavie.player.MainActivity
import app.mavie.player.data.MavieRepository
import app.mavie.player.data.MediaItem
import app.mavie.player.data.MediaKind
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.videolan.libvlc.util.VLCVideoLayout
import java.io.File
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs

/**
 * Explicit opt-in only. Normal connected tests never contact a real provider.
 * The operator must place filesDir/qa-account.json using run-as, then select
 * this test. The plaintext opt-in is deleted before parsing or any networking.
 *
 * Input: {"connection":{"host":"...","username":"...","password":"..."},
 *         "state":{...Mac /api/export backup...}}
 *
 * Proof artifacts contain numeric measurements and booleans only. Test
 * callbacks deliberately never save progress or track choices to user state.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativePlaybackProofTest {
    @Test(timeout = 360_000)
    fun optedInProviderPlaysNativelyWithTracksSeekingAndLifecycle() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val optIn = File(context.filesDir, "qa-account.json")
        assumeTrue("Real-provider verification is opt-in; no private QA account file is present.", optIn.isFile)
        val raw = try {
            assertTrue("Private QA file must be bounded.", optIn.length() in 1..(26L * 1024 * 1024))
            optIn.readText(Charsets.UTF_8)
        } finally {
            assertTrue("Private opt-in must be removed before networking.", optIn.delete())
        }
        val request = runCatching { JSONObject(raw) }.getOrElse { throw AssertionError("Private opt-in JSON is invalid.") }
        val connection = request.optJSONObject("connection") ?: throw AssertionError("Private opt-in requires a connection object.")
        val importedState = request.optJSONObject("state") ?: throw AssertionError("Private opt-in requires a state backup.")
        val proofDirectory = File(context.getExternalFilesDir(null) ?: context.filesDir, "proofs").apply { mkdirs() }
        val proofFile = File(proofDirectory, "native-playback-proof.json")
        val proof = JSONObject().put("schemaVersion", 1).put("deviceApi", Build.VERSION.SDK_INT)
            .put("success", false).put("phase", 0).put("privateOptInDeleted", !optIn.exists())
        val began = SystemClock.elapsedRealtime()
        val repository = MavieRepository(context)
        var scenario: ActivityScenario<MainActivity>? = null
        var controller: NativePlaybackController? = null
        var selected: MediaItem? = null
        var baseline: JSONObject? = null
        val progressCallbacks = AtomicInteger(0)
        val selectionCallbacks = AtomicInteger(0)

        try {
            scenario = ActivityScenario.launch(MainActivity::class.java)
            scenario.onActivity { it.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
            runBlocking {
                repository.importConnection(connection.toString())
                repository.importState(importedState.toString())
            }
            proof.put("phase", 1).put("accountImported", true)
            val home = runBlocking { repository.home() }
            val catalog = runBlocking { repository.catalog(MediaKind.VOD, pageSize = 60) }
            assertTrue("The provider movie catalog must contain content.", catalog.total > 0)
            assertTrue("Home must have movie metadata.", home.recentMovies.isNotEmpty())
            proof.put("catalogMovieCount", catalog.total).put("homeMovieCount", home.recentMovies.size)
                .put("homeSeriesCount", home.recentSeries.size).put("phase", 2)
            val known = runBlocking { repository.item("vod:1774083") }
            val fallback = (home.recentMovies + catalog.items).distinctBy { it.id }
                .sortedByDescending { movie ->
                    (if (movie.extension.equals("mkv", true)) 2 else 0) +
                        (if (movie.name.contains("TR-EN", true) || movie.name.contains("TR-ENG", true)) 3 else 0)
                }.firstOrNull()
            val movie = known ?: fallback ?: throw AssertionError("A playable movie is required.")
            selected = runBlocking { repository.detail(movie).item }
            val item = requireNotNull(selected)
            baseline = JSONObject(runBlocking { repository.exportState() })
            val baselineProgress = progressRow(requireNotNull(baseline), item.id)
            val baselineTracks = runBlocking { repository.trackPreference(item.id) }
            proof.put("knownMovie", known != null).put("phase", 3)
            val source = repository.streamUrl(item)
            // Start independently of imported user progress: test callbacks are
            // memory-only, so these probes cannot advance the user's history.
            val startPosition = if (item.durationSeconds > 60 || item.durationSeconds == 0.0) 30_000L else 0L
            val runningScenario = requireNotNull(scenario)
            runningScenario.onActivity { activity ->
                val nativeView = VLCVideoLayout(activity)
                activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                activity.setContentView(nativeView)
                controller = NativePlaybackController(
                    activity.applicationContext, source, false, startPosition,
                    initialAudioTrack = null, initialSubtitleTrack = -1,
                    onProgress = { _, _ -> progressCallbacks.incrementAndGet() },
                    onTrackSelection = { _, _ -> selectionCallbacks.incrementAndGet() },
                ).also { it.attach(nativeView) }
            }
            val player = requireNotNull(controller)
            awaitSnapshot(player, "Native playback did not start and advance.", 90_000) {
                it.playing && it.durationMs > 0 && it.positionMs >= startPosition + 1_500 && it.seekable
            }
            val initial = awaitSnapshot(player, "Native track inventory was not populated.", 20_000) {
                it.audioTracks.isNotEmpty() && (known == null || it.audioTracks.size >= 2 && it.subtitleTracks.isNotEmpty())
            }
            proof.put("phase", 4).put("nativePlaybackStarted", true).put("positionAdvanced", true)
                .put("nativeDurationMs", initial.durationMs).put("nativeAudioCount", initial.audioTracks.size)
                .put("nativeSubtitleCount", initial.subtitleTracks.size)
            if (known != null) {
                assertTrue("Known movie must expose both provider audio tracks.", initial.audioTracks.size >= 2)
                assertTrue("Known movie must expose provider subtitles.", initial.subtitleTracks.isNotEmpty())
            }
            val english = initial.audioTracks.firstOrNull {
                it.label.contains("İngilizce", true) || it.label.contains("English", true) || it.label.contains("eng", true)
            }
            val turkish = initial.subtitleTracks.firstOrNull {
                it.label.contains("Türkçe", true) || it.label.contains("Turkish", true) || it.label.contains("tur", true)
            }
            if (known != null) {
                assertNotNull("Known movie must expose English audio.", english)
                assertNotNull("Known movie must expose Turkish subtitles.", turkish)
            }
            val chosenAudio = english ?: initial.audioTracks.first()
            val chosenSubtitle = turkish ?: initial.subtitleTracks.firstOrNull()
            runningScenario.onActivity {
                player.selectAudio(chosenAudio.id)
                if (chosenSubtitle != null) player.selectSubtitle(chosenSubtitle.id)
            }
            awaitSnapshot(player, "Native audio/subtitle selection was not applied.", 20_000) {
                it.audioTrackId == chosenAudio.id && (chosenSubtitle == null || it.subtitleTrackId == chosenSubtitle.id)
            }
            proof.put("audioSelectionApplied", true).put("englishAudioAvailable", english != null)
                .put("subtitleSelectionApplied", chosenSubtitle != null).put("turkishSubtitleAvailable", turkish != null)
            runningScenario.onActivity { player.selectSubtitle(-1) }
            awaitSnapshot(player, "Subtitles could not be disabled.", 10_000) { it.subtitleTrackId == -1 }
            proof.put("subtitleOffApplied", true)
            if (chosenSubtitle != null) {
                runningScenario.onActivity { player.selectSubtitle(chosenSubtitle.id) }
                awaitSnapshot(player, "Subtitles could not be restored.", 10_000) { it.subtitleTrackId == chosenSubtitle.id }
            }

            val forward = player.state.value.positionMs + 10_000
            runningScenario.onActivity { player.seekTo(forward) }
            val afterForward = awaitSnapshot(player, "Native forward seek did not reach the requested point.", 25_000) {
                it.playing && it.positionMs in (forward + 600)..(forward + 3_500)
            }
            proof.put("seekForwardPassed", true).put("forwardSeekDeviationMs", abs(afterForward.positionMs - forward))
            val backward = (afterForward.positionMs - 10_000).coerceAtLeast(0)
            runningScenario.onActivity { player.seekTo(backward) }
            val afterBackward = awaitSnapshot(player, "Native backward seek did not reach the requested point.", 25_000) {
                it.playing && it.positionMs in (backward + 600)..(backward + 3_500)
            }
            proof.put("seekBackwardPassed", true).put("backwardSeekDeviationMs", abs(afterBackward.positionMs - backward))
            runningScenario.onActivity { player.togglePlaying() }
            val paused = awaitSnapshot(player, "Native pause did not take effect.", 10_000) { !it.playing && !it.buffering }
            SystemClock.sleep(1_200)
            assertTrue("Paused media time must remain stable.", abs(player.state.value.positionMs - paused.positionMs) < 800)
            proof.put("pausePassed", true)
            runningScenario.onActivity { player.togglePlaying() }
            awaitSnapshot(player, "Playback did not advance after resume.", 15_000) { it.playing && it.positionMs > paused.positionMs + 800 }
            proof.put("resumePassed", true).put("phase", 5)

            val lifecyclePosition = player.state.value.positionMs
            runningScenario.onActivity { player.suspendPlayback() }
            awaitSnapshot(player, "Background playback did not stop.", 10_000) { !it.playing && !it.buffering }
            SystemClock.sleep(700)
            runningScenario.onActivity { player.resumePlayback() }
            awaitSnapshot(player, "Foreground playback did not resume at its saved position.", 45_000) {
                it.playing && it.positionMs > lifecyclePosition + 700 && it.positionMs < lifecyclePosition + 12_000
            }
            proof.put("lifecycleResumePassed", true)
            instrumentation.waitForIdleSync()
            instrumentation.uiAutomation.takeScreenshot()?.let { image ->
                try {
                    File(proofDirectory, "native-playback.png").outputStream().use { output ->
                        proof.put("screenshotSaved", image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, output))
                    }
                    var sampleCount = 0
                    var nonBlackCount = 0
                    var darkest = 255
                    var lightest = 0
                    // Inspect the center of the native video surface, avoiding
                    // status/navigation bars and the subtitle baseline.
                    for (y in (image.height * .43f).toInt() until (image.height * .57f).toInt() step 8) {
                        for (x in (image.width * .25f).toInt() until (image.width * .75f).toInt() step 8) {
                            val pixel = image.getPixel(x, y)
                            val luma = (android.graphics.Color.red(pixel) * 3 + android.graphics.Color.green(pixel) * 6 + android.graphics.Color.blue(pixel)) / 10
                            sampleCount++
                            if (luma > 12) nonBlackCount++
                            darkest = minOf(darkest, luma)
                            lightest = maxOf(lightest, luma)
                        }
                    }
                    proof.put("sampledVideoPixels", sampleCount).put("nonBlackVideoPixels", nonBlackCount)
                        .put("videoLumaRange", lightest - darkest)
                    assertTrue("Native video surface must contain a rendered picture.", nonBlackCount > sampleCount / 100 && lightest - darkest >= 15)
                    proof.put("nativeVideoPictureVisible", true)
                } finally { image.recycle() }
            }
            runningScenario.onActivity { player.close() }
            controller = null
            proof.put("released", true)
            val after = JSONObject(runBlocking { repository.exportState() })
            assertEquals("QA must not change the selected movie's saved progress.", baselineProgress?.toString(), progressRow(after, item.id)?.toString())
            assertEquals("QA must not change saved track preferences.", baselineTracks, runBlocking { repository.trackPreference(item.id) })
            proof.put("progressPreserved", true).put("trackPreferencesPreserved", true)
                .put("progressCallbackCount", progressCallbacks.get()).put("trackSelectionCallbackCount", selectionCallbacks.get())
                .put("phase", 6).put("success", true)
            assertTrue("Native progress callbacks must be emitted.", progressCallbacks.get() > 0)
            assertTrue("Native track selection callbacks must be emitted.", selectionCallbacks.get() > 0)
        } finally {
            scenario?.let { activityScenario -> runCatching { activityScenario.onActivity { controller?.close() } } }
            runCatching { scenario?.close() }
            // The test passes memory-only callbacks. Defensive exact restoration
            // is limited to its own movie if any future callback changes that.
            val restoreItem = selected
            val restoreBackup = baseline
            if (restoreItem != null && restoreBackup != null) runBlocking {
                runCatching {
                    val previous = progressRow(restoreBackup, restoreItem.id)
                    val now = progressRow(JSONObject(repository.exportState()), restoreItem.id)
                    if (previous?.toString() != now?.toString()) {
                        repository.clearProgress(restoreItem.id)
                        if (previous != null) repository.importState(
                            JSONObject().put("version", 1).put("progress", JSONArray().put(previous)).toString()
                        )
                    }
                }
            }
            proof.put("elapsedMs", SystemClock.elapsedRealtime() - began)
            proofFile.writeText(proof.toString(2), Charsets.UTF_8)
            optIn.delete()
        }
    }

    private fun progressRow(backup: JSONObject, itemId: String): JSONObject? {
        val rows = backup.optJSONArray("progress") ?: return null
        for (index in 0 until rows.length()) rows.optJSONObject(index)?.let { if (it.optString("item_id") == itemId) return it }
        return null
    }

    private fun awaitSnapshot(
        player: NativePlaybackController,
        reason: String,
        timeoutMs: Long,
        predicate: (PlaybackSnapshot) -> Boolean,
    ): PlaybackSnapshot {
        val deadline = SystemClock.elapsedRealtime() + timeoutMs
        while (SystemClock.elapsedRealtime() < deadline) {
            val snapshot = player.state.value
            assertFalse("Native player reported a playback error.", snapshot.error != null)
            if (predicate(snapshot)) return snapshot
            SystemClock.sleep(100)
        }
        val last = player.state.value
        throw AssertionError("$reason State: playing=${last.playing}, buffering=${last.buffering}, positionMs=${last.positionMs}, durationMs=${last.durationMs}, audioCount=${last.audioTracks.size}, subtitleCount=${last.subtitleTracks.size}.")
    }
}
