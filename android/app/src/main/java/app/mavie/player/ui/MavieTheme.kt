package app.mavie.player.ui

import android.os.Build
import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

val MaviePurple = Color(0xFF7C3AED)
val MavieBlue = Color(0xFF3B82F6)
val MavieTurquoise = Color(0xFF06B6D4)
val MavieCyanDot = Color(0xFF22D3EE)
val MavieLaunchIndigo = Color(0xFF131932)
val MavieCoral = MaviePurple
val MavieAmber = MavieTurquoise
val MavieBackground = Color(0xFF0A0D16)
val MaviePanel = Color(0xFF121726)
val MavieMuted = Color(0xFFB3BCE2)

val MavieGlassFillTop = Color(0xCC192138)
val MavieGlassFillBottom = Color(0xB30E1322)
val MavieGlassPillFill = Color(0x9E171F36)
val MavieGlassDialogFill = Color(0xE6121728)

val MavieBrandGradient = Brush.horizontalGradient(listOf(MaviePurple, MavieBlue, MavieTurquoise))
val MavieBrandDiagonalGradient = Brush.linearGradient(listOf(MaviePurple, MavieBlue, MavieTurquoise))
val MavieSpecularBorderBrush = Brush.verticalGradient(
    listOf(Color.White.copy(alpha = 0.24f), Color.White.copy(alpha = 0.06f))
)
val MavieSpecularSheenBrush = Brush.verticalGradient(
    0f to Color.White.copy(alpha = 0.13f),
    0.38f to Color.White.copy(alpha = 0.03f),
    1f to Color.Transparent,
)

private val MavieColors = darkColorScheme(
    primary = MaviePurple,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF281A52),
    onPrimaryContainer = Color.White,
    secondary = MavieTurquoise,
    onSecondary = Color.Black,
    secondaryContainer = Color(0xFF1D263B),
    background = MavieBackground,
    onBackground = Color.White,
    surface = MaviePanel,
    onSurface = Color.White,
    surfaceVariant = Color(0xFF1E2538),
    onSurfaceVariant = MavieMuted,
    outline = Color(0xFF434E6B),
    error = Color(0xFFFFB4AB),
)

@Composable
fun MavieTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = MavieColors,
        typography = Typography(
            displaySmall = Typography().displaySmall.copy(fontWeight = FontWeight.ExtraBold, letterSpacing = (-1.1).sp),
            headlineLarge = Typography().headlineLarge.copy(fontWeight = FontWeight.ExtraBold, letterSpacing = (-.7).sp),
            titleLarge = Typography().titleLarge.copy(fontWeight = FontWeight.Bold, letterSpacing = (-.3).sp),
            titleMedium = Typography().titleMedium.copy(fontWeight = FontWeight.Bold),
            bodyMedium = Typography().bodyMedium.copy(lineHeight = 20.sp),
            labelLarge = Typography().labelLarge.copy(fontWeight = FontWeight.Bold),
        ),
        shapes = Shapes(
            extraSmall = RoundedCornerShape(12.dp),
            small = RoundedCornerShape(16.dp),
            medium = RoundedCornerShape(20.dp),
            large = RoundedCornerShape(24.dp),
        ),
    ) {
        Surface(Modifier.fillMaxSize(), color = MavieBackground, contentColor = Color.White, content = content)
    }
}

internal fun Modifier.mavieGlassSurface(
    shape: Shape = RoundedCornerShape(20.dp),
    topColor: Color = MavieGlassFillTop,
    bottomColor: Color = MavieGlassFillBottom,
    focused: Boolean = false,
): Modifier = this
    .clip(shape)
    .background(Brush.verticalGradient(listOf(topColor, bottomColor)), shape)
    .background(MavieSpecularSheenBrush, shape)
    .border(
        width = if (focused) 2.dp else 1.dp,
        brush = if (focused) MavieBrandDiagonalGradient else MavieSpecularBorderBrush,
        shape = shape,
    )

@Composable
internal fun MavieAmbientBackdrop(modifier: Modifier = Modifier) {
    val reducedMotion = rememberReducedMotion()
    val orbBlur = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !reducedMotion) {
        Modifier.blur(72.dp)
    } else {
        Modifier
    }
    Box(modifier.fillMaxSize().background(MavieBackground)) {
        Box(
            Modifier
                .align(Alignment.TopStart)
                .offset(x = (-70).dp, y = (-60).dp)
                .size(280.dp)
                .then(orbBlur)
                .background(
                    Brush.radialGradient(listOf(MaviePurple.copy(alpha = 0.34f), Color.Transparent)),
                    CircleShape,
                )
        )
        Box(
            Modifier
                .align(Alignment.TopEnd)
                .offset(x = 80.dp, y = 40.dp)
                .size(260.dp)
                .then(orbBlur)
                .background(
                    Brush.radialGradient(listOf(MavieTurquoise.copy(alpha = 0.24f), Color.Transparent)),
                    CircleShape,
                )
        )
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .offset(y = 120.dp)
                .size(340.dp)
                .then(orbBlur)
                .background(
                    Brush.radialGradient(listOf(MavieBlue.copy(alpha = 0.18f), Color.Transparent)),
                    CircleShape,
                )
        )
    }
}

@Composable
internal fun rememberReducedMotion(): Boolean {
    val context = LocalContext.current
    return remember(context) {
        runCatching {
            Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        }.getOrDefault(false)
    }
}

@Composable
internal fun rememberPressScale(
    interactionSource: InteractionSource,
    reducedMotion: Boolean = rememberReducedMotion(),
): Float {
    val pressed by interactionSource.collectIsPressedAsState()
    val focused by interactionSource.collectIsFocusedAsState()
    val scale by animateFloatAsState(
        targetValue = when {
            reducedMotion -> 1f
            pressed -> 0.96f
            focused -> 1.04f
            else -> 1f
        },
        animationSpec = if (reducedMotion) snap() else spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessMediumLow,
        ),
        label = "mavie-press-scale",
    )
    return scale
}

@Composable
internal fun MavieGradientButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    shape: Shape = RoundedCornerShape(16.dp),
    contentPadding: PaddingValues = ButtonDefaults.ContentPadding,
    content: @Composable RowScope.() -> Unit,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    val scale = rememberPressScale(interactionSource)
    Button(
        onClick = onClick,
        enabled = enabled,
        interactionSource = interactionSource,
        shape = shape,
        contentPadding = contentPadding,
        elevation = ButtonDefaults.buttonElevation(0.dp, 0.dp, 0.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Color.Transparent,
            contentColor = Color.White,
            disabledContainerColor = Color.Transparent,
            disabledContentColor = Color.White.copy(alpha = 0.45f),
        ),
        modifier = modifier
            .heightIn(min = 48.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(shape)
            .background(
                brush = if (enabled) MavieBrandGradient else SolidColor(Color(0x4D1E263D)),
                shape = shape,
            )
            .border(
                width = if (focused) 2.dp else 1.dp,
                color = if (focused) Color.White.copy(alpha = 0.85f) else Color.White.copy(alpha = 0.24f),
                shape = shape,
            ),
        content = content,
    )
}

@Composable
internal fun MavieGlassPillButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    shape: Shape = RoundedCornerShape(16.dp),
    contentPadding: PaddingValues = ButtonDefaults.ContentPadding,
    content: @Composable RowScope.() -> Unit,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    val scale = rememberPressScale(interactionSource)
    Button(
        onClick = onClick,
        enabled = enabled,
        interactionSource = interactionSource,
        shape = shape,
        contentPadding = contentPadding,
        elevation = ButtonDefaults.buttonElevation(0.dp, 0.dp, 0.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = Color.Transparent,
            contentColor = Color.White,
            disabledContainerColor = Color.Transparent,
            disabledContentColor = Color.White.copy(alpha = 0.45f),
        ),
        modifier = modifier
            .heightIn(min = 48.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .clip(shape)
            .background(MavieGlassPillFill, shape)
            .background(MavieSpecularSheenBrush, shape)
            .border(
                width = if (focused) 2.dp else 1.dp,
                brush = if (focused) MavieBrandDiagonalGradient else MavieSpecularBorderBrush,
                shape = shape,
            ),
        content = content,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun MavieTooltipIconButton(
    label: String,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    tint: Color = Color.White,
    enabled: Boolean = true,
) {
    TooltipBox(
        positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
        tooltip = { PlainTooltip { Text(label) } },
        state = rememberTooltipState(),
    ) {
        IconButton(
            onClick = onClick,
            enabled = enabled,
            modifier = modifier
                .defaultMinSize(minWidth = 48.dp, minHeight = 48.dp)
                .semantics { role = Role.Button },
        ) {
            Icon(
                imageVector = icon,
                contentDescription = label,
                tint = if (enabled) tint else tint.copy(alpha = 0.38f),
            )
        }
    }
}

@Composable
fun MavieWordmark(modifier: Modifier = Modifier, large: Boolean = false, compact: Boolean = false) {
    val height = when {
        large -> 58.dp
        compact -> 28.dp
        else -> 34.dp
    }
    val spacing = when {
        large -> 12.dp
        compact -> 6.dp
        else -> 8.dp
    }
    Row(
        modifier = modifier.height(height),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(spacing),
    ) {
        Canvas(
            Modifier.fillMaxHeight().aspectRatio(1f)
                .semantics { contentDescription = "Mavie logosu" }
        ) {
            val s = size.minDimension / 120f
            scale(s, s, pivot = Offset.Zero) {
                drawArc(
                    brush = Brush.linearGradient(listOf(MaviePurple, MavieBlue, MavieTurquoise)),
                    startAngle = 42f,
                    sweepAngle = 276f,
                    useCenter = false,
                    topLeft = Offset(22f, 22f),
                    size = Size(76f, 76f),
                    style = Stroke(width = 17f, cap = StrokeCap.Round),
                )
                drawPath(MaviePlayPath, color = Color.White)
                drawPath(MaviePlayPath, color = Color.White, style = Stroke(width = 3.5f, join = StrokeJoin.Round))
                drawCircle(color = MavieCyanDot, radius = 5f, center = Offset(92f, 60f))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = "mavie",
                fontSize = when {
                    large -> 30.sp
                    compact -> 17.sp
                    else -> 20.sp
                },
                fontWeight = FontWeight.ExtraBold,
                letterSpacing = (-0.8).sp,
                color = Color.White,
                maxLines = 1,
                softWrap = false,
            )
            Text(
                text = ".",
                fontSize = when {
                    large -> 32.sp
                    compact -> 19.sp
                    else -> 22.sp
                },
                fontWeight = FontWeight.Black,
                color = MavieCyanDot,
                maxLines = 1,
                softWrap = false,
                modifier = Modifier.padding(start = 0.dp),
            )
        }
    }
}

private val MaviePlayPath = Path().apply {
    moveTo(52f, 44f)
    lineTo(82f, 60f)
    lineTo(52f, 76f)
    close()
}

@Composable
fun MavieLaunchScreen(onFinished: () -> Unit, reducedMotion: Boolean = rememberReducedMotion()) {
    val latestFinished = rememberUpdatedState(onFinished)
    val progress = remember { Animatable(0f) }

    LaunchedEffect(reducedMotion) {
        if (reducedMotion) delay(120)
        else progress.animateTo(1f, tween(720, easing = FastOutSlowInEasing))
        latestFinished.value()
    }

    val glowAlpha = if (reducedMotion) 0.25f else {
        val pulse = rememberInfiniteTransition(label = "mavie-launch-glow")
        pulse.animateFloat(
            initialValue = 0.16f,
            targetValue = 0.36f,
            animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse),
            label = "glow-alpha",
        ).value
    }

    Box(
        Modifier.fillMaxSize().background(
            Brush.radialGradient(
                listOf(
                    MaviePurple.copy(alpha = glowAlpha),
                    MavieLaunchIndigo,
                    Color(0xFF0A0D18),
                ),
            ),
        ),
        contentAlignment = Alignment.Center,
    ) {
        if (reducedMotion) {
            MavieWordmark(large = true)
        } else {
            val scaleFactor = 0.8f + progress.value * 0.22f
            val alpha = (1f - ((progress.value - 0.82f) / 0.18f).coerceIn(0f, 1f))
            Canvas(Modifier.fillMaxSize()) {
                val base = size.minDimension * 0.24f * scaleFactor
                val center = Offset(size.width / 2f, size.height / 2f)
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(MaviePurple.copy(alpha = 0.24f * alpha), Color.Transparent),
                        center = center,
                        radius = base * 1.4f,
                    ),
                    radius = base * 1.4f,
                    center = center,
                )
                translate(center.x - base / 2f, center.y - base / 2f) {
                    val unit = base / 120f
                    scale(unit, unit, pivot = Offset.Zero) {
                        drawArc(
                            brush = Brush.linearGradient(listOf(MaviePurple, MavieBlue, MavieTurquoise)),
                            startAngle = 42f,
                            sweepAngle = 276f * progress.value.coerceAtLeast(0.15f),
                            useCenter = false,
                            topLeft = Offset(22f, 22f),
                            size = Size(76f, 76f),
                            style = Stroke(width = 16f, cap = StrokeCap.Round),
                            alpha = alpha,
                        )
                        drawPath(MaviePlayPath, color = Color.White.copy(alpha = alpha * progress.value))
                        drawCircle(
                            color = MavieCyanDot.copy(alpha = alpha * progress.value),
                            radius = 5f,
                            center = Offset(92f, 60f),
                        )
                    }
                }
            }
        }
    }
}
