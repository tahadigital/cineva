package app.cineva.player.ui

import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

val CinevaCoral = Color(0xFFFF4B45)
val CinevaAmber = Color(0xFFFF9933)
val CinevaBackground = Color(0xFF0E1015)
val CinevaPanel = Color(0xFF161922)
val CinevaMuted = Color(0xFFB3B6C2)

// Semantic color aliases preserved for internal UI modules.
val AkisRed = CinevaCoral
val AkisBackground = CinevaBackground
val AkisPanel = CinevaPanel
val AkisMuted = CinevaMuted

private val CinevaColors = darkColorScheme(
    primary = CinevaCoral,
    onPrimary = Color.White,
    primaryContainer = Color(0xFF5A1D20),
    onPrimaryContainer = Color.White,
    secondary = Color.White,
    onSecondary = Color.Black,
    secondaryContainer = Color(0xFF282D3A),
    background = CinevaBackground,
    onBackground = Color.White,
    surface = CinevaPanel,
    onSurface = Color.White,
    surfaceVariant = Color(0xFF232836),
    onSurfaceVariant = CinevaMuted,
    outline = Color(0xFF4B5163),
    error = Color(0xFFFFB4AB),
)

@Composable
fun AkisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = CinevaColors,
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
        Surface(Modifier.fillMaxSize(), color = CinevaBackground, contentColor = Color.White, content = content)
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
fun AkisWordmark(modifier: Modifier = Modifier, large: Boolean = false) {
    Row(
        modifier = modifier.height(if (large) 58.dp else 34.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(if (large) 12.dp else 8.dp),
    ) {
        Canvas(
            Modifier.fillMaxHeight().aspectRatio(1f)
                .semantics { contentDescription = "Cineva logosu" }
        ) {
            val s = size.minDimension / 120f
            scale(s, s, pivot = Offset.Zero) {
                drawArc(
                    brush = Brush.linearGradient(listOf(CinevaCoral, CinevaAmber)),
                    startAngle = 42f,
                    sweepAngle = 276f,
                    useCenter = false,
                    topLeft = Offset(22f, 22f),
                    size = Size(76f, 76f),
                    style = Stroke(width = 17f, cap = StrokeCap.Round),
                )
                drawPath(CinevaPlayPath, color = Color.White)
                drawPath(CinevaPlayPath, color = Color.White, style = Stroke(width = 3.5f, join = StrokeJoin.Round))
            }
        }
        Text(
            text = "cineva",
            fontSize = if (large) 30.sp else 20.sp,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = (-0.8).sp,
            color = Color.White,
        )
        Text(
            text = ".",
            fontSize = if (large) 32.sp else 22.sp,
            fontWeight = FontWeight.Black,
            color = CinevaCoral,
            modifier = Modifier.padding(start = 0.dp),
        )
    }
}

private val CinevaPlayPath = Path().apply {
    moveTo(52f, 44f)
    lineTo(82f, 60f)
    lineTo(52f, 76f)
    close()
}

@Composable
fun AkisLaunchScreen(onFinished: () -> Unit, reducedMotion: Boolean = rememberReducedMotion()) {
    val latestFinished = rememberUpdatedState(onFinished)
    val progress = remember { Animatable(0f) }

    LaunchedEffect(reducedMotion) {
        if (reducedMotion) delay(120)
        else progress.animateTo(1f, tween(680, easing = FastOutSlowInEasing))
        latestFinished.value()
    }

    Box(
        Modifier.fillMaxSize().background(
            Brush.radialGradient(listOf(Color(0xFF1D1621), Color(0xFF0B0D12)))
        ),
        contentAlignment = Alignment.Center,
    ) {
        if (reducedMotion) {
            AkisWordmark(large = true)
        } else {
            val scaleFactor = 0.78f + progress.value * 0.24f
            val alpha = (1f - ((progress.value - 0.8f) / 0.2f).coerceIn(0f, 1f))
            Canvas(Modifier.fillMaxSize()) {
                val base = size.minDimension * 0.22f * scaleFactor
                val center = Offset(size.width / 2f, size.height / 2f)
                translate(center.x - base / 2f, center.y - base / 2f) {
                    val unit = base / 120f
                    scale(unit, unit, pivot = Offset.Zero) {
                        drawArc(
                            brush = Brush.linearGradient(listOf(CinevaCoral, CinevaAmber)),
                            startAngle = 42f,
                            sweepAngle = 276f * progress.value.coerceAtLeast(0.15f),
                            useCenter = false,
                            topLeft = Offset(22f, 22f),
                            size = Size(76f, 76f),
                            style = Stroke(width = 16f, cap = StrokeCap.Round),
                            alpha = alpha,
                        )
                        drawPath(CinevaPlayPath, color = Color.White.copy(alpha = alpha * progress.value))
                    }
                }
            }
        }
    }
}
