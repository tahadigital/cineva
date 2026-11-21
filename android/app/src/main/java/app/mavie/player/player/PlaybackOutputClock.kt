package app.mavie.player.player

/**
 * A fallback for demuxers whose native position stops updating before their final
 * audio/video output. Time advances only when actual output counters advance.
 * Immutable so an EOF event can preserve its clock before a later Stopped event.
 */
internal data class PlaybackOutputClock private constructor(
    private val estimatedPositionMs: Long,
    private val lastSampleMs: Long,
    private val lastOutputChangeMs: Long,
    private val lastOutputCount: Long,
    private val confirmed: Boolean,
) {
    constructor() : this(0, -1, -1, -1, false)

    val positionMs: Long? get() = estimatedPositionMs.takeIf { confirmed }

    fun observe(positionMs: Long, elapsedMs: Long, playedAudioBuffers: Int, displayedPictures: Int): PlaybackOutputClock {
        val outputCount = playedAudioBuffers.coerceAtLeast(0).toLong() + displayedPictures.coerceAtLeast(0)
        val sampleGap = elapsedMs - lastSampleMs
        val outputGap = elapsedMs - lastOutputChangeMs
        if (positionMs < 0 || elapsedMs < 0) return PlaybackOutputClock()
        if (lastSampleMs < 0 || sampleGap !in 0..MAX_SAMPLE_GAP_MS || outputCount < lastOutputCount || outputGap > MAX_OUTPUT_GAP_MS) {
            return PlaybackOutputClock(positionMs, elapsedMs, elapsedMs, outputCount, false)
        }
        if (outputCount == lastOutputCount) {
            // Repeated samples and stalls never accrue elapsed time.
            return copy(lastSampleMs = elapsedMs)
        }
        return PlaybackOutputClock(
            estimatedPositionMs = maxOf(positionMs, estimatedPositionMs + outputGap),
            lastSampleMs = elapsedMs,
            lastOutputChangeMs = elapsedMs,
            lastOutputCount = outputCount,
            confirmed = true,
        )
    }

    private companion object {
        // The player samples every 400 ms; an unobserved gap must not count as output.
        const val MAX_SAMPLE_GAP_MS = 1_200L
        // VLC output statistics can be published less often than the native clock.
        const val MAX_OUTPUT_GAP_MS = 2_000L
    }
}
