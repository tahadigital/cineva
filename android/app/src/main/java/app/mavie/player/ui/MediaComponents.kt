package app.mavie.player.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.Movie
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.zIndex
import coil.compose.AsyncImage
import coil.request.ImageRequest

@Composable
internal fun PosterArt(media: UiMedia, modifier: Modifier = Modifier, backdrop: Boolean = false) {
    Box(modifier.background(Brush.linearGradient(listOf(Color(0xFF1E2642), Color(0xFF111629))))) {
        Column(Modifier.align(Alignment.Center).padding(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Outlined.Movie, null, tint = MavieMuted, modifier = Modifier.size(30.dp))
            Spacer(Modifier.height(12.dp))
            Text(media.title, color = Color(0xFFE2E8F8), fontSize = 12.sp, fontWeight = FontWeight.Medium,
                maxLines = 3, overflow = TextOverflow.Ellipsis)
        }
        val url = if (backdrop) media.backdrop.ifBlank { media.poster } else media.poster.ifBlank { media.backdrop }
        if (url.isNotBlank()) {
            val reducedMotion = rememberReducedMotion()
            val context = LocalContext.current
            val request = remember(url, context, reducedMotion) {
                ImageRequest.Builder(context).data(url).crossfade(!reducedMotion).build()
            }
            AsyncImage(model = request, contentDescription = null, modifier = Modifier.fillMaxSize(),
                contentScale = if (media.kind == "live") ContentScale.Fit else ContentScale.Crop)
        }
    }
}

@Composable
internal fun PosterCard(media: UiMedia, onOpen: () -> Unit, onFavorite: () -> Unit, modifier: Modifier = Modifier, compact: Boolean = false) {
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    val scale = rememberPressScale(interactionSource)
    val cardShape = RoundedCornerShape(16.dp)
    Column(modifier.zIndex(if (focused) 1f else 0f).graphicsLayer { scaleX = scale; scaleY = scale }) {
        Card(
            onClick = onOpen,
            interactionSource = interactionSource,
            modifier = Modifier
                .fillMaxWidth()
                .then(
                    if (focused) {
                        Modifier.shadow(
                            elevation = 16.dp,
                            shape = cardShape,
                            clip = false,
                            ambientColor = MaviePurple.copy(alpha = 0.55f),
                            spotColor = MavieTurquoise.copy(alpha = 0.65f),
                        )
                    } else {
                        Modifier
                    }
                )
                .semantics {
                    contentDescription = media.title
                    role = Role.Button
                },
            shape = cardShape,
            border = BorderStroke(if (focused) 2.5.dp else 1.dp, if (focused) MavieTvFocusBrush else MavieSpecularBorderBrush),
            colors = CardDefaults.cardColors(containerColor = Color(0xB8141B2E)),
        ) {
            Box(Modifier.fillMaxWidth().aspectRatio(if (media.kind == "live") 1.25f else 2f / 3f)) {
                PosterArt(media, Modifier.fillMaxSize())
                if (!compact) IconButton(
                    onClick = onFavorite,
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .size(48.dp)
                        .mavieTvFocusable(shape = CircleShape, addFocusable = false),
                ) {
                    Box(
                        Modifier.size(34.dp).clip(CircleShape).background(Color(0x880A0D16))
                            .border(1.dp, MavieSpecularBorderBrush, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            if (media.favorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                            if (media.favorite) "${media.title} favorilerden kaldır" else "${media.title} favorilere ekle",
                            tint = if (media.favorite) MavieCyanDot else Color.White,
                            modifier = Modifier.size(18.dp),
                        )
                    }
                }
                if (media.kind == "live") Box(
                    Modifier.align(Alignment.BottomStart).padding(8.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(Brush.horizontalGradient(listOf(MaviePurple, MavieBlue)))
                        .border(1.dp, Color.White.copy(alpha = 0.25f), RoundedCornerShape(8.dp)),
                ) {
                    Text("CANLI", Modifier.padding(horizontal = 7.dp, vertical = 3.dp), fontSize = 9.sp,
                        fontWeight = FontWeight.Bold, color = Color.White, letterSpacing = .7.sp)
                }
                if (media.progressPositionMs > 0) LinearProgressIndicator(
                    progress = { media.progressFraction }, modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(3.dp),
                    color = MavieTurquoise, trackColor = Color.White.copy(alpha = .18f))
            }
        }
        if (!compact || media.kind == "live") {
            Text(media.title, Modifier.padding(top = 7.dp), style = MaterialTheme.typography.labelLarge,
                maxLines = 2, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onBackground)
            Text(listOf(media.year, if (media.rating > 0) "★ %.1f".format(media.rating) else mediaKind(media.kind))
                .filter { it.isNotBlank() }.joinToString("  ·  "),
                Modifier.padding(top = 3.dp), fontSize = 11.sp, color = MavieMuted, maxLines = 1,
                overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
internal fun LiveChannelRow(
    media: UiMedia,
    onOpen: () -> Unit,
    onFavorite: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(18.dp)
    Card(
        onClick = onOpen,
        shape = shape,
        border = BorderStroke(if (focused) 2.5.dp else 1.dp, if (focused) MavieTvFocusBrush else MavieSpecularBorderBrush),
        colors = CardDefaults.cardColors(containerColor = if (focused) Color(0xD91A223B) else Color(0xB8141B2E)),
        modifier = modifier
            .fillMaxWidth()
            .mavieTvFocusable(
                shape = shape,
                showFocusBorder = false,
                addFocusable = false,
                onFocusChange = { focused = it },
            )
            .semantics {
                contentDescription = media.title
                role = Role.Button
            },
    ) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 76.dp).padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Box(
                Modifier
                    .size(width = 96.dp, height = 56.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xFF0E1424)),
            ) {
                PosterArt(media, Modifier.fillMaxSize())
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = media.title,
                    style = MaterialTheme.typography.titleMedium,
                    color = Color.White,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(
                        Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(Brush.horizontalGradient(listOf(MaviePurple, MavieBlue)))
                            .padding(horizontal = 7.dp, vertical = 2.dp),
                    ) {
                        Text("CANLI", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color.White, letterSpacing = 0.7.sp)
                    }
                    if (media.category.isNotBlank()) {
                        Text(media.category, color = MavieMuted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            IconButton(
                onClick = onFavorite,
                modifier = Modifier
                    .size(48.dp)
                    .mavieTvFocusable(shape = CircleShape, addFocusable = false),
            ) {
                Icon(
                    if (media.favorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                    if (media.favorite) "${media.title} favorilerden kaldır" else "${media.title} favorilere ekle",
                    tint = if (media.favorite) MavieCyanDot else MavieMuted,
                    modifier = Modifier.size(20.dp),
                )
            }
        }
    }
}

@Composable
internal fun ContinueCard(media: UiMedia, onOpen: () -> Unit, onPlay: () -> Unit) {
    val isTv = LocalIsTv.current
    val interactionSource = remember { MutableInteractionSource() }
    val focused by interactionSource.collectIsFocusedAsState()
    val scale = rememberPressScale(interactionSource)
    val cardShape = RoundedCornerShape(16.dp)
    Card(
        onClick = onOpen,
        interactionSource = interactionSource,
        modifier = Modifier
            .zIndex(if (focused) 1f else 0f)
            .width(continueCardWidthDp(isTv).dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .then(
                if (focused) {
                    Modifier.shadow(
                        elevation = 16.dp,
                        shape = cardShape,
                        clip = false,
                        ambientColor = MaviePurple.copy(alpha = 0.55f),
                        spotColor = MavieTurquoise.copy(alpha = 0.65f),
                    )
                } else {
                    Modifier
                }
            ),
        shape = cardShape,
        border = BorderStroke(if (focused) 2.5.dp else 1.dp, if (focused) MavieTvFocusBrush else MavieSpecularBorderBrush),
        colors = CardDefaults.cardColors(containerColor = Color(0xBD151C30)),
    ) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
            PosterArt(media, Modifier.fillMaxSize(), backdrop = true)
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .20f)))
            FilledIconButton(
                onClick = onPlay,
                modifier = Modifier
                    .align(Alignment.Center)
                    .size(48.dp)
                    .mavieTvFocusable(shape = CircleShape, addFocusable = false)
                    .border(1.dp, MavieSpecularBorderBrush, CircleShape),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color(0x99141B2E), contentColor = Color.White),
            ) {
                Icon(Icons.Filled.PlayArrow, "${media.title} izlemeye devam et", Modifier.size(28.dp))
            }
            if (media.progressPositionMs > 0 && media.progressFraction < .95f) LinearProgressIndicator(progress = { media.progressFraction },
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(3.dp),
                color = MavieTurquoise, trackColor = Color.White.copy(alpha = .25f))
        }
        Column(Modifier.padding(10.dp)) {
            Text(media.title, fontWeight = FontWeight.SemiBold, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val statusText = if (media.progressPositionMs <= 0L) {
                if (media.episodeNumber > 0) "Sıradaki bölüm · ${media.episodeNumber}. Bölüm" else "Sıradaki bölüm"
            } else "${playbackTime((media.progressDurationMs - media.progressPositionMs).coerceAtLeast(0))} kaldı"
            Text(statusText, Modifier.padding(top = 2.dp), color = MavieMuted, fontSize = 10.sp)
        }
    }
}

@Composable
internal fun SectionTitle(title: String, subtitle: String? = null, onAll: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontSize = 20.sp)
            if (!subtitle.isNullOrBlank()) Text(subtitle, color = MavieMuted, fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp))
        }
        if (onAll != null) {
            TextButton(
                onClick = onAll,
                modifier = Modifier
                    .heightIn(min = 48.dp)
                    .mavieTvFocusable(shape = CircleShape, addFocusable = false),
            ) { Text("Tümü", fontSize = 12.sp, color = MavieCyanDot) }
        }
    }
}

@Composable
internal fun MessagePanel(
    title: String,
    message: String,
    modifier: Modifier = Modifier,
    action: String? = null,
    onAction: (() -> Unit)? = null,
    hint: String? = null,
    secondaryAction: String? = null,
    onSecondaryAction: (() -> Unit)? = null,
) {
    Column(modifier.fillMaxWidth().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Outlined.Movie, null, tint = MaviePurple, modifier = Modifier.size(32.dp))
        Spacer(Modifier.height(15.dp))
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(message, Modifier.padding(top = 8.dp), style = MaterialTheme.typography.bodyMedium, color = MavieMuted)
        if (!hint.isNullOrBlank()) {
            Text(hint, Modifier.padding(top = 6.dp), style = MaterialTheme.typography.bodySmall, color = MavieMuted.copy(alpha = 0.85f))
        }
        val hasPrimary = action != null && onAction != null
        val hasSecondary = secondaryAction != null && onSecondaryAction != null
        if (hasPrimary || hasSecondary) {
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                if (hasPrimary) {
                    MavieGlassPillButton(
                        onClick = onAction!!,
                        modifier = Modifier.heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        Text(action!!, color = Color.White)
                    }
                }
                if (hasSecondary) {
                    OutlinedButton(
                        onClick = onSecondaryAction!!,
                        modifier = Modifier
                            .heightIn(min = 48.dp)
                            .mavieTvFocusable(shape = RoundedCornerShape(16.dp), addFocusable = false),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
                    ) {
                        Text(secondaryAction!!)
                    }
                }
            }
        }
    }
}

@Composable
internal fun LoadingStageBanner(
    title: String = "Sahne Hazırlanıyor",
    subtitle: String = "Kütüphanen, afişler ve yayın akışları yükleniyor…",
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.fillMaxWidth().mavieGlassSurface(RoundedCornerShape(18.dp)),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CircularProgressIndicator(Modifier.size(18.dp), color = MavieTurquoise, strokeWidth = 2.4.dp)
                Text(title, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
            }
            Text(subtitle, color = MavieMuted, fontSize = 12.sp)
            LinearProgressIndicator(
                modifier = Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(99.dp)),
                color = MavieTurquoise,
                trackColor = Color.White.copy(alpha = .12f),
            )
        }
    }
}

@Composable
internal fun LoadingPoster(modifier: Modifier = Modifier) {
    val reducedMotion = rememberReducedMotion()
    val alpha = if (reducedMotion) 0.75f else {
        val transition = rememberInfiniteTransition(label = "poster-shimmer")
        transition.animateFloat(
            initialValue = 0.45f,
            targetValue = 0.95f,
            animationSpec = infiniteRepeatable(tween(900, easing = FastOutSlowInEasing), RepeatMode.Reverse),
            label = "poster-alpha",
        ).value
    }
    Column(modifier) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(2f / 3f).clip(RoundedCornerShape(16.dp))
                .background(Brush.verticalGradient(listOf(Color(0xFF1A223B).copy(alpha = alpha), Color(0xFF111628).copy(alpha = alpha))))
                .border(1.dp, MavieSpecularBorderBrush, RoundedCornerShape(16.dp)),
            contentAlignment = Alignment.BottomStart,
        ) {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Box(Modifier.fillMaxWidth(.7f).height(8.dp).clip(RoundedCornerShape(3.dp)).background(Color.White.copy(alpha = .12f * alpha)))
                Box(Modifier.fillMaxWidth(.45f).height(6.dp).clip(RoundedCornerShape(3.dp)).background(Color.White.copy(alpha = .08f * alpha)))
            }
        }
        Spacer(Modifier.height(9.dp))
        Box(Modifier.fillMaxWidth(.8f).height(12.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xFF1A223B).copy(alpha = alpha)))
        Spacer(Modifier.height(6.dp))
        Box(Modifier.fillMaxWidth(.5f).height(8.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xFF1A223B).copy(alpha = alpha * .85f)))
    }
}
