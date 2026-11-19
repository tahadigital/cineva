package app.vrelio.player.player

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IMedia
import org.videolan.libvlc.util.VLCVideoLayout
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.abs

/** IDs are the provider's native elementary-stream IDs, never list positions. */
data class PlaybackTrack(val id: Int, val label: String)

data class PlaybackSnapshot(
    val positionMs: Long = 0,
    val durationMs: Long = 0,
    val playing: Boolean = false,
    val buffering: Boolean = true,
    val bufferingPercent: Float = 0f,
    val seekable: Boolean = false,
    val ended: Boolean = false,
    val error: String? = null,
    val audioTracks: List<PlaybackTrack> = emptyList(),
    val subtitleTracks: List<PlaybackTrack> = emptyList(),
    val audioTrackId: Int? = null,
    val subtitleTrackId: Int = -1,
    val audioPreference: Int? = null,
    val subtitlePreference: Int? = -1,
    val playbackRate: Float = 1.0f,
    val fillScreen: Boolean = false,
    val subtitleDelayMs: Long = 0L,
)

/**
 * One native source connection, decoding on the phone itself. Potentially
 * blocking native stop/open calls share a worker, never the Compose thread.
 * Source URLs are intentionally never logged or included in error messages.
 */
internal class NativePlaybackController(
    context: Context,
    sourceUrl: String,
    private val isLive: Boolean,
    startPositionMs: Long,
    initialAudioTrack: Int?,
    initialSubtitleTrack: Int?,
    onProgress: (Long, Long) -> Unit,
    onTrackSelection: (Int?, Int?) -> Unit,
    durationHintMs: Long = 0L,
) {
    private var sourceUrl = sourceUrl
    private var onProgress = onProgress
    private var onTrackSelection = onTrackSelection
    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    private val audioManager = appContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val mutableState = MutableStateFlow(
        PlaybackSnapshot(
            positionMs = if (isLive) 0 else startPositionMs.coerceAtLeast(0),
            durationMs = if (isLive) 0 else durationHintMs.coerceAtLeast(0),
            audioPreference = initialAudioTrack,
            subtitlePreference = initialSubtitleTrack,
        )
    )
    val state: StateFlow<PlaybackSnapshot> = mutableState.asStateFlow()
    @Volatile private var released = false
    @Volatile private var foreground = true
    private var libVlc: LibVLC? = null
    private var player: MediaPlayer? = null
    private var layout: VLCVideoLayout? = null
    private var openPfd: ParcelFileDescriptor? = null
    private var viewsAttached = false
    private var initialized = false
    private var sourceOpened = false
    private var userWantsPlayback = true
    private var focusInterruptedPlayback = false
    private var resumePosition = if (isLive) 0 else startPositionMs.coerceAtLeast(0)
    private var pendingSeek: Long? = resumePosition.takeIf { it > 0 }
    private var expectedSeek: Long? = pendingSeek
    private var seekDeadline = 0L
    private var defaultAudioId: Int? = null
    private var audioPreference = initialAudioTrack
    private var subtitlePreference = initialSubtitleTrack
    // LibVLC can retain the previous track ID after stop(), even though the
    // freshly opened decoder has not restored that subtitle renderer yet.
    // Keep the user's choice and explicitly send it once its tracks reappear.
    @Volatile private var subtitleNeedsReapply = initialSubtitleTrack != null
    private var lastPersistedPosition = -1L
    private var errorRetries = 0
    private var stableSincePosition = resumePosition
    private var lastProgressWallTime = SystemClock.elapsedRealtime()
    private var outputClock = PlaybackOutputClock()
    @Volatile private var requestGeneration = 0
    private var seekGeneration = 0
    private var muted = false

    private val focusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
        .setAudioAttributes(
            AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build()
        )
        .setOnAudioFocusChangeListener({ change ->
            when (change) {
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> {
                    outputClock = PlaybackOutputClock()
                    focusInterruptedPlayback = state.value.playing
                    command { player?.pause() }
                }
                AudioManager.AUDIOFOCUS_GAIN -> {
                    if (focusInterruptedPlayback && foreground && userWantsPlayback) command { player?.play() }
                    focusInterruptedPlayback = false
                }
                AudioManager.AUDIOFOCUS_LOSS -> {
                    outputClock = PlaybackOutputClock()
                    focusInterruptedPlayback = false
                    userWantsPlayback = false
                    command { player?.pause() }
                }
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> command { player?.volume = 30 }
            }
            if (change == AudioManager.AUDIOFOCUS_GAIN) command { player?.volume = if (muted) 0 else 100 }
        }, main)
        .build()

    private fun isValidSource(url: String): Boolean {
        val uri = runCatching { Uri.parse(url) }.getOrNull() ?: return false
        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return false
        return when (scheme) {
            "http", "https" -> !uri.host.isNullOrBlank()
            "content", "file" -> url.length > scheme.length + 3
            else -> false
        }
    }

    fun attach(view: VLCVideoLayout) {
        if (!isValidSource(sourceUrl)) {
            fail("Yayın adresi geçersiz. Hesap bağlantısını kontrol edin.")
            return
        }
        layout = view
        view.keepScreenOn = true
        command {
            if (!initialized) {
                try {
                    libVlc = LibVLC(appContext, arrayListOf("--quiet", "--verbose=-1", "--no-video-title-show"))
                    player = MediaPlayer(requireNotNull(libVlc))
                    initialized = true
                } catch (_: Exception) {
                    fail("Oynatıcı başlatılamadı. Uygulamayı yeniden açıp tekrar deneyin.")
                    return@command
                }
            }
            main.post {
                if (released || layout !== view) return@post
                try {
                    player?.attachViews(view, null, true, false)
                    player?.setVideoScale(MediaPlayer.ScaleType.SURFACE_BEST_FIT)
                    viewsAttached = true
                    if (foreground) open(resumePosition)
                } catch (_: Exception) {
                    fail("Görüntü ekranı hazırlanamadı. Tekrar deneyin.")
                }
            }
        }
    }

    /** Reuse the native decoder and surface. The worker stops the old stream before opening the next. */
    fun replaceSource(
        url: String,
        startPositionMs: Long,
        durationHintMs: Long,
        audioTrack: Int?,
        subtitleTrack: Int?,
        progress: (Long, Long) -> Unit,
        trackSelection: (Int?, Int?) -> Unit,
    ) {
        if (released) return
        if (sourceUrl == url) {
            onProgress = progress
            onTrackSelection = trackSelection
            return
        }
        persistProgress()
        requestGeneration++
        outputClock = PlaybackOutputClock()
        sourceUrl = url
        onProgress = progress
        onTrackSelection = trackSelection
        resumePosition = if (isLive) 0 else startPositionMs.coerceAtLeast(0)
        defaultAudioId = null
        audioPreference = audioTrack
        subtitlePreference = subtitleTrack
        lastPersistedPosition = -1
        errorRetries = 0
        stableSincePosition = resumePosition
        userWantsPlayback = true
        focusInterruptedPlayback = false
        mutableState.value = PlaybackSnapshot(
            positionMs = resumePosition,
            durationMs = if (isLive) 0 else durationHintMs.coerceAtLeast(0),
            audioPreference = audioTrack,
            subtitlePreference = subtitleTrack,
        )
        if (foreground && initialized && viewsAttached) open(resumePosition)
    }

    private fun command(action: () -> Unit) {
        nativeQueue.execute { if (!released) runCatching(action).onFailure { fail("Yayın oynatılamadı. Bağlantını kontrol edip tekrar deneyin.") } }
    }

    private fun open(position: Long) {
        val generation = ++requestGeneration
        val url = sourceUrl
        resumePosition = position
        pendingSeek = if (isLive) null else position.takeIf { it > 0 }
        expectedSeek = pendingSeek
        seekDeadline = SystemClock.elapsedRealtime() + 15_000
        lastProgressWallTime = SystemClock.elapsedRealtime()
        outputClock = PlaybackOutputClock()
        subtitleNeedsReapply = subtitlePreference != null
        mutableState.update { it.copy(positionMs = position, buffering = true, error = null, ended = false) }
        watchForStall(generation)
        if (!isLive) observeClock(generation)
        command {
            if (!foreground || !viewsAttached || generation != requestGeneration) return@command
            val mp = player ?: return@command
            mp.setEventListener(null)
            if (sourceOpened) mp.stop()
            runCatching { openPfd?.close() }; openPfd = null
            if (released || !foreground || generation != requestGeneration) return@command
            val parsedUri = Uri.parse(url)
            val media = if (parsedUri.scheme.equals("content", ignoreCase = true)) {
                val pfd = appContext.contentResolver.openFileDescriptor(parsedUri, "r")
                    ?: run { fail("Yerel video dosyası açılamadı."); return@command }
                openPfd = pfd
                Media(requireNotNull(libVlc), pfd.fileDescriptor)
            } else {
                Media(requireNotNull(libVlc), parsedUri)
            }
            try {
                media.setHWDecoderEnabled(true, false)
                media.addOption(":network-caching=${if (isLive) 1400 else 3000}")
                media.addOption(":http-reconnect")
                media.addOption(":http-user-agent=VLC/3.0.21 LibVLC/3.0.21")
                if (!isLive && position > 0) media.addOption(":start-time=${position / 1000.0}")
                mp.media = media
            } finally {
                media.release()
            }
            mp.setEventListener { event ->
                main.post {
                    if (!released && generation == requestGeneration) handleEvent(event)
                }
            }
            sourceOpened = true
            main.post {
                if (!released && foreground && generation == requestGeneration && userWantsPlayback) audioManager.requestAudioFocus(focusRequest)
            }
            mp.play()
        }
    }

    private fun handleEvent(event: MediaPlayer.Event) {
        if (released) return
        when (event.type) {
            MediaPlayer.Event.Opening -> {
                outputClock = PlaybackOutputClock()
                mutableState.update { it.copy(buffering = true, error = null) }
            }
            MediaPlayer.Event.Buffering -> {
                val wasBuffering = state.value.buffering
                val enteringBuffer = !state.value.buffering && event.buffering < 99.5f
                mutableState.update { it.copy(buffering = event.buffering < 99.5f, bufferingPercent = event.buffering.coerceIn(0f, 100f)) }
                if (enteringBuffer) {
                    outputClock = PlaybackOutputClock()
                    watchForStall(requestGeneration)
                } else if (wasBuffering && !state.value.buffering && state.value.playing) outputClock = PlaybackOutputClock()
            }
            MediaPlayer.Event.Playing -> {
                mutableState.update { it.copy(playing = true, buffering = false, error = null, ended = false) }
                outputClock = PlaybackOutputClock()
                command {
                    refreshTracks()
                    applyPreferences()
                    applyPendingSeek()
                    player?.rate = state.value.playbackRate
                    player?.setVideoScale(if (state.value.fillScreen) MediaPlayer.ScaleType.SURFACE_FILL else MediaPlayer.ScaleType.SURFACE_BEST_FIT)
                    if (state.value.subtitleDelayMs != 0L) player?.setSpuDelay(state.value.subtitleDelayMs * 1000L)
                    if (!userWantsPlayback || !foreground) player?.pause()
                }
            }
            MediaPlayer.Event.Paused -> {
                outputClock = PlaybackOutputClock()
                mutableState.update { it.copy(playing = false, buffering = false) }
                persistProgress()
            }
            MediaPlayer.Event.Stopped -> {
                outputClock = PlaybackOutputClock()
                mutableState.update { it.copy(playing = false, buffering = false) }
            }
            MediaPlayer.Event.TimeChanged -> updatePosition(event.timeChanged)
            MediaPlayer.Event.LengthChanged -> if (!isLive && event.lengthChanged > 0) {
                mutableState.update { it.copy(durationMs = event.lengthChanged) }
            }
            MediaPlayer.Event.SeekableChanged -> {
                mutableState.update { it.copy(seekable = !isLive && event.seekable) }
                // A resume seek can recreate the elementary streams. Reapply a
                // chosen subtitle after that seek instead of trusting LibVLC's
                // stale selected-track getter.
                command {
                    applyPendingSeek()
                    refreshTracks()
                    applyPreferences()
                }
            }
            MediaPlayer.Event.ESAdded, MediaPlayer.Event.ESDeleted, MediaPlayer.Event.ESSelected -> command {
                refreshTracks()
                applyPreferences()
            }
            MediaPlayer.Event.EndReached -> resolveContentEnd()
            MediaPlayer.Event.EncounteredError -> retryAutomatically()
        }
    }

    private fun resolveContentEnd() {
        if (isLive) { retryAutomatically(); return }
        val generation = requestGeneration
        val seek = seekGeneration
        val snapshot = state.value
        val clockAtEnd = outputClock
        val endedAt = SystemClock.elapsedRealtime()
        command {
            if (!foreground || generation != requestGeneration) return@command
            val mp = player ?: return@command
            val duration = mp.length.takeIf { it > 0 } ?: snapshot.durationMs
            val position = nativePlaybackPosition(mp.time, mp.position, duration)
            val counters = outputCounters(mp)
            // Use the EOF timestamp: neither the worker queue nor a following Stopped event
            // may add elapsed time or erase output already observed before EOF.
            val finalOutputClock = if (snapshot.playing && !snapshot.buffering && counters != null)
                clockAtEnd.observe(position, endedAt, counters.first, counters.second).positionMs else null
            val playbackClock = maxOf(clockAtEnd.positionMs ?: 0, finalOutputClock ?: 0)
            main.post {
                // A different source, seek or lifecycle owner may have taken over while sampling.
                if (released || !foreground || generation != requestGeneration || seek != seekGeneration || state.value.ended) return@post
                val finalPosition = maxOf(position, playbackClock)
                if (!reachedContentEnd(finalPosition, duration)) retryAutomatically()
                else {
                    mutableState.update {
                        it.copy(positionMs = duration.takeIf { value -> value > 0 } ?: finalPosition,
                            durationMs = duration, playing = false, buffering = false, ended = true)
                    }
                    persistProgress()
                }
            }
        }
    }

    private fun updatePosition(position: Long) {
        if (position < 0 || state.value.ended) return
        val expected = expectedSeek
        // Do not overwrite a seek or resume point with a stale native clock sample.
        if (expected != null && abs(position - expected) > 4_000 && SystemClock.elapsedRealtime() < seekDeadline) return
        expectedSeek = null
        if (abs(position - resumePosition) > 200) lastProgressWallTime = SystemClock.elapsedRealtime()
        resumePosition = position
        if (position - stableSincePosition > 60_000) {
            errorRetries = 0
            stableSincePosition = position
        }
        mutableState.update { it.copy(positionMs = position) }
        if (lastPersistedPosition < 0 || abs(position - lastPersistedPosition) >= 5_000) persistProgress()
    }

    // Some streams give sparse TimeChanged callbacks. Sample the native clock for the same timeline.
    private fun observeClock(generation: Int) {
        main.postDelayed({
            if (released || !foreground || generation != requestGeneration || state.value.ended || state.value.error != null) return@postDelayed
            if (state.value.playing) {
                val seek = seekGeneration
                command {
                    if (!foreground || generation != requestGeneration) return@command
                    val mp = player ?: return@command
                    val duration = mp.length
                    val position = nativePlaybackPosition(mp.time, mp.position, duration)
                    val counters = outputCounters(mp)
                    val sampledAt = SystemClock.elapsedRealtime()
                    main.post {
                        if (released || !foreground || generation != requestGeneration || seek != seekGeneration || !state.value.playing) return@post
                        if (duration > 0) mutableState.update { it.copy(durationMs = duration) }
                        val nativeSeekConfirmed = expectedSeek?.let { abs(position - it) <= 4_000 } ?: true
                        if (!state.value.buffering && state.value.error == null && nativeSeekConfirmed && counters != null) {
                            outputClock = outputClock.observe(position, sampledAt, counters.first, counters.second)
                        } else outputClock = PlaybackOutputClock()
                        updatePosition(position)
                    }
                }
            }
            observeClock(generation)
        }, 400)
    }

    private fun outputCounters(mp: MediaPlayer): Pair<Int, Int>? = runCatching {
        mp.media?.let { media ->
            try { media.stats?.let { it.playedAbuffers to it.displayedPictures } }
            finally { media.release() }
        }
    }.getOrNull()

    private fun applyPendingSeek() {
        val target = pendingSeek ?: return
        val mp = player ?: return
        if (!mp.isSeekable) return
        if (abs(mp.time - target) > 1500) mp.setTime(target, false)
        pendingSeek = null
    }

    private fun refreshTracks() {
        val mp = player ?: return
        val metadata = mutableMapOf<Int, IMedia.Track>()
        mp.media?.let { media ->
            try { for (i in 0 until media.trackCount) media.getTrack(i)?.let { metadata[it.id] = it } }
            finally { media.release() }
        }
        fun track(description: MediaPlayer.TrackDescription): PlaybackTrack {
            val meta = metadata[description.id]
            val rawTitle = description.name.orEmpty().trim()
            val title = meta?.description.orEmpty().ifBlank { rawTitle }
            val language = languageName(meta?.language.orEmpty(), title)
            val pieces = mutableListOf<String>()
            if (language.isNotBlank()) pieces += language
            if (title.isNotBlank() && !title.equals(language, true)) pieces += title
            if (meta is IMedia.AudioTrack && meta.channels > 2) pieces += "${meta.channels} kanal"
            meta?.codec?.takeIf { it.isNotBlank() }?.let { pieces += it.uppercase(Locale.ROOT) }
            return PlaybackTrack(description.id, pieces.joinToString(" · ").ifBlank { "Parça ${description.id + 1}" })
        }
        val audio = mp.audioTracks.orEmpty().filter { it.id >= 0 }.map(::track)
        val subtitles = mp.spuTracks.orEmpty().filter { it.id >= 0 }.map(::track)
        if (defaultAudioId == null && mp.audioTrack >= 0) defaultAudioId = mp.audioTrack
        mutableState.update {
            it.copy(audioTracks = audio, subtitleTracks = subtitles,
                audioTrackId = mp.audioTrack.takeIf { id -> id >= 0 }, subtitleTrackId = mp.spuTrack,
                durationMs = mp.length.takeIf { length -> length > 0 } ?: it.durationMs)
        }
    }

    private fun applyPreferences() {
        val mp = player ?: return
        val snapshot = state.value
        audioPreference?.takeIf { id -> snapshot.audioTracks.any { it.id == id } }?.let { id ->
            if (mp.audioTrack != id) mp.setAudioTrack(id)
        }
        subtitlePreference?.let { id ->
            val available = id == -1 || snapshot.subtitleTracks.any { it.id == id }
            if (available && (subtitleNeedsReapply || mp.spuTrack != id)) {
                // setSpuTrack is deliberately called even if getSpuTrack()
                // still says the old ID: after resume the getter may be stale
                // while the new decoder has no active subtitle renderer.
                mp.setSpuTrack(id)
                subtitleNeedsReapply = false
            }
        }
    }

    fun selectAudio(id: Int?) {
        outputClock = PlaybackOutputClock()
        audioPreference = id
        mutableState.update { it.copy(audioPreference = id) }
        command {
            val chosen = id ?: defaultAudioId
            if (chosen != null && state.value.audioTracks.any { it.id == chosen }) player?.setAudioTrack(chosen)
            refreshTracks()
        }
        onTrackSelection(id, subtitlePreference)
    }

    fun selectSubtitle(id: Int?) {
        subtitlePreference = id
        subtitleNeedsReapply = false
        mutableState.update { it.copy(subtitlePreference = id) }
        command {
            if (id != null) player?.setSpuTrack(id)
            refreshTracks()
        }
        onTrackSelection(audioPreference, id)
    }

    fun seekTo(positionMs: Long) {
        val snapshot = state.value
        if (isLive || (!snapshot.seekable && !snapshot.ended)) return
        val target = positionMs.coerceAtLeast(0).let { if (snapshot.durationMs > 0) it.coerceAtMost(snapshot.durationMs) else it }
        seekGeneration++
        outputClock = PlaybackOutputClock()
        if (snapshot.ended) {
            if (target >= snapshot.durationMs && snapshot.durationMs > 0) return
            userWantsPlayback = true
            open(target)
            return
        }
        resumePosition = target
        pendingSeek = null
        expectedSeek = target
        seekDeadline = SystemClock.elapsedRealtime() + 15_000
        mutableState.update { it.copy(positionMs = target, ended = false) }
        command { player?.setTime(target, false) }
        persistProgress()
    }

    fun skipBy(deltaMs: Long) = seekTo(state.value.positionMs + deltaMs)

    fun togglePlaying() {
        if (state.value.error != null || state.value.ended) { retry(); return }
        userWantsPlayback = !state.value.playing
        if (!userWantsPlayback) outputClock = PlaybackOutputClock()
        if (userWantsPlayback) audioManager.requestAudioFocus(focusRequest)
        command { if (userWantsPlayback) player?.play() else player?.pause() }
        if (!userWantsPlayback) audioManager.abandonAudioFocusRequest(focusRequest)
    }

    fun toggleMute(): Boolean {
        muted = !muted
        command { player?.volume = if (muted) 0 else 100 }
        return muted
    }

    fun setPlaybackRate(rate: Float) {
        val clamped = rate.coerceIn(0.5f, 2.0f)
        mutableState.update { it.copy(playbackRate = clamped) }
        command { player?.rate = clamped }
    }

    fun setFillScreen(fill: Boolean) {
        mutableState.update { it.copy(fillScreen = fill) }
        command { player?.setVideoScale(if (fill) MediaPlayer.ScaleType.SURFACE_FILL else MediaPlayer.ScaleType.SURFACE_BEST_FIT) }
    }

    fun setSubtitleDelayMs(delayMs: Long) {
        val clamped = delayMs.coerceIn(-30_000L, 30_000L)
        mutableState.update { it.copy(subtitleDelayMs = clamped) }
        command { player?.setSpuDelay(clamped * 1000L) }
    }

    fun pausePlayback() {
        userWantsPlayback = false
        outputClock = PlaybackOutputClock()
        command { player?.pause() }
        audioManager.abandonAudioFocusRequest(focusRequest)
    }

    fun retry() {
        if (released || !foreground) return
        errorRetries = 0
        userWantsPlayback = true
        stableSincePosition = resumePosition
        open(if (isLive || state.value.ended) 0 else resumePosition)
    }

    private fun retryAutomatically() {
        if (released || !foreground) return
        outputClock = PlaybackOutputClock()
        persistProgress()
        if (errorRetries >= 2) {
            fail("Yayın bağlantısı kesildi. İnternetini kontrol edip yeniden deneyin.")
            return
        }
        errorRetries++
        mutableState.update { it.copy(buffering = true, playing = false, error = null) }
        val generation = requestGeneration
        main.postDelayed({ if (!released && foreground && generation == requestGeneration) open(if (isLive) 0 else resumePosition) }, 800L * errorRetries)
    }

    private fun watchForStall(generation: Int) {
        main.postDelayed({
            if (!released && foreground && generation == requestGeneration && state.value.buffering &&
                state.value.error == null && SystemClock.elapsedRealtime() - lastProgressWallTime >= 25_000) {
                retryAutomatically()
            }
        }, 30_000)
    }

    fun suspendPlayback() {
        if (released || !foreground) return
        foreground = false
        outputClock = PlaybackOutputClock()
        requestGeneration++
        persistProgress()
        mutableState.update { it.copy(playing = false, buffering = false) }
        audioManager.abandonAudioFocusRequest(focusRequest)
        command { player?.setEventListener(null); if (sourceOpened) player?.stop(); sourceOpened = false }
    }

    fun resumePlayback() {
        if (released || foreground) return
        foreground = true
        if (initialized && viewsAttached && !state.value.ended) open(resumePosition)
    }

    fun persistProgress() {
        if (isLive) return
        val snapshot = state.value
        lastPersistedPosition = snapshot.positionMs
        onProgress(snapshot.positionMs.coerceAtLeast(0), snapshot.durationMs.coerceAtLeast(0))
    }

    private fun fail(message: String) {
        outputClock = PlaybackOutputClock()
        if (!released) mutableState.update { it.copy(error = message, playing = false, buffering = false) }
    }

    fun close() {
        if (released) return
        persistProgress()
        outputClock = PlaybackOutputClock()
        released = true
        foreground = false
        requestGeneration++
        main.removeCallbacksAndMessages(null)
        audioManager.abandonAudioFocusRequest(focusRequest)
        layout?.keepScreenOn = false
        if (viewsAttached) runCatching { player?.detachViews() }
        viewsAttached = false
        layout = null
        // Queue directly: normal commands intentionally skip work after release.
        nativeQueue.execute {
            runCatching { player?.setEventListener(null); player?.stop() }
            runCatching { openPfd?.close() }; openPfd = null
            runCatching { player?.release() }
            runCatching { libVlc?.release() }
            player = null
            libVlc = null
        }
    }

    private companion object {
        val nativeQueue = Executors.newSingleThreadExecutor { task -> Thread(task, "vrelio-native-player").apply { isDaemon = true } }
    }

}

private val TitleLanguageHints = listOf(
    Regex("\\b(t[uü]rk[cç]e|turkish|\\btr\\b|dublaj)\\b", RegexOption.IGNORE_CASE) to "Türkçe",
    Regex("\\b(ingilizce|english|\\beng?\\b|original|orijinal)\\b", RegexOption.IGNORE_CASE) to "İngilizce",
    Regex("\\b(almanca|german|deutsch|\\bdeu\\b|\\bger\\b)\\b", RegexOption.IGNORE_CASE) to "Almanca",
    Regex("\\b(frans[ıi]zca|french|fran[cç]ais|\\bfra\\b|\\bfre\\b)\\b", RegexOption.IGNORE_CASE) to "Fransızca",
    Regex("\\b(rus[cç]a|russian|\\brus\\b)\\b", RegexOption.IGNORE_CASE) to "Rusça",
    Regex("\\b(arap[cç]a|arabic|\\bara\\b)\\b", RegexOption.IGNORE_CASE) to "Arapça",
    Regex("\\b(ispanyolca|spanish|espa[nñ]ol|\\bspa\\b)\\b", RegexOption.IGNORE_CASE) to "İspanyolca",
    Regex("\\b(italyanca|italian|italiano|\\bita\\b)\\b", RegexOption.IGNORE_CASE) to "İtalyanca",
    Regex("\\b(japonca|japanese|\\bjpn\\b)\\b", RegexOption.IGNORE_CASE) to "Japonca",
    Regex("\\b(korece|korean|\\bkor\\b)\\b", RegexOption.IGNORE_CASE) to "Korece",
    Regex("\\b(portekizce|portuguese|\\bpor\\b)\\b", RegexOption.IGNORE_CASE) to "Portekizce",
    Regex("\\b(azerice|azerbaijani|\\baze\\b)\\b", RegexOption.IGNORE_CASE) to "Azerice",
    Regex("\\b(k[uü]rt[cç]e|kurdish|\\bkur\\b)\\b", RegexOption.IGNORE_CASE) to "Kürtçe",
)

internal fun languageName(raw: String, titleHint: String = ""): String {
    val code = raw.trim().lowercase(Locale.ROOT)
    if (code.isEmpty() || code in setOf("und", "unk", "unknown", "mul", "zxx")) {
        if (titleHint.isNotBlank()) {
            val folded = titleHint.replace('İ', 'i').replace('I', 'ı').lowercase(Locale.ROOT)
            for ((pattern, label) in TitleLanguageHints) {
                if (pattern.containsMatchIn(folded) || pattern.containsMatchIn(titleHint)) return label
            }
        }
        return ""
    }
    val known = mapOf(
        "tr" to "Türkçe", "tur" to "Türkçe",
        "en" to "İngilizce", "eng" to "İngilizce",
        "de" to "Almanca", "deu" to "Almanca", "ger" to "Almanca",
        "fr" to "Fransızca", "fra" to "Fransızca", "fre" to "Fransızca",
        "ar" to "Arapça", "ara" to "Arapça",
        "es" to "İspanyolca", "spa" to "İspanyolca",
        "ru" to "Rusça", "rus" to "Rusça",
        "it" to "İtalyanca", "ita" to "İtalyanca",
        "ja" to "Japonca", "jpn" to "Japonca",
        "ko" to "Korece", "kor" to "Korece",
        "pt" to "Portekizce", "por" to "Portekizce",
        "nl" to "Felemenkçe", "nld" to "Felemenkçe", "dut" to "Felemenkçe",
        "pl" to "Lehçe", "pol" to "Lehçe",
        "zh" to "Çince", "zho" to "Çince", "chi" to "Çince",
        "az" to "Azerice", "aze" to "Azerice",
        "ku" to "Kürtçe", "kur" to "Kürtçe",
        "el" to "Yunanca", "ell" to "Yunanca", "gre" to "Yunanca",
        "fa" to "Farsça", "fas" to "Farsça", "per" to "Farsça",
        "hi" to "Hintçe", "hin" to "Hintçe",
        "uk" to "Ukraynaca", "ukr" to "Ukraynaca",
    )
    return known[code] ?: runCatching { Locale.forLanguageTag(code).getDisplayLanguage(Locale.forLanguageTag("tr")) }.getOrDefault(code).ifBlank { code }
}

internal fun playbackTime(milliseconds: Long): String {
    val seconds = (milliseconds.coerceAtLeast(0) / 1000)
    val h = seconds / 3600
    val m = seconds % 3600 / 60
    val s = seconds % 60
    return if (h > 0) "%d:%02d:%02d".format(Locale.ROOT, h, m, s) else "%d:%02d".format(Locale.ROOT, m, s)
}
