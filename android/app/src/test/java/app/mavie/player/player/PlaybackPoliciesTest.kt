package app.mavie.player.player

import app.mavie.player.data.MavieErrorCode
import org.junit.Assert.*
import org.junit.Test

class PlaybackPoliciesTest {
    @Test
    fun isValidPlaybackSourceAcceptsSafeMediaSchemesAndRejectsEmptyOrUnsupported() {
        assertTrue(isValidPlaybackSource("http://stream.example.test/live/1.ts"))
        assertTrue(isValidPlaybackSource("https://cdn.example.test/movie/2.mp4"))
        assertTrue(isValidPlaybackSource("content://com.android.providers.media/document/12"))
        assertTrue(isValidPlaybackSource("file:///storage/emulated/0/Movies/sample.mkv"))

        assertFalse(isValidPlaybackSource(""))
        assertFalse(isValidPlaybackSource("   "))
        assertFalse(isValidPlaybackSource("no-scheme.mp4"))
        assertFalse(isValidPlaybackSource("http://"))
        assertFalse(isValidPlaybackSource("content://   "))
        assertFalse(isValidPlaybackSource("file://"))
        assertFalse(isValidPlaybackSource("javascript:alert(1)"))
        assertFalse(isValidPlaybackSource("ftp://files.example.test/video.mp4"))
    }

    @Test
    fun shouldObservePlaybackClockRunsOnlyForActiveForegroundVodPlayback() {
        val active = PlaybackSnapshot(playing = true, buffering = false, ended = false, error = null)
        assertTrue(shouldObservePlaybackClock(released = false, foreground = true, isLive = false, snapshot = active))

        assertFalse(shouldObservePlaybackClock(released = false, foreground = true, isLive = false, snapshot = active.copy(playing = false)))
        assertFalse(shouldObservePlaybackClock(released = false, foreground = true, isLive = true, snapshot = active))
        assertFalse(shouldObservePlaybackClock(released = false, foreground = false, isLive = false, snapshot = active))
        assertFalse(shouldObservePlaybackClock(released = true, foreground = true, isLive = false, snapshot = active))
        assertFalse(shouldObservePlaybackClock(released = false, foreground = true, isLive = false, snapshot = active.copy(ended = true)))
        assertFalse(shouldObservePlaybackClock(released = false, foreground = true, isLive = false, snapshot = active.copy(error = "err")))
    }

    @Test
    fun evaluateStallWatchdogHandlesStopRescheduleAndRetryThresholds() {
        val buffering = PlaybackSnapshot(buffering = true, ended = false, error = null)
        assertEquals(
            StallAction.RESCHEDULE,
            evaluateStallWatchdog(false, true, true, buffering, lastProgressWallMs = 1_000L, nowWallMs = 25_999L),
        )
        assertEquals(
            StallAction.RETRY,
            evaluateStallWatchdog(false, true, true, buffering, lastProgressWallMs = 1_000L, nowWallMs = 26_000L),
        )
        assertEquals(StallAction.STOP, evaluateStallWatchdog(true, true, true, buffering, 0L, 30_000L))
        assertEquals(StallAction.STOP, evaluateStallWatchdog(false, false, true, buffering, 0L, 30_000L))
        assertEquals(StallAction.STOP, evaluateStallWatchdog(false, true, false, buffering, 0L, 30_000L))
        assertEquals(StallAction.STOP, evaluateStallWatchdog(false, true, true, buffering.copy(buffering = false), 0L, 30_000L))
        assertEquals(StallAction.STOP, evaluateStallWatchdog(false, true, true, buffering.copy(ended = true), 0L, 30_000L))
        assertEquals(StallAction.STOP, evaluateStallWatchdog(false, true, true, buffering.copy(error = "fail"), 0L, 30_000L))
    }

    @Test
    fun resolveAudioFocusRequestAndChangeCoverGrantedDelayedLostAndDuck() {
        assertEquals(AudioFocusDecision(true, false, true), resolveAudioFocusRequest(1))
        assertEquals(AudioFocusDecision(false, true, true), resolveAudioFocusRequest(2))
        assertEquals(AudioFocusDecision(false, false, false), resolveAudioFocusRequest(0))

        val transientLoss = resolveAudioFocusChange(-2, focusInterruptedPlayback = false, foreground = true, userWantsPlayback = true)
        assertTrue(transientLoss.pause)
        assertTrue(transientLoss.setInterruptedFromPlaying)
        assertTrue(transientLoss.resetClock)

        val gainWhileForeground = resolveAudioFocusChange(1, focusInterruptedPlayback = true, foreground = true, userWantsPlayback = true)
        assertTrue(gainWhileForeground.resumeIfInterrupted)
        assertTrue(gainWhileForeground.clearInterrupted)
        assertEquals(100, gainWhileForeground.volumePercent)

        val gainWhileBackground = resolveAudioFocusChange(1, focusInterruptedPlayback = true, foreground = false, userWantsPlayback = true)
        assertFalse(gainWhileBackground.resumeIfInterrupted)

        val permanentLoss = resolveAudioFocusChange(-1, focusInterruptedPlayback = true, foreground = true, userWantsPlayback = true)
        assertTrue(permanentLoss.pause)
        assertTrue(permanentLoss.clearInterrupted)
        assertTrue(permanentLoss.clearUserWantsPlayback)
        assertTrue(permanentLoss.resetClock)

        val duck = resolveAudioFocusChange(-3, focusInterruptedPlayback = false, foreground = true, userWantsPlayback = true)
        assertEquals(30, duck.volumePercent)
        assertFalse(duck.pause)
    }

    @Test
    fun nextRetryOrFailureBacksOffAndClassifiesTerminalErrorCodes() {
        val retry1 = nextRetryOrFailure(0, PlaybackFailureReason.GENERIC, networkAvailable = true)
        assertTrue(retry1.shouldRetry)
        assertEquals(1, retry1.nextRetryCount)
        assertEquals(800L, retry1.delayMs)

        val retry2 = nextRetryOrFailure(1, PlaybackFailureReason.STALL, networkAvailable = true)
        assertTrue(retry2.shouldRetry)
        assertEquals(2, retry2.nextRetryCount)
        assertEquals(1600L, retry2.delayMs)

        val stallFail = nextRetryOrFailure(2, PlaybackFailureReason.STALL, networkAvailable = true)
        assertFalse(stallFail.shouldRetry)
        assertEquals(MavieErrorCode.PLAYBACK_STALLED, stallFail.errorCode)

        val offlineFail = nextRetryOrFailure(2, PlaybackFailureReason.GENERIC, networkAvailable = false)
        assertFalse(offlineFail.shouldRetry)
        assertEquals(MavieErrorCode.OFFLINE, offlineFail.errorCode)

        val networkLostFail = nextRetryOrFailure(2, PlaybackFailureReason.GENERIC, networkAvailable = true)
        assertFalse(networkLostFail.shouldRetry)
        assertEquals(MavieErrorCode.PLAYBACK_NETWORK_LOST, networkLostFail.errorCode)
    }
}
