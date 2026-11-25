package app.mavie.player.ui

import android.app.UiModeManager
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex

const val AMAZON_FIRE_TV_FEATURE = "amazon.hardware.fire_tv"

val MavieTvFocusBrush: Brush = Brush.linearGradient(
    listOf(MaviePurple, MavieBlue, MavieTurquoise),
)

val LocalIsTv = staticCompositionLocalOf { false }

enum class NavigationChromeMode {
    BOTTOM_BAR,
    NAVIGATION_RAIL,
    TV_TOP_BAR,
}

fun isTelevisionUiMode(uiMode: Int): Boolean =
    (uiMode and Configuration.UI_MODE_TYPE_MASK) == Configuration.UI_MODE_TYPE_TELEVISION

fun isTelevisionEnvironment(
    uiModeType: Int,
    hasLeanbackFeature: Boolean,
    hasFireTvFeature: Boolean = false,
): Boolean = isTelevisionUiMode(uiModeType) || hasLeanbackFeature || hasFireTvFeature

fun isTelevisionDevice(context: Context): Boolean {
    val uiModeType = runCatching {
        val uiModeManager = context.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        uiModeManager?.currentModeType ?: context.resources.configuration.uiMode
    }.getOrDefault(Configuration.UI_MODE_TYPE_UNDEFINED)
    val packageManager = runCatching { context.packageManager }.getOrNull()
    val hasLeanback = runCatching {
        packageManager?.hasSystemFeature(PackageManager.FEATURE_LEANBACK) == true
    }.getOrDefault(false)
    val hasFireTv = runCatching {
        packageManager?.hasSystemFeature(AMAZON_FIRE_TV_FEATURE) == true
    }.getOrDefault(false)
    return isTelevisionEnvironment(
        uiModeType = uiModeType,
        hasLeanbackFeature = hasLeanback,
        hasFireTvFeature = hasFireTv,
    )
}

@Composable
fun rememberIsTelevision(): Boolean {
    val context = LocalContext.current
    return remember(context) { isTelevisionDevice(context) }
}

fun isDpadConfirmKey(key: Key): Boolean = when (key) {
    Key.DirectionCenter, Key.Enter, Key.NumPadEnter -> true
    else -> false
}

fun isDpadNavigationKey(key: Key): Boolean = when (key) {
    Key.DirectionUp, Key.DirectionDown, Key.DirectionLeft, Key.DirectionRight -> true
    else -> false
}

fun isTvBackKey(key: Key): Boolean = when (key) {
    Key.Back, Key.Escape -> true
    else -> false
}

fun stepTvTabIndex(currentIndex: Int, delta: Int, tabCount: Int): Int {
    if (tabCount <= 0) return 0
    val clampedCurrent = currentIndex.coerceIn(0, tabCount - 1)
    return (clampedCurrent + delta).coerceIn(0, tabCount - 1)
}

fun tvFocusScaleTarget(
    focused: Boolean,
    pressed: Boolean,
    reducedMotion: Boolean,
    focusedScale: Float = 1.04f,
    pressedScale: Float = 0.96f,
): Float = when {
    reducedMotion -> 1f
    pressed -> pressedScale
    focused -> focusedScale
    else -> 1f
}

fun resolveNavigationChromeMode(isTv: Boolean, widthDp: Int): NavigationChromeMode = when {
    isTv -> NavigationChromeMode.TV_TOP_BAR
    widthDp >= 600 -> NavigationChromeMode.NAVIGATION_RAIL
    else -> NavigationChromeMode.BOTTOM_BAR
}

fun catalogGridMinCellWidthDp(isTv: Boolean, isTablet: Boolean): Int = when {
    isTv -> 168
    isTablet -> 144
    else -> 108
}

fun mediaRowCardWidthDp(isTv: Boolean): Int = if (isTv) 154 else 112

fun continueCardWidthDp(isTv: Boolean): Int = if (isTv) 232 else 168

/**
 * Reusable TV / D-Pad focus modifier built purely on standard Jetpack Compose Foundation.
 *
 * - Pass [onClick] when making a plain layout container (Box/Row/Column) focusable & clickable;
 *   it handles both pointer clicks and D-Pad confirm keys (Center / Enter / NumPadEnter).
 * - Set [addFocusable] = false (with [onClick] = null) when wrapping an already-focusable
 *   Material3 component (Button, OutlinedButton, TextButton, Card, IconButton, FilterChip)
 *   so there is never a duplicate focus stop while still applying the 1.04x focus scale,
 *   z-index lift, glow shadow, and #7C3AED -> #06B6D4 focus border.
 */
@Composable
fun Modifier.mavieTvFocusable(
    enabled: Boolean = true,
    shape: Shape = RoundedCornerShape(16.dp),
    focusedScale: Float = 1.04f,
    showFocusBorder: Boolean = true,
    showFocusShadow: Boolean = true,
    addFocusable: Boolean = true,
    role: Role? = null,
    onClickLabel: String? = null,
    onFocusChange: ((Boolean) -> Unit)? = null,
    onClick: (() -> Unit)? = null,
): Modifier {
    val reducedMotion = rememberReducedMotion()
    var focused by remember { mutableStateOf(false) }
    val interactionSource = remember { MutableInteractionSource() }
    val pressed by interactionSource.collectIsPressedAsState()
    val scale by animateFloatAsState(
        targetValue = tvFocusScaleTarget(
            focused = focused,
            pressed = pressed,
            reducedMotion = reducedMotion,
            focusedScale = focusedScale,
        ),
        animationSpec = if (reducedMotion) snap() else spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessMediumLow,
        ),
        label = "mavie-tv-focus-scale",
    )
    val visual = this
        .zIndex(if (focused) 1f else 0f)
        .graphicsLayer {
            scaleX = scale
            scaleY = scale
        }
        .then(
            if (focused && showFocusShadow) {
                Modifier.shadow(
                    elevation = 14.dp,
                    shape = shape,
                    clip = false,
                    ambientColor = MaviePurple.copy(alpha = 0.55f),
                    spotColor = MavieTurquoise.copy(alpha = 0.65f),
                )
            } else {
                Modifier
            }
        )
        .then(
            if (focused && showFocusBorder) {
                Modifier.border(width = 2.5.dp, brush = MavieTvFocusBrush, shape = shape)
            } else {
                Modifier
            }
        )
        .onFocusChanged { state ->
            val next = state.isFocused
            if (focused != next) {
                focused = next
                onFocusChange?.invoke(next)
            }
        }

    return when {
        onClick != null -> visual
            .clip(shape)
            .onPreviewKeyEvent { keyEvent ->
                if (
                    enabled &&
                    keyEvent.type == KeyEventType.KeyDown &&
                    keyEvent.nativeKeyEvent.repeatCount == 0 &&
                    isDpadConfirmKey(keyEvent.key)
                ) {
                    onClick()
                    true
                } else {
                    false
                }
            }
            .clickable(
                enabled = enabled,
                interactionSource = interactionSource,
                indication = LocalIndication.current,
                role = role,
                onClickLabel = onClickLabel,
                onClick = onClick,
            )
        addFocusable -> visual.focusable(enabled = enabled, interactionSource = interactionSource)
        else -> visual
    }
}

@Composable
internal fun MavieFilterChip(
    selected: Boolean,
    onClick: () -> Unit,
    label: @Composable () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    FilterChip(
        selected = selected,
        onClick = onClick,
        enabled = enabled,
        interactionSource = interactionSource,
        label = label,
        shape = CircleShape,
        modifier = modifier.mavieTvFocusable(
            enabled = enabled,
            shape = CircleShape,
            showFocusBorder = false,
            showFocusShadow = false,
            addFocusable = false,
        ),
        colors = FilterChipDefaults.filterChipColors(
            containerColor = if (focused) Color(0xCC222B4A) else Color(0x80182038),
            labelColor = if (focused) Color.White else MavieMuted,
            selectedContainerColor = MaviePurple.copy(alpha = 0.90f),
            selectedLabelColor = Color.White,
        ),
        border = if (focused) {
            BorderStroke(2.5.dp, MavieTvFocusBrush)
        } else {
            FilterChipDefaults.filterChipBorder(
                enabled = enabled,
                selected = selected,
                borderColor = Color.White.copy(alpha = 0.14f),
                selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
            )
        },
    )
}

@Composable
internal fun MavieTvTopNavTab(
    label: String,
    icon: ImageVector,
    selected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    leadingContent: (@Composable () -> Unit)? = null,
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = Color.Transparent,
        border = if (focused) {
            BorderStroke(2.5.dp, MavieTvFocusBrush)
        } else {
            BorderStroke(
                width = 1.dp,
                color = if (selected) MavieCyanDot.copy(alpha = 0.72f) else Color.White.copy(alpha = 0.14f),
            )
        },
        modifier = modifier
            .heightIn(min = 48.dp)
            .mavieTvFocusable(
                shape = CircleShape,
                showFocusBorder = false,
                addFocusable = false,
                onFocusChange = { focused = it },
            )
            .semantics { this.selected = selected },
    ) {
        Row(
            modifier = Modifier
                .background(
                    brush = when {
                        selected -> MavieBrandGradient
                        focused -> Brush.horizontalGradient(
                            listOf(MaviePurple.copy(alpha = 0.42f), MavieTurquoise.copy(alpha = 0.30f)),
                        )
                        else -> Brush.horizontalGradient(listOf(Color(0x99182038), Color(0x9912182B)))
                    },
                )
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (leadingContent != null) {
                leadingContent()
            } else {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = if (selected || focused) Color.White else MavieMuted,
                    modifier = Modifier.size(20.dp),
                )
            }
            Text(
                text = label,
                color = if (selected || focused) Color.White else MavieMuted,
                fontSize = 14.sp,
                fontWeight = if (selected || focused) FontWeight.Bold else FontWeight.Medium,
                maxLines = 1,
                softWrap = false,
            )
        }
    }
}
