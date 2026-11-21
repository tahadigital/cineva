package app.mavie.player.ui

import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.interaction.InteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
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
val MavieCoral = MaviePurple
val MavieAmber = MavieTurquoise
val MavieBackground = Color(0xFF0A0D16)
val MaviePanel = Color(0xFF121726)
val MavieMuted = Color(0xFFB3BCE2)

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
            extraSmall = RoundedCornerShape(4.dp), small = RoundedCornerShape(6.dp),
            medium = RoundedCornerShape(8.dp), large = RoundedCornerShape(10.dp),
        ),
    ) {
        Surface(Modifier.fillMaxSize(), color = MavieBackground, contentColor = Color.White, content = content)
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
    val scale by animateFloatAsState(
        targetValue = if (!reducedMotion && pressed) 0.97f else 1f,
        animationSpec = tween(durationMillis = if (reducedMotion) 0 else 110),
        label = "mavie-press-scale",
    )
    return scale
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
fun MavieWordmark(modifier: Modifier = Modifier, large: Boolean = false) {
    Row(
        modifier = modifier.height(if (large) 58.dp else 34.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(if (large) 12.dp else 8.dp),
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
                drawCircle(color = Color(0xFF22D3EE), radius = 5f, center = Offset(92f, 60f))
            }
        }
        Text(
            text = "mavie",
            fontSize = if (large) 30.sp else 20.sp,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = (-0.8).sp,
            color = Color.White,
        )
        Text(
            text = ".",
            fontSize = if (large) 32.sp else 22.sp,
            fontWeight = FontWeight.Black,
            color = MavieTurquoise,
            modifier = Modifier.padding(start = 0.dp),
        )
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
                    MavieCoral.copy(alpha = glowAlpha),
                    Color(0xFF1D1621),
                    Color(0xFF0B0D12),
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
                        listOf(MavieCoral.copy(alpha = 0.22f * alpha), Color.Transparent),
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
                    }
                }
            }
        }
    }
}
