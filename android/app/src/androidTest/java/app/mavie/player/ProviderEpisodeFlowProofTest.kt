package app.mavie.player

import android.app.KeyguardManager
import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.graphics.Bitmap
import android.os.Build
import android.os.SystemClock
import android.view.WindowManager
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.mavie.player.data.MavieRepository
import app.mavie.player.data.LocalDatabase
import app.mavie.player.data.MediaItem
import app.mavie.player.data.MediaKind
import app.mavie.player.data.WatchProgress
import app.mavie.player.ui.UiMedia
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.concurrent.atomic.AtomicReference

/** Opt-in integration test of the real Activity, ViewModel and provider. Never replaces application content. */
@RunWith(AndroidJUnit4::class)
class ProviderEpisodeFlowProofTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Test(timeout = 360_000)
    fun realProviderLongMovieSeekingAndEpisodeTransition() {
        assumeTrue("Real-provider playback requires the episodeProof instrumentation argument.",
            InstrumentationRegistry.getArguments().getString("episodeProof") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assumeTrue("Unlock the test device before playback verification.",
            !(context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isDeviceLocked)
        val repository = MavieRepository(context)
        val accountId = repository.account.value?.id
        assumeTrue("The user's account must already exist on this device.", accountId != null)
        val account = requireNotNull(accountId)
        val database = LocalDatabase(context)
        val directory = File(context.getExternalFilesDir(null), "proofs").apply { mkdirs() }
        val episodeOnly = InstrumentationRegistry.getArguments().getString("episodeOnly") == "true"
        val tailLeadSeconds = InstrumentationRegistry.getArguments().getString("tailLeadSeconds")?.let {
            requireNotNull(it.toDoubleOrNull()) { "tailLeadSeconds must be a finite number from 1 to 60." }
        } ?: 1.5
        require(tailLeadSeconds.isFinite() && tailLeadSeconds in 1.0..60.0) {
            "tailLeadSeconds must be a finite number from 1 to 60."
        }
        val proof = JSONObject().put("success", false).put("deviceApi", Build.VERSION.SDK_INT).put("episodeOnly", episodeOnly)
            .put("requestedTailLeadSeconds", tailLeadSeconds)
        val snapshots = linkedMapOf<Pair<String, String>, ContentValues?>()
        var model: MainViewModel? = null
        var firstEpisode: MediaItem? = null
        var nextEpisode: MediaItem? = null
        val began = SystemClock.elapsedRealtime()
        fun phase(name: String) {
            proof.put("phase", name)
            android.util.Log.i("MavieProviderProof", name)
        }
        try {
            phase("setup")
            rule.runOnUiThread {
                rule.activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                model = ViewModelProvider(rule.activity)[MainViewModel::class.java]
            }
            phase("metadata")
            val (movie, first, next) = runBlocking {
                val series = repository.catalog(MediaKind.SERIES, query = "Dexter", pageSize = 100).items
                    .filter { it.name.startsWith("Dexter", ignoreCase = true) }
                    .minByOrNull { it.name.length }
                    ?: error("Dexter is unavailable in the current provider catalog.")
                val seasons = repository.detail(series).seasons.filter { it.number > 0 }.sortedBy { it.number }
                val episodes = seasons.firstOrNull()?.episodes.orEmpty().sortedBy { it.episode }
                val episode = episodes.firstOrNull { it.episode > 0 }
                    ?: error("Dexter has no playable first-season episode.")
                val following = repository.nextEpisode(episode)
                    ?: error("Dexter has no next episode to verify.")
                var longMovie: MediaItem? = null
                if (!episodeOnly) {
                    val candidates = repository.catalog(MediaKind.VOD, query = "Interstellar", pageSize = 40).items +
                        repository.catalog(MediaKind.VOD, query = "Inception", pageSize = 20).items
                    for (candidate in candidates.distinctBy { it.id }) {
                        val detail = repository.detail(candidate).item
                        if (detail.durationSeconds >= 3600) {
                            longMovie = detail
                            break
                        }
                    }
                    check(longMovie != null) { "The provider has no long movie available for this test." }
                }
                Triple(longMovie, episode, following)
            }
            firstEpisode = first
            nextEpisode = next
            proof.put("movieId", movie?.id ?: JSONObject.NULL).put("firstEpisodeId", first.id).put("nextEpisodeId", next.id)
            phase("snapshot")
            val affectedIds = listOfNotNull(movie?.id, first.id, next.id)
            for (id in affectedIds) {
                for (table in listOf("progress", "native_track_preferences")) {
                    snapshots[table to id] = snapshot(database, table, account, id)
                }
            }
            database.transaction { db ->
                for (id in affectedIds) {
                    db.delete("progress", "account=? AND item_id=?", arrayOf(account, id))
                }
            }
            phase("await-home")
            awaitNodes(hasText("Ana Sayfa"), 120_000)
            val application = requireNotNull(model)
            if (movie != null) {
                phase("movie-start")
                rule.runOnUiThread { application.play(movie.ui()) }
                awaitPlayer(movie)
                val initialMovie = awaitProgress(repository, movie.id, 60_000) {
                    it.durationSeconds >= 3600 && it.positionSeconds >= 1
                }
                proof.put("movieNativeDurationSeconds", initialMovie.durationSeconds)
                phase("movie-far-seek")
                seek(.73f)
                val forwardTarget = initialMovie.durationSeconds * .73
                val forward = awaitProgress(repository, movie.id, 60_000) {
                    it.positionSeconds >= forwardTarget + 3 && it.positionSeconds <= forwardTarget + 20
                }
                capture(directory, "Android-provider-long-seek.png")
                phase("movie-backward-seek")
                seek(.21f)
                val backwardTarget = initialMovie.durationSeconds * .21
                val backward = awaitProgress(repository, movie.id, 60_000) {
                    it.positionSeconds >= backwardTarget + 3 && it.positionSeconds <= backwardTarget + 20
                }
                proof.put("longMovieFarSeek", true).put("farSeekPositionSeconds", forward.positionSeconds)
                    .put("longMovieBackwardSeek", true).put("backwardSeekPositionSeconds", backward.positionSeconds)
                closePlayer()
            }
            phase("episode-start")
            rule.runOnUiThread { application.play(first.ui()) }
            awaitPlayer(first)
            phase("await-next-candidate")
            rule.waitUntil(45_000) { application.player?.nextEpisode?.id == next.id }
            phase("episode-clock")
            val episode = awaitProgress(repository, first.id, 45_000) {
                it.durationSeconds >= 60 && it.positionSeconds >= 1
            }
            val tailFraction = (1.0 - tailLeadSeconds / episode.durationSeconds).toFloat()
            proof.put("episodeDurationSeconds", episode.durationSeconds)
                .put("requestedTailFraction", tailFraction.toDouble())
                .put("requestedTailTargetSeconds", tailFraction.toDouble() * episode.durationSeconds)
            phase("episode-tail-seek")
            seek(tailFraction)
            phase("await-next-card")
            awaitNodes(hasText("Sonraki bölümü oynat"), 60_000)
            capture(directory, "Android-provider-next-episode.png")
            phase("activate-next")
            rule.onNodeWithText("Sonraki bölümü oynat").assertIsDisplayed().performClick()
            phase("await-next-player")
            awaitPlayer(next)
            rule.waitUntil(30_000) { application.player?.item?.id == next.id }
            phase("await-next-clock")
            val nextProgress = awaitProgress(repository, next.id, 45_000) {
                it.durationSeconds > 0 && it.positionSeconds >= 3
            }
            phase("verify-completion")
            val completed = runBlocking { repository.progress(first.id) }
            assertTrue("The finished provider episode must be recorded as complete.", completed?.completed == true)
            proof.put("normalViewModelEntrypoint", true).put("oneTimeline", true)
                .put("realEpisodeReachedEnd", true).put("realNextEpisodeStarted", true)
                .put("nextEpisodePositionSeconds", nextProgress.positionSeconds)
            capture(directory, "Android-provider-next-playing.png")
            closePlayer()
            proof.put("success", true)
            phase("complete")
        } catch (error: Throwable) {
            proof.put("failureType", error.javaClass.simpleName)
            runCatching {
                val first = firstEpisode?.let { runBlocking { repository.progress(it.id) } }
                val next = nextEpisode?.let { runBlocking { repository.progress(it.id) } }
                proof.put("firstLastProgress", first.json()).put("nextLastProgress", next.json())
                rule.runOnUiThread {
                    proof.put("applicationCurrentItemId", model?.player?.item?.id ?: JSONObject.NULL)
                        .put("applicationNextItemId", model?.player?.nextEpisode?.id ?: JSONObject.NULL)
                }
                proof.put("nextCardVisible", rule.onAllNodesWithText("Sonraki bölümü oynat").fetchSemanticsNodes().isNotEmpty())
                    .put("retryPanelVisible", rule.onAllNodesWithText("Yayına bağlanamadık").fetchSemanticsNodes().isNotEmpty())
                    .put("playingControlVisible", rule.onAllNodesWithContentDescription("Duraklat").fetchSemanticsNodes().isNotEmpty())
                val image = rule.onRoot().captureToImage().asAndroidBitmap()
                try {
                    val filename = if (episodeOnly) "Android-provider-episode-tail-failure.png" else "Android-provider-flow-failure.png"
                    File(directory, filename).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
                    proof.put("failureScreenshot", filename)
                } finally {
                    image.recycle()
                }
            }.onFailure { diagnostic -> proof.put("diagnosticFailureType", diagnostic.javaClass.simpleName) }
            throw error
        } finally {
            val scopeJob = model?.viewModelScope?.coroutineContext?.get(Job)
            val cleanupBegan = SystemClock.elapsedRealtime()
            val cleanupStacks = AtomicReference<JSONArray?>()
            proof.put("activityClosed", false).put("viewModelJobsStopped", false)
                .put("viewModelChildrenBeforeCleanup", scopeJob?.children?.count() ?: 0)
            try {
                try {
                    rule.activityRule.scenario.close()
                    proof.put("activityClosed", true)
                } finally {
                    runBlocking {
                        val diagnostic = launch(Dispatchers.Default) {
                            delay(5_000)
                            val stacks = JSONArray()
                            Thread.getAllStackTraces().entries
                                .filter { (_, frames) -> frames.any { it.className.startsWith("app.mavie.player.") } }
                                .take(12).forEach { (thread, frames) ->
                                    // Thread names can contain upstream URLs; only numeric IDs and code frames are safe.
                                    stacks.put(JSONObject().put("threadId", thread.id).put("state", thread.state.name)
                                        .put("frames", JSONArray(frames.take(30).map { "${it.className}.${it.methodName}:${it.lineNumber}" })))
                                }
                            cleanupStacks.set(stacks)
                            android.util.Log.i("MavieProviderProof", "cleanup-pending $stacks")
                        }
                        try {
                            withTimeout(70_000) { scopeJob?.cancelAndJoin() }
                        } finally {
                            diagnostic.cancelAndJoin()
                        }
                    }
                    proof.put("viewModelJobsStopped", scopeJob == null || scopeJob.isCompleted)
                }
            } catch (error: Throwable) {
                proof.put("success", false).put("cleanupFailureType", error.javaClass.simpleName)
                throw error
            } finally {
                proof.put("cleanupElapsedSeconds", (SystemClock.elapsedRealtime() - cleanupBegan) / 1000.0)
                cleanupStacks.get()?.let { proof.put("cleanupPendingStacks", it) }
                try {
                    database.transaction { db ->
                        for ((key, row) in snapshots) {
                            db.delete(key.first, "account=? AND item_id=?", arrayOf(account, key.second))
                            if (row != null) db.insertWithOnConflict(key.first, null, row, SQLiteDatabase.CONFLICT_REPLACE)
                        }
                    }
                    val restored = snapshots.all { (key, row) -> snapshot(database, key.first, account, key.second) == row }
                    proof.put("userStateRestored", restored)
                    assertTrue("Every affected progress and native track-preference row must be restored.", restored)
                } catch (error: Throwable) {
                    proof.put("success", false).put("stateRestorationFailureType", error.javaClass.simpleName)
                    throw error
                } finally {
                    proof.put("elapsedSeconds", (SystemClock.elapsedRealtime() - began) / 1000.0)
                    val filename = if (episodeOnly) "provider-episode-tail-proof.json" else "provider-episode-flow-proof.json"
                    try {
                        File(directory, filename).writeText(proof.toString(2))
                    } finally {
                        database.close()
                    }
                }
            }
        }
    }

    private fun WatchProgress?.json(): Any = if (this == null) JSONObject.NULL else JSONObject()
        .put("positionSeconds", positionSeconds).put("durationSeconds", durationSeconds).put("completed", completed)

    private fun MediaItem.ui() = UiMedia(id, name, kind.key, poster = poster, backdrop = backdrop,
        progressDurationMs = (durationSeconds * 1000).toLong(), episodeNumber = episode)

    private fun snapshot(database: LocalDatabase, table: String, account: String, id: String): ContentValues? =
        database.readableDatabase.rawQuery(
            "SELECT * FROM $table WHERE account=? AND item_id=?", arrayOf(account, id),
        ).use { cursor ->
            if (!cursor.moveToFirst()) null else ContentValues().apply {
                for (index in 0 until cursor.columnCount) {
                    val column = cursor.getColumnName(index)
                    if (cursor.isNull(index)) putNull(column) else put(column, cursor.getString(index))
                }
            }
        }

    private fun awaitNodes(matcher: SemanticsMatcher, timeoutMs: Long) {
        rule.waitUntil(timeoutMs) {
            runCatching { rule.onAllNodes(matcher, useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }.getOrDefault(false)
        }
    }

    private fun awaitPlayer(item: MediaItem) {
        awaitNodes(hasTestTag("player-title") and hasText(item.name), 60_000)
        awaitNodes(hasContentDescription("Duraklat"), 60_000)
        showTimeline()
        rule.onAllNodesWithContentDescription("İçerikte ileri geri sar").assertCountEquals(1)
        rule.waitUntil(15_000) {
            runCatching { rule.onNodeWithContentDescription("İçerikte ileri geri sar").assertIsEnabled() }.isSuccess
        }
    }

    private fun showTimeline() {
        val visible = rule.onAllNodesWithContentDescription("İçerikte ileri geri sar").fetchSemanticsNodes().isNotEmpty()
        if (!visible) rule.onRoot().performTouchInput { click(center) }
        awaitNodes(hasContentDescription("İçerikte ileri geri sar"), 10_000)
    }

    private fun seek(fraction: Float) {
        showTimeline()
        rule.onNodeWithContentDescription("İçerikte ileri geri sar").assertIsEnabled()
            .performSemanticsAction(SemanticsActions.SetProgress) { seek -> assertTrue(seek(fraction)) }
    }

    private fun awaitProgress(repository: MavieRepository, id: String, timeoutMs: Long, predicate: (WatchProgress) -> Boolean): WatchProgress {
        var result: WatchProgress? = null
        rule.waitUntil(timeoutMs) {
            val progress = runBlocking { repository.progress(id) }
            if (progress != null && predicate(progress)) result = progress
            result != null
        }
        return requireNotNull(result)
    }

    private fun closePlayer() {
        showTimeline()
        rule.onNodeWithContentDescription("Oynatıcıdan çık").performClick()
        awaitNodes(hasText("Ana Sayfa"), 30_000)
    }

    private fun capture(directory: File, filename: String) {
        showTimelineUnlessNextPrompt()
        val image = rule.onRoot().captureToImage().asAndroidBitmap()
        try {
            File(directory, filename).outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        } finally {
            image.recycle()
        }
    }

    private fun showTimelineUnlessNextPrompt() {
        if (rule.onAllNodesWithText("Sonraki bölümü oynat").fetchSemanticsNodes().isEmpty()) showTimeline()
    }
}
