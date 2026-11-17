package app.cineva.player.player

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaybackPositionTest {
    @Test fun fullTitleRemainsReachableEvenForLongMedia() {
        val durationMs = 12 * 60 * 60 * 1000L + 500L
        assertEquals(0L, timelinePosition(0f, durationMs))
        assertEquals(durationMs / 2, timelinePosition(.5f, durationMs))
        assertEquals(durationMs, timelinePosition(1f, durationMs))
        assertEquals(1f, timelineFraction(durationMs, durationMs), 0f)
        assertEquals(0L, timelinePosition(Float.NaN, durationMs))
        assertEquals(0f, timelineFraction(5_000, 0), 0f)
    }

    @Test fun aPrematureEofDoesNotOfferTheNextEpisode() {
        assertFalse(reachedContentEnd(39_000, 45_000))
        assertTrue(reachedContentEnd(44_700, 45_000))
        assertTrue(reachedContentEnd(8_000, 8_000))
        assertTrue(reachedContentEnd(75_000, 0))
    }

    @Test fun providerEofUsesNativeFractionWhenAbsoluteClockLagsAfterSeeking() {
        val duration = 3_190_519L
        val staleClock = 3_183_097L
        assertFalse(reachedContentEnd(staleClock, duration))
        val resolved = nativePlaybackPosition(staleClock, .99952954f, duration)
        assertTrue("The native fraction is within the final two seconds.", resolved >= duration - 2_000)
        assertTrue(reachedContentEnd(resolved, duration))
    }

    @Test fun resolvingNativePositionStillRejectsEarlyDisconnectsAndInvalidFractions() {
        val duration = 3_190_519L
        assertFalse(reachedContentEnd(nativePlaybackPosition(1_590_000L, .5f, duration), duration))
        assertEquals(1_590_000L, nativePlaybackPosition(1_590_000L, Float.NaN, duration))
        assertFalse(reachedContentEnd(nativePlaybackPosition(1_590_000L, Float.NaN, duration), duration))
        assertEquals(0L, nativePlaybackPosition(-1, Float.NaN, duration))
        assertEquals(5_000L, nativePlaybackPosition(5_000, .8f, 0))
    }
}
