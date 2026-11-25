package app.mavie.player

import android.content.res.Configuration
import androidx.compose.ui.input.key.Key
import app.mavie.player.ui.NavigationChromeMode
import app.mavie.player.ui.catalogGridMinCellWidthDp
import app.mavie.player.ui.continueCardWidthDp
import app.mavie.player.ui.isDpadConfirmKey
import app.mavie.player.ui.isDpadNavigationKey
import app.mavie.player.ui.isTelevisionEnvironment
import app.mavie.player.ui.isTelevisionUiMode
import app.mavie.player.ui.isTvBackKey
import app.mavie.player.ui.mediaRowCardWidthDp
import app.mavie.player.ui.resolveNavigationChromeMode
import app.mavie.player.ui.stepTvTabIndex
import app.mavie.player.ui.tvFocusScaleTarget
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TvNavigationTest {
    @Test
    fun dpadConfirmKeysRecognizeCenterEnterAndNumPadEnter() {
        assertTrue(isDpadConfirmKey(Key.DirectionCenter))
        assertTrue(isDpadConfirmKey(Key.Enter))
        assertTrue(isDpadConfirmKey(Key.NumPadEnter))

        assertFalse(isDpadConfirmKey(Key.DirectionLeft))
        assertFalse(isDpadConfirmKey(Key.DirectionRight))
        assertFalse(isDpadConfirmKey(Key.DirectionUp))
        assertFalse(isDpadConfirmKey(Key.DirectionDown))
        assertFalse(isDpadConfirmKey(Key.Spacebar))
        assertFalse(isDpadConfirmKey(Key.MediaPlayPause))
        assertFalse(isDpadConfirmKey(Key.Back))
        assertFalse(isDpadConfirmKey(Key.Escape))
    }

    @Test
    fun dpadNavigationAndBackKeysClassifyAccurately() {
        assertTrue(isDpadNavigationKey(Key.DirectionUp))
        assertTrue(isDpadNavigationKey(Key.DirectionDown))
        assertTrue(isDpadNavigationKey(Key.DirectionLeft))
        assertTrue(isDpadNavigationKey(Key.DirectionRight))
        assertFalse(isDpadNavigationKey(Key.DirectionCenter))
        assertFalse(isDpadNavigationKey(Key.Enter))

        assertTrue(isTvBackKey(Key.Back))
        assertTrue(isTvBackKey(Key.Escape))
        assertFalse(isTvBackKey(Key.DirectionCenter))
    }

    @Test
    fun televisionEnvironmentDetectsUiModeLeanbackAndFireTv() {
        assertTrue(isTelevisionUiMode(Configuration.UI_MODE_TYPE_TELEVISION))
        assertTrue(
            isTelevisionUiMode(Configuration.UI_MODE_TYPE_TELEVISION or Configuration.UI_MODE_NIGHT_YES),
        )
        assertFalse(isTelevisionUiMode(Configuration.UI_MODE_TYPE_NORMAL))
        assertFalse(isTelevisionUiMode(Configuration.UI_MODE_TYPE_NORMAL or Configuration.UI_MODE_NIGHT_YES))
        assertFalse(isTelevisionUiMode(Configuration.UI_MODE_TYPE_CAR))
        assertFalse(isTelevisionUiMode(Configuration.UI_MODE_TYPE_WATCH))

        assertTrue(isTelevisionEnvironment(Configuration.UI_MODE_TYPE_TELEVISION, hasLeanbackFeature = false))
        assertTrue(isTelevisionEnvironment(Configuration.UI_MODE_TYPE_NORMAL, hasLeanbackFeature = true))
        assertTrue(
            isTelevisionEnvironment(
                uiModeType = Configuration.UI_MODE_TYPE_NORMAL,
                hasLeanbackFeature = false,
                hasFireTvFeature = true,
            ),
        )
        assertFalse(
            isTelevisionEnvironment(
                uiModeType = Configuration.UI_MODE_TYPE_NORMAL,
                hasLeanbackFeature = false,
                hasFireTvFeature = false,
            ),
        )
    }

    @Test
    fun navigationChromeModeSelectsTvTopBarRailOrBottomBar() {
        assertEquals(NavigationChromeMode.TV_TOP_BAR, resolveNavigationChromeMode(isTv = true, widthDp = 540))
        assertEquals(NavigationChromeMode.TV_TOP_BAR, resolveNavigationChromeMode(isTv = true, widthDp = 960))
        assertEquals(NavigationChromeMode.TV_TOP_BAR, resolveNavigationChromeMode(isTv = true, widthDp = 1920))

        assertEquals(NavigationChromeMode.BOTTOM_BAR, resolveNavigationChromeMode(isTv = false, widthDp = 412))
        assertEquals(NavigationChromeMode.BOTTOM_BAR, resolveNavigationChromeMode(isTv = false, widthDp = 599))
        assertEquals(NavigationChromeMode.NAVIGATION_RAIL, resolveNavigationChromeMode(isTv = false, widthDp = 600))
        assertEquals(NavigationChromeMode.NAVIGATION_RAIL, resolveNavigationChromeMode(isTv = false, widthDp = 840))
    }

    @Test
    fun stepTvTabIndexClampsWithinBounds() {
        assertEquals(0, stepTvTabIndex(currentIndex = 0, delta = -1, tabCount = 7))
        assertEquals(1, stepTvTabIndex(currentIndex = 0, delta = 1, tabCount = 7))
        assertEquals(6, stepTvTabIndex(currentIndex = 6, delta = 1, tabCount = 7))
        assertEquals(5, stepTvTabIndex(currentIndex = 6, delta = -1, tabCount = 7))
        assertEquals(0, stepTvTabIndex(currentIndex = 3, delta = 1, tabCount = 0))
        assertEquals(6, stepTvTabIndex(currentIndex = 99, delta = 0, tabCount = 7))
    }

    @Test
    fun tvFocusScaleTargetRespectsReducedMotionAndPressPriority() {
        assertEquals(1.0f, tvFocusScaleTarget(focused = false, pressed = false, reducedMotion = false), 0.0001f)
        assertEquals(1.04f, tvFocusScaleTarget(focused = true, pressed = false, reducedMotion = false), 0.0001f)
        assertEquals(0.96f, tvFocusScaleTarget(focused = false, pressed = true, reducedMotion = false), 0.0001f)
        assertEquals(0.96f, tvFocusScaleTarget(focused = true, pressed = true, reducedMotion = false), 0.0001f)

        assertEquals(1.0f, tvFocusScaleTarget(focused = true, pressed = false, reducedMotion = true), 0.0001f)
        assertEquals(1.0f, tvFocusScaleTarget(focused = true, pressed = true, reducedMotion = true), 0.0001f)
    }

    @Test
    fun tvCardAndGridDimensionsScaleForLivingRoomScreens() {
        assertEquals(108, catalogGridMinCellWidthDp(isTv = false, isTablet = false))
        assertEquals(144, catalogGridMinCellWidthDp(isTv = false, isTablet = true))
        assertEquals(168, catalogGridMinCellWidthDp(isTv = true, isTablet = false))
        assertEquals(168, catalogGridMinCellWidthDp(isTv = true, isTablet = true))

        assertEquals(112, mediaRowCardWidthDp(isTv = false))
        assertEquals(154, mediaRowCardWidthDp(isTv = true))

        assertEquals(168, continueCardWidthDp(isTv = false))
        assertEquals(232, continueCardWidthDp(isTv = true))
    }
}
