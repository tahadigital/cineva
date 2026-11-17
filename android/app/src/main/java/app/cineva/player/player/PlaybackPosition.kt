package app.cineva.player.player

internal fun timelineFraction(positionMs: Long, durationMs: Long): Float {
    if (durationMs <= 0) return 0f
    return (positionMs.toDouble() / durationMs).coerceIn(0.0, 1.0).toFloat()
}

internal fun timelinePosition(fraction: Float, durationMs: Long): Long =
    if (durationMs <= 0 || !fraction.isFinite()) 0L else
        (fraction.coerceIn(0f, 1f).toDouble() * durationMs).toLong()

// Some demuxers report a stale absolute clock after a seek while their normalized
// position already reflects the actual source location. Both belong to one timeline.
internal fun nativePlaybackPosition(timeMs: Long, fraction: Float, durationMs: Long): Long =
    maxOf(timeMs.coerceAtLeast(0), timelinePosition(fraction, durationMs))

// LibVLC may emit the final clock tick before the true end of the last frame.
internal fun reachedContentEnd(positionMs: Long, durationMs: Long): Boolean =
    durationMs <= 0 || positionMs >= durationMs - minOf(durationMs / 4, (durationMs / 20).coerceIn(2_000L, 3_000L))
