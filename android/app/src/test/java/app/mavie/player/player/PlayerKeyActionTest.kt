package app.mavie.player.player

import androidx.compose.ui.input.key.Key
import org.junit.Assert.assertEquals
import org.junit.Test

class PlayerKeyActionTest {
    private fun resolve(
        key: Key,
        controlsVisible: Boolean = false,
        locked: Boolean = false,
        isLive: Boolean = false,
        seekable: Boolean = true,
        ended: Boolean = false,
        playing: Boolean = true,
        showNext: Boolean = false,
        dialogOpen: Boolean = false,
    ): PlayerKeyAction = resolvePlayerKeyAction(
        key = key,
        controlsVisible = controlsVisible,
        locked = locked,
        isLive = isLive,
        seekable = seekable,
        ended = ended,
        playing = playing,
        showNext = showNext,
        dialogOpen = dialogOpen,
    )

    @Test
    fun dialogOpenSuppressesAllCustomKeyActions() {
        assertEquals(PlayerKeyAction.NONE, resolve(Key.Spacebar, dialogOpen = true))
        assertEquals(PlayerKeyAction.NONE, resolve(Key.Escape, dialogOpen = true))
        assertEquals(PlayerKeyAction.NONE, resolve(Key.DirectionLeft, dialogOpen = true))
    }

    @Test
    fun lockedModeOnlyTriggersUnlockHintOnConfirmOrEscape() {
        assertEquals(PlayerKeyAction.UNLOCK_HINT, resolve(Key.DirectionCenter, locked = true))
        assertEquals(PlayerKeyAction.UNLOCK_HINT, resolve(Key.Enter, locked = true))
        assertEquals(PlayerKeyAction.UNLOCK_HINT, resolve(Key.NumPadEnter, locked = true))
        assertEquals(PlayerKeyAction.UNLOCK_HINT, resolve(Key.Escape, locked = true))
        assertEquals(PlayerKeyAction.NONE, resolve(Key.Spacebar, locked = true))
        assertEquals(PlayerKeyAction.NONE, resolve(Key.DirectionLeft, locked = true))
    }

    @Test
    fun mediaKeysRespectPlayPauseAndLiveSeekability() {
        assertEquals(PlayerKeyAction.TOGGLE_PLAY_PAUSE, resolve(Key.MediaPlayPause))
        assertEquals(PlayerKeyAction.TOGGLE_PLAY_PAUSE, resolve(Key.Spacebar))

        assertEquals(PlayerKeyAction.TOGGLE_PLAY_PAUSE, resolve(Key.MediaPlay, playing = false))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.MediaPlay, playing = true))
        assertEquals(PlayerKeyAction.TOGGLE_PLAY_PAUSE, resolve(Key.MediaPause, playing = true))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.MediaPause, playing = false))

        assertEquals(PlayerKeyAction.SEEK_BACK, resolve(Key.MediaRewind, isLive = false, seekable = true))
        assertEquals(PlayerKeyAction.SEEK_BACK, resolve(Key.MediaStepBackward, isLive = false, seekable = false, ended = true))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.MediaRewind, isLive = true, seekable = true))

        assertEquals(PlayerKeyAction.SEEK_FORWARD, resolve(Key.MediaFastForward, isLive = false, seekable = true))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.MediaStepForward, isLive = false, seekable = false))
    }

    @Test
    fun dpadAndEscapeBehaveDifferentlyWhenControlsHiddenVsVisible() {
        assertEquals(PlayerKeyAction.DISMISS_NEXT, resolve(Key.Escape, showNext = true))
        assertEquals(PlayerKeyAction.EXIT, resolve(Key.Escape, showNext = false))

        assertEquals(PlayerKeyAction.SEEK_BACK, resolve(Key.DirectionLeft, controlsVisible = false, isLive = false, seekable = true))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.DirectionLeft, controlsVisible = false, isLive = true))
        assertEquals(PlayerKeyAction.SEEK_FORWARD, resolve(Key.DirectionRight, controlsVisible = false, isLive = false, seekable = true))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.DirectionCenter, controlsVisible = false))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.DirectionUp, controlsVisible = false))
        assertEquals(PlayerKeyAction.REVEAL_CONTROLS, resolve(Key.DirectionDown, controlsVisible = false))

        assertEquals(PlayerKeyAction.NONE, resolve(Key.DirectionLeft, controlsVisible = true))
        assertEquals(PlayerKeyAction.NONE, resolve(Key.DirectionCenter, controlsVisible = true))
    }
}
