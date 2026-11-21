package app.mavie.player.player

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackOutputClockTest {
    private val duration = 3_190_519L
    private val tailStart = duration - 15_000
    private val frozenNativePosition = 3_183_097L

    @Test fun finalOutputCanFinishWhileNativeTimeAndFractionStayFrozen() {
        var clock = PlaybackOutputClock()
        for (elapsed in 0L..14_800L step 400) {
            clock = clock.observe(minOf(tailStart + elapsed, frozenNativePosition), elapsed,
                playedAudioBuffers = (elapsed / 20).toInt(), displayedPictures = 0)
        }
        val end = requireNotNull(clock.positionMs)
        assertEquals(tailStart + 14_800, end)
        assertTrue(reachedContentEnd(end, duration))
    }

    @Test fun aStalledOutputCounterCannotTurnWaitingTimeIntoCompletion() {
        var clock = PlaybackOutputClock()
        for (elapsed in 0L..30_000L step 400) {
            val played = minOf(elapsed, 7_600)
            clock = clock.observe(minOf(tailStart + played, frozenNativePosition), elapsed,
                playedAudioBuffers = (played / 20).toInt(), displayedPictures = 0)
            assertFalse(reachedContentEnd(clock.positionMs ?: frozenNativePosition, duration))
        }
        assertNull(clock.positionMs)
    }

    @Test fun infrequentlyPublishedOutputStatsStillCountContinuousPlayback() {
        var clock = PlaybackOutputClock()
        for (elapsed in 0L..14_800L step 400) {
            clock = clock.observe(minOf(tailStart + elapsed, frozenNativePosition), elapsed,
                playedAudioBuffers = 0, displayedPictures = (elapsed / 1_000 * 24).toInt())
        }
        assertTrue(reachedContentEnd(requireNotNull(clock.positionMs), duration))
    }

    @Test fun anUnobservedGapOrCounterResetCannotAccruePlayback() {
        var clock = PlaybackOutputClock().observe(frozenNativePosition, 0, 1, 0)
        clock = clock.observe(frozenNativePosition, 400, 2, 0)
        assertEquals(frozenNativePosition + 400, clock.positionMs)
        clock = clock.observe(frozenNativePosition, 30_000, 500, 0)
        assertNull(clock.positionMs)
        clock = clock.observe(frozenNativePosition, 30_400, 0, 0)
        assertNull(clock.positionMs)
        clock = clock.observe(frozenNativePosition, 30_800, 1, 0)
        assertFalse(reachedContentEnd(requireNotNull(clock.positionMs), duration))
    }

    @Test fun resetForSeekPauseOrBufferingDiscardsThePreviousRun() {
        var clock = PlaybackOutputClock().observe(tailStart, 0, 0, 0)
        for (elapsed in 400L..14_800L step 400) {
            clock = clock.observe(frozenNativePosition, elapsed, (elapsed / 20).toInt(), 0)
        }
        assertTrue(reachedContentEnd(requireNotNull(clock.positionMs), duration))
        clock = PlaybackOutputClock()
        clock = clock.observe(100_000, 60_000, 1_000, 0)
        assertNull(clock.positionMs)
        clock = clock.observe(100_400, 60_400, 1_020, 0)
        assertFalse(reachedContentEnd(requireNotNull(clock.positionMs), duration))
    }

    @Test fun outputConfirmedBeforeAnEarlyEofStillRequiresTheFullContentEnd() {
        var clock = PlaybackOutputClock()
        for (elapsed in 0L..4_000L step 400) {
            clock = clock.observe(tailStart + elapsed, elapsed, (elapsed / 20).toInt(), 0)
        }
        assertFalse(reachedContentEnd(requireNotNull(clock.positionMs), duration))
    }
}
