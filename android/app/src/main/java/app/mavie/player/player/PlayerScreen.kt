package app.mavie.player.player

import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import android.media.AudioManager
import android.os.Build
import android.util.Rational
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.sizeIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.List
import androidx.compose.material.icons.automirrored.rounded.VolumeOff
import androidx.compose.material.icons.automirrored.rounded.VolumeUp
import androidx.compose.material.icons.rounded.AspectRatio
import androidx.compose.material.icons.rounded.Audiotrack
import androidx.compose.material.icons.rounded.Bedtime
import androidx.compose.material.icons.rounded.Forward10
import androidx.compose.material.icons.rounded.Fullscreen
import androidx.compose.material.icons.rounded.FullscreenExit
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PictureInPictureAlt
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.Replay
import androidx.compose.material.icons.rounded.Replay10
import androidx.compose.material.icons.rounded.SkipNext
import androidx.compose.material.icons.rounded.Speed
import androidx.compose.material.icons.rounded.Subtitles
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.app.PictureInPictureModeChangedInfo
import androidx.core.util.Consumer
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.mavie.player.ui.MavieBrandDiagonalGradient
import app.mavie.player.ui.MavieCyanDot
import app.mavie.player.ui.MavieGlassDialogFill
import app.mavie.player.ui.MavieGlassPillButton
import app.mavie.player.ui.MavieGlassPillFill
import app.mavie.player.ui.MavieGradientButton
import app.mavie.player.ui.MavieMuted
import app.mavie.player.ui.MaviePurple
import app.mavie.player.ui.MavieTurquoise
import app.mavie.player.ui.errorHintFor
import app.mavie.player.ui.mavieGlassSurface
import app.mavie.player.ui.playbackTime
import app.mavie.player.ui.rememberPressScale
import app.mavie.player.ui.rememberReducedMotion
import coil.compose.AsyncImage
import kotlinx.coroutines.delay
import org.videolan.libvlc.util.VLCVideoLayout

data class UpNextEpisode(val title: String, val season: Int, val number: Int, val artwork: String)

private const val NEXT_EPISODE_SECONDS = 6

internal enum class PlayerKeyAction {
    NONE,
    TOGGLE_PLAY_PAUSE,
    SEEK_BACK,
    SEEK_FORWARD,
    REVEAL_CONTROLS,
    UNLOCK_HINT,
    DISMISS_NEXT,
    EXIT,
}

internal fun resolvePlayerKeyAction(
    key: Key,
    controlsVisible: Boolean,
    locked: Boolean,
    isLive: Boolean,
    seekable: Boolean,
    ended: Boolean,
    playing: Boolean,
    showNext: Boolean,
    dialogOpen: Boolean,
): PlayerKeyAction {
    if (dialogOpen) return PlayerKeyAction.NONE
    if (locked) {
        return when (key) {
            Key.DirectionCenter, Key.Enter, Key.NumPadEnter, Key.Escape -> PlayerKeyAction.UNLOCK_HINT
            else -> PlayerKeyAction.NONE
        }
    }
    when (key) {
        Key.MediaPlayPause, Key.Spacebar -> return PlayerKeyAction.TOGGLE_PLAY_PAUSE
        Key.MediaPlay -> return if (!playing) PlayerKeyAction.TOGGLE_PLAY_PAUSE else PlayerKeyAction.REVEAL_CONTROLS
        Key.MediaPause -> return if (playing) PlayerKeyAction.TOGGLE_PLAY_PAUSE else PlayerKeyAction.REVEAL_CONTROLS
        Key.MediaRewind, Key.MediaStepBackward -> {
            return if (!isLive && (seekable || ended)) PlayerKeyAction.SEEK_BACK else PlayerKeyAction.REVEAL_CONTROLS
        }
        Key.MediaFastForward, Key.MediaStepForward -> {
            return if (!isLive && seekable) PlayerKeyAction.SEEK_FORWARD else PlayerKeyAction.REVEAL_CONTROLS
        }
        Key.Escape -> return if (showNext) PlayerKeyAction.DISMISS_NEXT else PlayerKeyAction.EXIT
        else -> Unit
    }
    if (!controlsVisible) {
        return when (key) {
            Key.DirectionLeft -> if (!isLive && (seekable || ended)) PlayerKeyAction.SEEK_BACK else PlayerKeyAction.REVEAL_CONTROLS
            Key.DirectionRight -> if (!isLive && seekable) PlayerKeyAction.SEEK_FORWARD else PlayerKeyAction.REVEAL_CONTROLS
            Key.DirectionCenter, Key.Enter, Key.NumPadEnter, Key.DirectionUp, Key.DirectionDown -> PlayerKeyAction.REVEAL_CONTROLS
            else -> PlayerKeyAction.NONE
        }
    }
    return PlayerKeyAction.NONE
}

/**
 * Direct, native Android playback: no localhost, WebView or desktop server is involved.
 * Progress and stream selections can be saved by the caller per content.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlayerScreen(
    title: String,
    sourceUrl: String,
    startPositionMs: Long = 0,
    isLive: Boolean = false,
    initialAudioTrack: Int? = null,
    initialSubtitleTrack: Int? = -1,
    durationHintMs: Long = 0L,
    nextEpisode: UpNextEpisode? = null,
    onNextEpisode: () -> Unit = {},
    onProgress: (positionMs: Long, durationMs: Long) -> Unit,
    onTrackSelection: (audioId: Int?, subtitleId: Int?) -> Unit = { _, _ -> },
    episodes: List<Pair<String, String>> = emptyList(),
    currentEpisodeId: String = "",
    onSelectEpisode: (String) -> Unit = {},
    initialLandscape: Boolean = !isLive,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    val view = LocalView.current
    val isTablet = LocalConfiguration.current.smallestScreenWidthDp >= 600
    val lifecycleOwner = LocalLifecycleOwner.current
    val activity = remember(context) { context.findActivity() }
    val audioManager = remember(context) { context.applicationContext.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    val latestNextEpisode by rememberUpdatedState(onNextEpisode)
    val lifecycleState by lifecycleOwner.lifecycle.currentStateFlow.collectAsState()
    val reducedMotion = rememberReducedMotion()
    val controller = remember(isLive) {
        NativePlaybackController(
            context.applicationContext, sourceUrl, isLive, startPositionMs,
            initialAudioTrack, initialSubtitleTrack,
            onProgress, onTrackSelection, durationHintMs,
        )
    }
    DisposableEffect(controller) {
        onDispose { controller.close() }
    }
    DisposableEffect(controller, lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_STOP -> controller.suspendPlayback()
                Lifecycle.Event.ON_START -> controller.resumePlayback()
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    SideEffect {
        controller.replaceSource(
            sourceUrl, startPositionMs, durationHintMs, initialAudioTrack, initialSubtitleTrack,
            onProgress, onTrackSelection,
        )
    }
    val playback by controller.state.collectAsState()
    var controlsVisible by remember(sourceUrl) { mutableStateOf(true) }
    var interactionVersion by remember(sourceUrl) { mutableIntStateOf(0) }
    var trackDialog by remember(sourceUrl) { mutableStateOf<String?>(null) }
    var episodeDrawerOpen by remember(sourceUrl) { mutableStateOf(false) }
    var optionsMenuOpen by remember(sourceUrl) { mutableStateOf(false) }
    var locked by remember(sourceUrl) { mutableStateOf(false) }
    var unlockHintVisible by remember(sourceUrl) { mutableStateOf(false) }
    var sleepMinutes by rememberSaveable { mutableIntStateOf(0) }
    var gestureFeedback by remember(sourceUrl) { mutableStateOf<String?>(null) }
    var dragging by remember(sourceUrl) { mutableStateOf(false) }
    var scrubFraction by remember(sourceUrl) { mutableFloatStateOf(0f) }
    var dragDurationMs by remember(sourceUrl) { mutableLongStateOf(0L) }
    var showBuffering by remember(sourceUrl) { mutableStateOf(false) }
    var muted by remember(isLive) { mutableStateOf(false) }
    var landscape by rememberSaveable(isLive, initialLandscape) { mutableStateOf(initialLandscape) }
    var nextDismissed by remember(sourceUrl) { mutableStateOf(false) }
    var secondsToNext by remember(sourceUrl) { mutableIntStateOf(NEXT_EPISODE_SECONDS) }
    var inPip by remember(activity) {
        mutableStateOf(Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && activity?.isInPictureInPictureMode == true)
    }
    DisposableEffect(activity) {
        val componentActivity = activity as? ComponentActivity
        if (componentActivity == null || Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            onDispose {}
        } else {
            val listener = Consumer<PictureInPictureModeChangedInfo> { info ->
                inPip = info.isInPictureInPictureMode
            }
            componentActivity.addOnPictureInPictureModeChangedListener(listener)
            onDispose { componentActivity.removeOnPictureInPictureModeChangedListener(listener) }
        }
    }
    val initialBrightness = remember(activity) { activity?.window?.attributes?.screenBrightness }
    LaunchedEffect(inPip) {
        if (inPip && initialBrightness != null) {
            activity?.window?.let { win ->
                val attrs = win.attributes
                attrs.screenBrightness = initialBrightness
                win.attributes = attrs
            }
        }
    }
    val rootFocusRequester = remember { FocusRequester() }
    val playPauseFocusRequester = remember { FocusRequester() }
    val showNext = !isLive && playback.ended && nextEpisode != null && !nextDismissed && !inPip
    fun advanceEpisode() {
        if (nextDismissed) return
        nextDismissed = true
        controller.persistProgress()
        latestNextEpisode()
    }
    fun cyclePlaybackRate() {
        val steps = listOf(0.5f, 0.75f, 1.0f, 1.25f, 1.5f, 2.0f)
        val idx = steps.indexOfFirst { kotlin.math.abs(it - playback.playbackRate) < 0.05f }
        val next = steps[(idx + 1) % steps.size]
        controller.setPlaybackRate(next)
        gestureFeedback = "Hız: ${next}x"
        interactionVersion++
    }
    fun toggleFillScreen() {
        val nextFill = !playback.fillScreen
        controller.setFillScreen(nextFill)
        gestureFeedback = if (nextFill) "Ekran: Doldur" else "Ekran: Sığdır"
        interactionVersion++
    }
    fun cycleSleepTimer() {
        val nextMins = when (sleepMinutes) { 0 -> 15; 15 -> 30; 30 -> 45; 45 -> 60; else -> 0 }
        sleepMinutes = nextMins
        gestureFeedback = if (nextMins > 0) "Uyku zamanlayıcısı: $nextMins dk" else "Uyku zamanlayıcısı kapalı"
        interactionVersion++
    }

    DisposableEffect(activity, view) {
        val previousOrientation = activity?.requestedOrientation
        val previousKeepAwake = activity?.window?.attributes?.flags?.and(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) != 0
        val previousBrightness = activity?.window?.attributes?.screenBrightness
        val bars = activity?.window?.let { WindowCompat.getInsetsController(it, view) }
        bars?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        bars?.hide(WindowInsetsCompat.Type.systemBars())
        activity?.window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        onDispose {
            bars?.show(WindowInsetsCompat.Type.systemBars())
            if (!previousKeepAwake) activity?.window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            if (previousBrightness != null) {
                activity?.window?.let { win ->
                    val attrs = win.attributes
                    attrs.screenBrightness = previousBrightness
                    win.attributes = attrs
                }
            }
            if (previousOrientation != null) activity?.requestedOrientation = previousOrientation
        }
    }
    LaunchedEffect(landscape, isTablet) {
        if (isTablet) return@LaunchedEffect
        if (landscape) activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        else if (activity?.requestedOrientation == ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE) {
            activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
        }
    }
    LaunchedEffect(sleepMinutes) {
        if (sleepMinutes > 0) {
            delay(sleepMinutes * 60_000L)
            controller.pausePlayback()
            sleepMinutes = 0
            gestureFeedback = "Uyku zamanlayıcısı: Oynatma durduruldu"
        }
    }
    LaunchedEffect(gestureFeedback) {
        if (gestureFeedback != null) {
            delay(1300)
            gestureFeedback = null
        }
    }
    LaunchedEffect(unlockHintVisible) {
        if (unlockHintVisible) {
            delay(2500)
            unlockHintVisible = false
        }
    }
    LaunchedEffect(playback.buffering, playback.error) {
        showBuffering = false
        if (playback.buffering && playback.error == null) {
            delay(450)
            showBuffering = true
        }
    }
    LaunchedEffect(controlsVisible, playback.playing, trackDialog, episodeDrawerOpen, optionsMenuOpen, dragging, interactionVersion, locked) {
        if (controlsVisible && playback.playing && trackDialog == null && !episodeDrawerOpen && !optionsMenuOpen && !dragging && !locked) {
            delay(4000)
            controlsVisible = false
        }
    }
    LaunchedEffect(controlsVisible, locked, inPip, trackDialog, episodeDrawerOpen, optionsMenuOpen, playback.error, showBuffering, showNext) {
        if (trackDialog == null && !episodeDrawerOpen && !optionsMenuOpen && !inPip) {
            if (!controlsVisible || locked) {
                runCatching { rootFocusRequester.requestFocus() }
            } else if (playback.error == null && !showBuffering && !showNext) {
                runCatching { playPauseFocusRequester.requestFocus() }
            }
        }
    }
    LaunchedEffect(showNext, lifecycleState, trackDialog) {
        if (showNext && lifecycleState.isAtLeast(Lifecycle.State.RESUMED) && trackDialog == null) {
            while (secondsToNext > 0) {
                delay(1000)
                secondsToNext--
            }
            advanceEpisode()
        }
    }
    LaunchedEffect(playback.ended) {
        if (!playback.ended) {
            nextDismissed = false
            secondsToNext = NEXT_EPISODE_SECONDS
        }
    }
    BackHandler {
        if (locked) { unlockHintVisible = true }
        else if (showNext) nextDismissed = true
        else {
            controller.persistProgress()
            onBack()
        }
    }

    var brightnessAccum by remember { mutableFloatStateOf(-1f) }
    var volumeAccum by remember { mutableFloatStateOf(-1f) }
    Box(
        Modifier.fillMaxSize().background(Color.Black)
            .focusRequester(rootFocusRequester)
            .focusable()
            .onPreviewKeyEvent { keyEvent ->
                if (keyEvent.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                val action = resolvePlayerKeyAction(
                    key = keyEvent.key,
                    controlsVisible = controlsVisible,
                    locked = locked,
                    isLive = isLive,
                    seekable = playback.seekable,
                    ended = playback.ended,
                    playing = playback.playing,
                    showNext = showNext,
                    dialogOpen = trackDialog != null || episodeDrawerOpen || optionsMenuOpen,
                )
                when (action) {
                    PlayerKeyAction.NONE -> false
                    PlayerKeyAction.TOGGLE_PLAY_PAUSE -> {
                        controller.togglePlaying()
                        controlsVisible = true
                        interactionVersion++
                        true
                    }
                    PlayerKeyAction.SEEK_BACK -> {
                        controller.skipBy(-10_000L)
                        gestureFeedback = "« 10 sn"
                        interactionVersion++
                        true
                    }
                    PlayerKeyAction.SEEK_FORWARD -> {
                        controller.skipBy(10_000L)
                        gestureFeedback = "10 sn »"
                        interactionVersion++
                        true
                    }
                    PlayerKeyAction.REVEAL_CONTROLS -> {
                        controlsVisible = true
                        interactionVersion++
                        true
                    }
                    PlayerKeyAction.UNLOCK_HINT -> {
                        unlockHintVisible = true
                        true
                    }
                    PlayerKeyAction.DISMISS_NEXT -> {
                        nextDismissed = true
                        true
                    }
                    PlayerKeyAction.EXIT -> {
                        controller.persistProgress()
                        onBack()
                        true
                    }
                }
            }
            .pointerInput(locked, isLive, playback.seekable, playback.ended) {
                detectTapGestures(
                    onTap = {
                        if (locked) unlockHintVisible = !unlockHintVisible
                        else controlsVisible = !controlsVisible
                    },
                    onDoubleTap = { offset ->
                        if (locked || isLive || (!playback.seekable && !playback.ended)) return@detectTapGestures
                        val delta = if (offset.x < size.width / 2f) -10_000L else 10_000L
                        controller.skipBy(delta)
                        gestureFeedback = if (delta < 0) "« 10 sn" else "10 sn »"
                        interactionVersion++
                    },
                )
            }
            .pointerInput(locked) {
                if (locked) return@pointerInput
                detectVerticalDragGestures(
                    onDragStart = {
                        val lp = activity?.window?.attributes
                        val currentBri = lp?.screenBrightness?.takeIf { it in 0f..1f } ?: 0.5f
                        brightnessAccum = currentBri
                        val maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
                        volumeAccum = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC).toFloat() / maxVol
                    },
                    onVerticalDrag = { change, dragAmount ->
                        val height = size.height.coerceAtLeast(1).toFloat()
                        val delta = -dragAmount / (height * 0.7f)
                        if (change.position.x < size.width / 2f) {
                            brightnessAccum = (brightnessAccum + delta).coerceIn(0.04f, 1.0f)
                            activity?.window?.let { win ->
                                val attrs = win.attributes
                                attrs.screenBrightness = brightnessAccum
                                win.attributes = attrs
                            }
                            gestureFeedback = "Parlaklık: %${(brightnessAccum * 100).toInt()}"
                        } else {
                            volumeAccum = (volumeAccum + delta).coerceIn(0f, 1.0f)
                            val maxVol = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
                            audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, (volumeAccum * maxVol).toInt().coerceIn(0, maxVol), 0)
                            gestureFeedback = "Ses: %${(volumeAccum * 100).toInt()}"
                        }
                    },
                )
            }
    ) {
        key(controller) {
            AndroidView(
                factory = { androidContext -> VLCVideoLayout(androidContext).also(controller::attach) },
                modifier = Modifier.fillMaxSize(),
            )
        }
        if (showBuffering && playback.error == null) {
            val pct = playback.bufferingPercent.toInt().coerceIn(0, 100)
            Column(
                Modifier.align(Alignment.Center)
                    .mavieGlassSurface(RoundedCornerShape(22.dp))
                    .padding(horizontal = 24.dp, vertical = 18.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                CircularProgressIndicator(color = MavieTurquoise, strokeWidth = 3.dp, modifier = Modifier.size(34.dp))
                Text(if (isLive) "Canlı yayın hazırlanıyor…" else "Yayın açılıyor…", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(
                    if (pct in 1..99) "Önbellek dolduruluyor · %$pct" else "Ses ve altyazı parçaları senkronize ediliyor",
                    color = Color.White.copy(alpha = .68f),
                    fontSize = 11.sp,
                )
            }
        }
        gestureFeedback?.let { label ->
            Box(
                Modifier.align(Alignment.TopCenter).padding(top = 56.dp)
                    .mavieGlassSurface(CircleShape)
                    .padding(horizontal = 18.dp, vertical = 8.dp),
            ) { Text(label, color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Bold) }
        }
        if (locked && unlockHintVisible && !inPip) {
            MavieGlassPillButton(
                onClick = { locked = false; controlsVisible = true; unlockHintVisible = false },
                modifier = Modifier.align(Alignment.BottomCenter).windowInsetsPadding(WindowInsets.safeDrawing)
                    .padding(bottom = 28.dp).heightIn(min = 48.dp),
                shape = CircleShape,
            ) { Text("Kilidi Aç", fontWeight = FontWeight.Bold, color = Color.White) }
        }
        AnimatedVisibility(
            visible = !locked && !inPip && (controlsVisible || !playback.playing || playback.error != null),
            enter = if (reducedMotion) EnterTransition.None else fadeIn(),
            exit = if (reducedMotion) ExitTransition.None else fadeOut(),
            modifier = Modifier.fillMaxSize(),
        ) {
            Column(
                Modifier.fillMaxSize()
                    .background(Brush.verticalGradient(listOf(Color.Black.copy(alpha = .8f), Color.Transparent, Color.Black.copy(alpha = .9f))))
                    .windowInsetsPadding(WindowInsets.safeDrawing)
                    .padding(horizontal = 16.dp, vertical = 12.dp)
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth()
                        .mavieGlassSurface(CircleShape, topColor = Color(0xA6121728), bottomColor = Color(0x8C0B0F1C))
                        .padding(horizontal = 4.dp, vertical = 2.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    PlayerControl(
                        icon = Icons.AutoMirrored.Rounded.ArrowBack,
                        label = "Oynatıcıdan çık",
                        size = 48,
                    ) { controller.persistProgress(); onBack() }
                    Column(Modifier.weight(1f).padding(start = 8.dp)) {
                        Text(
                            if (isLive) "CANLI YAYIN" else "ŞİMDİ OYNATILIYOR",
                            fontSize = 9.sp, letterSpacing = 2.sp, color = Color.White.copy(alpha = .68f), fontWeight = FontWeight.Bold,
                        )
                        Text(
                            title,
                            modifier = Modifier.testTag("player-title"),
                            fontSize = 17.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Color.White,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && activity != null) {
                        TextButton(
                            onClick = {
                                runCatching {
                                    activity.enterPictureInPictureMode(
                                        PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build()
                                    )
                                }
                            },
                            modifier = Modifier.heightIn(min = 48.dp).semantics {
                                contentDescription = "Resim içinde resim (PiP)"
                            },
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 8.dp),
                        ) {
                            Icon(Icons.Rounded.PictureInPictureAlt, null, tint = Color.White, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("PiP", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    TextButton(
                        onClick = { locked = true; controlsVisible = false; unlockHintVisible = true },
                        modifier = Modifier.heightIn(min = 48.dp).semantics {
                            contentDescription = "Ekranı kilitle"
                        },
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 8.dp),
                    ) {
                        Icon(Icons.Rounded.Lock, null, tint = Color.White, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Kilitle", color = Color.White, fontSize = 12.sp)
                    }
                    PlayerControl(
                        icon = if (muted) Icons.AutoMirrored.Rounded.VolumeOff else Icons.AutoMirrored.Rounded.VolumeUp,
                        label = if (muted) "Sesi aç" else "Sesi kapat",
                        size = 48,
                    ) { muted = controller.toggleMute() }
                }
                Spacer(Modifier.weight(1f))
                if (playback.error == null && !showBuffering && !showNext) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                        if (!isLive) {
                            PlayerControl(
                                icon = Icons.Rounded.Replay10,
                                label = "10 saniye geri sar",
                                enabled = playback.seekable || playback.ended,
                                size = 64,
                                iconSize = 34,
                            ) { controller.skipBy(-10_000); controlsVisible = true; interactionVersion++ }
                        }
                        Spacer(Modifier.width(24.dp))
                        PlayerControl(
                            icon = if (playback.playing) Icons.Rounded.Pause else if (playback.ended) Icons.Rounded.Replay else Icons.Rounded.PlayArrow,
                            label = if (playback.playing) "Duraklat" else if (playback.ended) "Tekrar oynat" else "Oynat",
                            size = 80,
                            prominent = true,
                            iconSize = 42,
                            modifier = Modifier.focusRequester(playPauseFocusRequester),
                        ) { controller.togglePlaying(); controlsVisible = true; interactionVersion++ }
                        Spacer(Modifier.width(24.dp))
                        if (!isLive) {
                            PlayerControl(
                                icon = Icons.Rounded.Forward10,
                                label = "10 saniye ileri sar",
                                enabled = playback.seekable,
                                size = 64,
                                iconSize = 34,
                            ) { controller.skipBy(10_000); controlsVisible = true; interactionVersion++ }
                        }
                    }
                }
                Spacer(Modifier.weight(1f))
                if (!isLive) {
                    val duration = if (dragging) dragDurationMs else playback.durationMs
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(playbackTime(if (dragging) timelinePosition(scrubFraction, duration) else playback.positionMs), color = Color.White, fontSize = 11.sp)
                        Text(if (duration > 0) playbackTime(duration) else "–:––", color = Color.White.copy(alpha = .72f), fontSize = 11.sp)
                    }
                    Slider(
                        value = if (dragging) scrubFraction else timelineFraction(playback.positionMs, duration),
                        onValueChange = {
                            if (!dragging) dragDurationMs = playback.durationMs
                            dragging = true
                            scrubFraction = it
                            controlsVisible = true
                            interactionVersion++
                        },
                        onValueChangeFinished = {
                            if (dragging) controller.seekTo(timelinePosition(scrubFraction, dragDurationMs))
                            dragging = false
                        },
                        enabled = duration > 0 && (playback.seekable || playback.ended),
                        colors = SliderDefaults.colors(
                            thumbColor = MavieCyanDot,
                            activeTrackColor = MaviePurple,
                            inactiveTrackColor = Color.White.copy(alpha = .28f),
                        ),
                        modifier = Modifier.fillMaxWidth().height(36.dp).semantics { contentDescription = "İçerikte ileri geri sar" },
                    )
                } else {
                    Text("●  CANLI", color = MavieCyanDot, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 10.dp))
                }
                BoxWithConstraints(Modifier.fillMaxWidth()) {
                    val compactWidth = maxWidth < 600.dp
                    Row(
                        Modifier.fillMaxWidth()
                            .mavieGlassSurface(CircleShape, topColor = Color(0xA6121728), bottomColor = Color(0x8C0B0F1C))
                            .padding(horizontal = 4.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        TextButton(
                            onClick = { trackDialog = "audio"; controlsVisible = true; interactionVersion++ },
                            modifier = Modifier.heightIn(min = 48.dp),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 8.dp),
                        ) {
                            Icon(Icons.Rounded.Audiotrack, null, tint = Color.White, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            val audioLabel = if (playback.audioTracks.isNotEmpty()) "Ses (${playback.audioTracks.size})" else "Ses"
                            Text(audioLabel, color = Color.White, fontSize = 12.sp, maxLines = 1)
                        }
                        TextButton(
                            onClick = { trackDialog = "subtitle"; controlsVisible = true; interactionVersion++ },
                            modifier = Modifier.heightIn(min = 48.dp),
                            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 8.dp),
                        ) {
                            Icon(Icons.Rounded.Subtitles, null, tint = Color.White, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(4.dp))
                            val subLabel = if (playback.subtitleTracks.isNotEmpty()) "Altyazı (${playback.subtitleTracks.size})" else "Altyazı"
                            Text(subLabel, color = Color.White, fontSize = 12.sp, maxLines = 1)
                        }
                        if (compactWidth) {
                            Spacer(Modifier.weight(1f))
                            Box {
                                TooltipBox(
                                    positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
                                    tooltip = { PlainTooltip { Text("Seçenekler") } },
                                    state = rememberTooltipState(),
                                ) {
                                    IconButton(
                                        onClick = { optionsMenuOpen = true; controlsVisible = true; interactionVersion++ },
                                        modifier = Modifier.defaultMinSize(48.dp, 48.dp)
                                            .semantics {
                                                contentDescription = "Seçenekler"
                                                role = Role.Button
                                            },
                                    ) {
                                        Icon(Icons.Rounded.Tune, contentDescription = null, tint = Color.White)
                                    }
                                }
                                DropdownMenu(expanded = optionsMenuOpen, onDismissRequest = { optionsMenuOpen = false }) {
                                    if (!isLive) {
                                        DropdownMenuItem(
                                            leadingIcon = { Icon(Icons.Rounded.Speed, null) },
                                            text = { Text("Oynatma Hızı (${playback.playbackRate}x)") },
                                            onClick = { optionsMenuOpen = false; cyclePlaybackRate() },
                                        )
                                    }
                                    DropdownMenuItem(
                                        leadingIcon = { Icon(Icons.Rounded.AspectRatio, null) },
                                        text = { Text("Ekran Oranı (${if (playback.fillScreen) "Doldur" else "Sığdır"})") },
                                        onClick = { optionsMenuOpen = false; toggleFillScreen() },
                                    )
                                    DropdownMenuItem(
                                        leadingIcon = { Icon(Icons.Rounded.Bedtime, null) },
                                        text = { Text("Uyku Zamanlayıcısı (${if (sleepMinutes > 0) "${sleepMinutes} dk" else "Kapalı"})") },
                                        onClick = { optionsMenuOpen = false; cycleSleepTimer() },
                                    )
                                    if (episodes.isNotEmpty()) {
                                        DropdownMenuItem(
                                            leadingIcon = { Icon(Icons.AutoMirrored.Rounded.List, null) },
                                            text = { Text("Bölümler") },
                                            onClick = { optionsMenuOpen = false; episodeDrawerOpen = true; controlsVisible = true; interactionVersion++ },
                                        )
                                    } else if (nextEpisode != null && !playback.ended) {
                                        DropdownMenuItem(
                                            leadingIcon = { Icon(Icons.Rounded.SkipNext, null) },
                                            text = { Text("Sonraki bölüm") },
                                            onClick = { optionsMenuOpen = false; advanceEpisode() },
                                        )
                                    }
                                }
                            }
                        } else {
                            Row(
                                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                if (!isLive) {
                                    TextButton(
                                        onClick = ::cyclePlaybackRate,
                                        modifier = Modifier.heightIn(min = 48.dp),
                                    ) {
                                        Text("${playback.playbackRate}x", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                    }
                                }
                                TextButton(
                                    onClick = ::toggleFillScreen,
                                    modifier = Modifier.heightIn(min = 48.dp),
                                ) {
                                    Text(if (playback.fillScreen) "Doldur" else "Sığdır", color = Color.White.copy(alpha = .85f), fontSize = 11.sp)
                                }
                                TextButton(
                                    onClick = ::cycleSleepTimer,
                                    modifier = Modifier.heightIn(min = 48.dp),
                                ) {
                                    Text(
                                        if (sleepMinutes > 0) "${sleepMinutes}dk" else "Uyku",
                                        color = if (sleepMinutes > 0) MavieCyanDot else Color.White.copy(alpha = .85f),
                                        fontSize = 11.sp,
                                    )
                                }
                                Spacer(Modifier.weight(1f))
                                if (episodes.isNotEmpty()) {
                                    TextButton(
                                        onClick = { episodeDrawerOpen = true; controlsVisible = true; interactionVersion++ },
                                        modifier = Modifier.heightIn(min = 48.dp),
                                    ) {
                                        Text("Bölümler", color = Color.White, fontSize = 12.sp)
                                    }
                                } else if (nextEpisode != null && !playback.ended) {
                                    TextButton(onClick = ::advanceEpisode, modifier = Modifier.heightIn(min = 48.dp)) {
                                        Text("Sonraki bölüm", color = Color.White, fontSize = 12.sp)
                                    }
                                }
                            }
                        }
                        if (!isTablet) {
                            PlayerControl(
                                icon = if (landscape) Icons.Rounded.FullscreenExit else Icons.Rounded.Fullscreen,
                                label = if (landscape) "Dikey ekrana geç" else "Yatay tam ekran",
                                size = 48,
                            ) { landscape = !landscape; controlsVisible = true; interactionVersion++ }
                        }
                    }
                }
            }
        }
        if (showNext) {
            Box(Modifier.align(Alignment.Center).windowInsetsPadding(WindowInsets.safeDrawing).padding(18.dp)) {
                NextEpisodeCard(nextEpisode, secondsToNext, ::advanceEpisode, { nextDismissed = true })
            }
        }
        playback.error?.let { message ->
            val hint = errorHintFor(playback.errorCode)
            Column(
                Modifier.align(Alignment.Center).padding(24.dp)
                    .mavieGlassSurface(
                        RoundedCornerShape(24.dp),
                        topColor = Color(0xEB181F36),
                        bottomColor = Color(0xEB0E1322),
                    )
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Text("Yayına bağlanamadık", color = Color.White, fontSize = 19.sp, fontWeight = FontWeight.SemiBold)
                Text(
                    message,
                    color = Color(0xFFB9BDC6),
                    fontSize = 13.sp,
                    modifier = Modifier.padding(top = 14.dp, bottom = if (hint != null) 6.dp else 14.dp),
                )
                if (hint != null) {
                    Text(
                        hint,
                        color = MavieMuted,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(bottom = 14.dp),
                    )
                }
                MavieGradientButton(
                    onClick = controller::retry,
                    modifier = Modifier.heightIn(min = 48.dp),
                    shape = RoundedCornerShape(14.dp),
                ) { Text("Yeniden dene", color = Color.White) }
            }
        }
    }
    trackDialog?.let { kind ->
        TrackChoiceDialog(
            title = if (kind == "audio") "Seslendirme ve ses dili" else "Altyazı",
            tracks = if (kind == "audio") playback.audioTracks else playback.subtitleTracks,
            initialLabel = if (kind == "audio") "Varsayılan ses" else "Kapalı",
            initialValue = if (kind == "audio") null else -1,
            selected = if (kind == "audio") playback.audioPreference else playback.subtitlePreference,
            subtitleDelayMs = if (kind == "subtitle") playback.subtitleDelayMs else null,
            onAdjustDelay = { deltaMs -> controller.setSubtitleDelayMs(playback.subtitleDelayMs + deltaMs) },
            onResetDelay = { controller.setSubtitleDelayMs(0L) },
            onDismiss = { trackDialog = null },
            onSelect = { id ->
                if (kind == "audio") controller.selectAudio(id) else controller.selectSubtitle(id)
                trackDialog = null
            },
        )
    }
    if (episodeDrawerOpen && episodes.isNotEmpty()) {
        AlertDialog(
            onDismissRequest = { episodeDrawerOpen = false },
            containerColor = MavieGlassDialogFill,
            shape = RoundedCornerShape(24.dp),
            titleContentColor = Color.White,
            title = { Text("Bölümler", fontSize = 20.sp, fontWeight = FontWeight.SemiBold) },
            text = {
                Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                    episodes.forEach { (epId, epLabel) ->
                        val active = epId == currentEpisodeId
                        Row(
                            Modifier.fillMaxWidth()
                                .heightIn(min = 48.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(if (active) MaviePurple.copy(alpha = .28f) else Color.Transparent)
                                .let { mod ->
                                    if (active) mod.border(1.dp, MavieTurquoise.copy(alpha = 0.5f), RoundedCornerShape(12.dp)) else mod
                                }
                                .clickable { episodeDrawerOpen = false; if (!active) onSelectEpisode(epId) }
                                .padding(horizontal = 10.dp, vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                epLabel,
                                color = if (active) Color.White else Color(0xFFD0D4DC),
                                fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
                                fontSize = 13.sp,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { episodeDrawerOpen = false }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text("Kapat", color = MavieTurquoise)
                }
            },
        )
    }
}

@Composable
private fun NextEpisodeCard(next: UpNextEpisode, seconds: Int, onPlay: () -> Unit, onDismiss: () -> Unit) {
    Column(
        Modifier.widthIn(max = 384.dp)
            .mavieGlassSurface(RoundedCornerShape(22.dp), topColor = Color(0xEB1B233C), bottomColor = Color(0xEB101526))
            .padding(horizontal = 18.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            if (next.artwork.isNotBlank()) {
                AsyncImage(
                    next.artwork, contentDescription = null,
                    modifier = Modifier.size(width = 84.dp, height = 49.dp).clip(RoundedCornerShape(12.dp)),
                    contentScale = ContentScale.Crop,
                )
            }
            Column(Modifier.weight(1f)) {
                Text("Sonraki bölüm · ${seconds.coerceAtLeast(1)} sn", color = Color.White.copy(alpha = .72f), fontSize = 12.sp)
                Text(next.title, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (next.season > 0 && next.number > 0) Text("${next.season}. Sezon · ${next.number}. Bölüm", color = Color.LightGray, fontSize = 11.sp)
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Şimdi değil", color = Color.White) }
            Spacer(Modifier.width(8.dp))
            MavieGradientButton(
                onClick = onPlay,
                modifier = Modifier.heightIn(min = 48.dp),
                shape = RoundedCornerShape(14.dp),
            ) {
                Text("Sonraki bölümü oynat", fontSize = 13.sp, color = Color.White)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlayerControl(
    icon: ImageVector,
    label: String,
    enabled: Boolean = true,
    size: Int = 48,
    prominent: Boolean = false,
    iconSize: Int = 24,
    modifier: Modifier = Modifier,
    onClick: () -> Unit,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    val scale = rememberPressScale(interactionSource)
    TooltipBox(
        positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
        tooltip = { PlainTooltip { Text(label) } },
        state = rememberTooltipState(),
    ) {
        IconButton(
            onClick = onClick,
            enabled = enabled,
            interactionSource = interactionSource,
            modifier = modifier
                .graphicsLayer { scaleX = scale; scaleY = scale }
                .sizeIn(minWidth = 48.dp, minHeight = 48.dp)
                .size(size.dp)
                .clip(CircleShape)
                .background(if (prominent) MavieGlassPillFill else Color.Transparent)
                .let { mod ->
                    when {
                        focused -> mod.border(2.dp, MavieCyanDot, CircleShape)
                        prominent -> mod.border(1.5.dp, MavieBrandDiagonalGradient, CircleShape)
                        else -> mod
                    }
                }
                .semantics {
                    contentDescription = label
                    role = Role.Button
                },
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (enabled) Color.White else Color.White.copy(alpha = .3f),
                modifier = Modifier.size(iconSize.dp),
            )
        }
    }
}

@Composable
private fun TrackChoiceDialog(
    title: String,
    tracks: List<PlaybackTrack>,
    initialLabel: String,
    initialValue: Int?,
    selected: Int?,
    subtitleDelayMs: Long? = null,
    onAdjustDelay: (Long) -> Unit = {},
    onResetDelay: () -> Unit = {},
    onDismiss: () -> Unit,
    onSelect: (Int?) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        titleContentColor = Color.White,
        title = { Text(title, fontSize = 20.sp, fontWeight = FontWeight.SemiBold) },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                TrackChoiceRow(initialLabel, selected == initialValue) { onSelect(initialValue) }
                tracks.forEach { track -> TrackChoiceRow(track.label, selected == track.id) { onSelect(track.id) } }
                if (tracks.isEmpty()) Text("Bu kaynakta ek parça bulunmuyor.", color = Color(0xFF999FAA), fontSize = 12.sp, modifier = Modifier.padding(top = 12.dp))
                if (subtitleDelayMs != null) {
                    HorizontalDivider(Modifier.padding(vertical = 10.dp), color = Color.White.copy(alpha = .12f))
                    Text("Altyazı senkronu: ${"%.1f".format(subtitleDelayMs / 1000.0)} sn", color = Color(0xFFD0D4DC), fontSize = 12.sp)
                    Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { onAdjustDelay(-500L) }, modifier = Modifier.heightIn(min = 48.dp)) { Text("-0.5 sn", color = Color.White) }
                        TextButton(onClick = onResetDelay, modifier = Modifier.heightIn(min = 48.dp)) { Text("Sıfırla", color = MavieTurquoise) }
                        TextButton(onClick = { onAdjustDelay(500L) }, modifier = Modifier.heightIn(min = 48.dp)) { Text("+0.5 sn", color = Color.White) }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) {
                Text("Kapat", color = MavieTurquoise)
            }
        },
    )
}

@Composable
private fun TrackChoiceRow(label: String, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClick = onClick).padding(vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = onClick, colors = RadioButtonDefaults.colors(selectedColor = MavieTurquoise, unselectedColor = Color(0xFF646B78)))
        Text(label, color = Color.White, fontSize = 13.sp, modifier = Modifier.weight(1f).padding(end = 6.dp))
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
