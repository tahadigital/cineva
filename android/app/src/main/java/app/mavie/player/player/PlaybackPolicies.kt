package app.mavie.player.player

import app.mavie.player.data.MavieErrorCode
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.util.Locale

internal enum class StallAction {
    STOP,
    RESCHEDULE,
    RETRY,
}

internal enum class PlaybackFailureReason {
    GENERIC,
    STALL,
}

internal data class AudioFocusDecision(
    val shouldStartPlayback: Boolean,
    val focusInterruptedPlayback: Boolean,
    val userWantsPlayback: Boolean,
)

internal data class AudioFocusChangeDecision(
    val pause: Boolean = false,
    val resumeIfInterrupted: Boolean = false,
    val setInterruptedFromPlaying: Boolean = false,
    val clearInterrupted: Boolean = false,
    val clearUserWantsPlayback: Boolean = false,
    val volumePercent: Int? = null,
    val resetClock: Boolean = false,
)

internal data class RetryDecision(
    val shouldRetry: Boolean,
    val nextRetryCount: Int,
    val delayMs: Long,
    val errorMessage: String? = null,
    val errorCode: MavieErrorCode? = null,
)

internal fun isValidPlaybackSource(url: String): Boolean {
    val trimmed = url.trim()
    if (trimmed.isEmpty()) return false
    val schemeEnd = trimmed.indexOf("://")
    if (schemeEnd <= 0) return false
    val scheme = trimmed.substring(0, schemeEnd).lowercase(Locale.ROOT)
    return when (scheme) {
        "http", "https" -> trimmed.toHttpUrlOrNull()?.host?.isNotBlank() == true
        "content", "file" -> trimmed.length > schemeEnd + 3 && !trimmed.substring(schemeEnd + 3).isBlank()
        else -> false
    }
}

internal fun shouldObservePlaybackClock(
    released: Boolean,
    foreground: Boolean,
    isLive: Boolean,
    snapshot: PlaybackSnapshot,
): Boolean = !released && foreground && !isLive && snapshot.playing && !snapshot.ended && snapshot.error == null

internal fun evaluateStallWatchdog(
    released: Boolean,
    foreground: Boolean,
    userWantsPlayback: Boolean,
    snapshot: PlaybackSnapshot,
    lastProgressWallMs: Long,
    nowWallMs: Long,
    thresholdMs: Long = 25_000L,
): StallAction {
    if (released || !foreground || !userWantsPlayback || !snapshot.buffering || snapshot.ended || snapshot.error != null) {
        return StallAction.STOP
    }
    return if (nowWallMs - lastProgressWallMs >= thresholdMs) StallAction.RETRY else StallAction.RESCHEDULE
}

internal fun resolveAudioFocusRequest(resultCode: Int): AudioFocusDecision = when (resultCode) {
    1 -> AudioFocusDecision(shouldStartPlayback = true, focusInterruptedPlayback = false, userWantsPlayback = true)
    2 -> AudioFocusDecision(shouldStartPlayback = false, focusInterruptedPlayback = true, userWantsPlayback = true)
    else -> AudioFocusDecision(shouldStartPlayback = false, focusInterruptedPlayback = false, userWantsPlayback = false)
}

internal fun resolveAudioFocusChange(
    change: Int,
    focusInterruptedPlayback: Boolean,
    foreground: Boolean,
    userWantsPlayback: Boolean,
): AudioFocusChangeDecision = when (change) {
    -2 -> AudioFocusChangeDecision(
        pause = true,
        setInterruptedFromPlaying = true,
        resetClock = true,
    )
    1 -> AudioFocusChangeDecision(
        resumeIfInterrupted = focusInterruptedPlayback && foreground && userWantsPlayback,
        clearInterrupted = true,
        volumePercent = 100,
    )
    -1 -> AudioFocusChangeDecision(
        pause = true,
        clearInterrupted = true,
        clearUserWantsPlayback = true,
        resetClock = true,
    )
    -3 -> AudioFocusChangeDecision(volumePercent = 30)
    else -> AudioFocusChangeDecision()
}

internal fun nextRetryOrFailure(
    currentRetries: Int,
    reason: PlaybackFailureReason,
    networkAvailable: Boolean,
): RetryDecision {
    if (currentRetries >= 2) {
        val code = when {
            reason == PlaybackFailureReason.STALL -> MavieErrorCode.PLAYBACK_STALLED
            !networkAvailable -> MavieErrorCode.OFFLINE
            else -> MavieErrorCode.PLAYBACK_NETWORK_LOST
        }
        val msg = when (code) {
            MavieErrorCode.PLAYBACK_STALLED -> "Yayın uzun süre yanıt vermedi. Bağlantını kontrol edip yeniden deneyin."
            MavieErrorCode.OFFLINE -> "İnternet bağlantısı yok. Bağlantını kontrol edip yeniden deneyin."
            else -> "Yayın bağlantısı kesildi. İnternetini kontrol edip yeniden deneyin."
        }
        return RetryDecision(
            shouldRetry = false,
            nextRetryCount = currentRetries,
            delayMs = 0L,
            errorMessage = msg,
            errorCode = code,
        )
    }
    val next = currentRetries + 1
    return RetryDecision(shouldRetry = true, nextRetryCount = next, delayMs = 800L * next)
}
