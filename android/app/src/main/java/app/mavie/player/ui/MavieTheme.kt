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
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
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
import androidx.compose.ui.zIndex
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
    val isTv = rememberIsTelevision()
    CompositionLocalProvider(LocalIsTv provides isTv) {
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
        width = if (focused) 2.5.dp else 1.dp,
        brush = if (focused) MavieTvFocusBrush else MavieSpecularBorderBrush,
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
            .zIndex(if (focused) 1f else 0f)
            .heightIn(min = 48.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .then(
                if (focused) {
                    Modifier.shadow(
                        elevation = 14.dp,
                        shape = shape,
                        clip = false,
                        ambientColor = MaviePurple.copy(alpha = 0.6f),
                        spotColor = MavieTurquoise.copy(alpha = 0.7f),
                    )
                } else {
                    Modifier
                }
            )
            .clip(shape)
            .background(
                brush = if (enabled) MavieBrandGradient else SolidColor(Color(0x4D1E263D)),
                shape = shape,
            )
            .border(
                width = if (focused) 2.5.dp else 1.dp,
                color = if (focused) Color.White.copy(alpha = 0.92f) else Color.White.copy(alpha = 0.24f),
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
            .zIndex(if (focused) 1f else 0f)
            .heightIn(min = 48.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .then(
                if (focused) {
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
            .clip(shape)
            .background(MavieGlassPillFill, shape)
            .background(MavieSpecularSheenBrush, shape)
            .border(
                width = if (focused) 2.5.dp else 1.dp,
                brush = if (focused) MavieTvFocusBrush else MavieSpecularBorderBrush,
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
                .zIndex(if (focused) 1f else 0f)
                .defaultMinSize(minWidth = 48.dp, minHeight = 48.dp)
                .graphicsLayer { scaleX = scale; scaleY = scale }
                .then(
                    if (focused) {
                        Modifier
                            .shadow(
                                elevation = 12.dp,
                                shape = CircleShape,
                                clip = false,
                                ambientColor = MaviePurple.copy(alpha = 0.55f),
                                spotColor = MavieTurquoise.copy(alpha = 0.65f),
                            )
                            .background(MavieGlassPillFill, CircleShape)
                            .border(2.5.dp, MavieTvFocusBrush, CircleShape)
                    } else {
                        Modifier
                    }
                )
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
            val s = size.minDimension / 256f
            val strokeBoost = if (compact) 1.15f else 1.0f
            scale(s, s, pivot = Offset.Zero) {
                drawMavieMonogram(alpha = 1f, strokeScale = strokeBoost)
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

private fun Path.addCubicEllipse(cx: Float, cy: Float, rx: Float, ry: Float, ccw: Boolean = false) {
    val k = 0.55228475f
    val kx = rx * k
    val ky = ry * k
    moveTo(cx, cy - ry)
    if (!ccw) {
        cubicTo(cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)
        cubicTo(cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)
        cubicTo(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)
        cubicTo(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry)
    } else {
        cubicTo(cx - kx, cy - ry, cx - rx, cy - ky, cx - rx, cy)
        cubicTo(cx - rx, cy + ky, cx - kx, cy + ry, cx, cy + ry)
        cubicTo(cx + kx, cy + ry, cx + rx, cy + ky, cx + rx, cy)
        cubicTo(cx + rx, cy - ky, cx + kx, cy - ry, cx, cy - ry)
    }
    close()
}

private val MavieMMonogramPath = Path().apply {
    moveTo(23.5f, 40.0f)
    cubicTo(23.5f, 32.5f, 27.2f, 29.2f, 34.5f, 28.5f)
    cubicTo(56.5f, 26.2f, 77.5f, 26.5f, 95.5f, 29.0f)
    cubicTo(101.0f, 29.8f, 103.8f, 32.8f, 105.4f, 38.0f)
    lineTo(129.0f, 128.5f)
    lineTo(152.6f, 38.0f)
    cubicTo(154.2f, 32.8f, 157.0f, 29.8f, 162.5f, 29.0f)
    cubicTo(180.5f, 26.5f, 201.5f, 26.2f, 223.5f, 28.5f)
    cubicTo(230.8f, 29.2f, 234.5f, 32.5f, 234.5f, 40.0f)
    lineTo(234.5f, 207.5f)
    cubicTo(234.5f, 218.5f, 227.5f, 224.5f, 216.0f, 224.5f)
    lineTo(195.5f, 224.5f)
    cubicTo(188.5f, 224.5f, 184.5f, 220.2f, 184.5f, 213.0f)
    lineTo(184.5f, 110.0f)
    lineTo(180.0f, 110.0f)
    lineTo(150.5f, 214.0f)
    cubicTo(148.5f, 221.0f, 143.5f, 224.5f, 136.0f, 224.5f)
    lineTo(123.5f, 224.5f)
    cubicTo(113.0f, 224.5f, 107.5f, 219.0f, 107.5f, 208.5f)
    lineTo(107.5f, 181.5f)
    cubicTo(107.5f, 160.61f, 96.99f, 141.42f, 80.18f, 131.61f)
    cubicTo(63.36f, 121.81f, 42.99f, 122.98f, 27.20f, 134.66f)
    cubicTo(24.80f, 136.44f, 23.50f, 134.60f, 23.50f, 130.00f)
    close()
}

private val MavieOOuterPath = Path().apply {
    addCubicEllipse(56.0f, 181.5f, 35.0f, 39.0f, ccw = false)
}

private val MavieOInnerPath = Path().apply {
    addCubicEllipse(56.0f, 181.5f, 13.8f, 15.6f, ccw = false)
}

private val MavieODonutPath = Path().apply {
    fillType = PathFillType.EvenOdd
    addCubicEllipse(56.0f, 181.5f, 35.0f, 39.0f, ccw = false)
    addCubicEllipse(56.0f, 181.5f, 13.8f, 15.6f, ccw = true)
}

private val MavieObsidianBrush = Brush.linearGradient(
    colors = listOf(Color(0xFF161C32), Color(0xFF090D18), Color(0xFF03050A)),
    start = Offset(46f, 26f),
    end = Offset(210f, 226f),
)

private val MavieMRimBrush = Brush.linearGradient(
    0.0f to MaviePurple,
    0.22f to MavieBlue,
    0.50f to MavieTurquoise,
    0.78f to MavieBlue,
    1.0f to MaviePurple,
    start = Offset(10f, 112f),
    end = Offset(246f, 144f),
)

private val MavieORimBrush = Brush.linearGradient(
    colors = listOf(MaviePurple, MavieTurquoise, MavieBlue),
    start = Offset(26f, 181.5f),
    end = Offset(86f, 181.5f),
)

private val MavieOInnerRimBrush = Brush.linearGradient(
    colors = listOf(MavieTurquoise, MavieBlue, MaviePurple),
    start = Offset(56f, 165.9f),
    end = Offset(56f, 197.1f),
)

private fun DrawScope.drawMavieMonogram(alpha: Float = 1f, strokeScale: Float = 1f, lensAlpha: Float = alpha) {
    val outerStroke = Stroke(
        width = 11.2f * strokeScale,
        cap = StrokeCap.Round,
        join = StrokeJoin.Round,
    )
    val innerStroke = Stroke(
        width = 9.4f * strokeScale,
        cap = StrokeCap.Round,
        join = StrokeJoin.Round,
    )
    drawPath(MavieMMonogramPath, brush = MavieObsidianBrush, alpha = alpha)
    drawPath(MavieMMonogramPath, brush = MavieMRimBrush, style = outerStroke, alpha = alpha)
    drawPath(MavieODonutPath, brush = MavieObsidianBrush, alpha = lensAlpha)
    drawPath(MavieOOuterPath, brush = MavieORimBrush, style = outerStroke, alpha = lensAlpha)
    drawPath(MavieOInnerPath, brush = MavieOInnerRimBrush, style = innerStroke, alpha = lensAlpha)
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
                val base = size.minDimension * 0.26f * scaleFactor
                val center = Offset(size.width / 2f, size.height / 2f)
                drawCircle(
                    brush = Brush.radialGradient(
                        listOf(
                            MaviePurple.copy(alpha = 0.26f * alpha),
                            MavieTurquoise.copy(alpha = 0.12f * alpha),
                            Color.Transparent,
                        ),
                        center = center,
                        radius = base * 1.45f,
                    ),
                    radius = base * 1.45f,
                    center = center,
                )
                translate(center.x - base / 2f, center.y - base / 2f) {
                    val unit = base / 256f
                    scale(unit, unit, pivot = Offset.Zero) {
                        val entrance = progress.value.coerceIn(0.18f, 1f)
                        drawMavieMonogram(
                            alpha = alpha * entrance,
                            strokeScale = 1.0f,
                            lensAlpha = alpha * ((progress.value - 0.12f) / 0.88f).coerceIn(0.15f, 1f),
                        )
                    }
                }
            }
        }
    }
}
