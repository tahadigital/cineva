package app.mavie.player.ui

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.FavoriteBorder
import androidx.compose.material.icons.outlined.Movie
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
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
import coil.compose.AsyncImage
import coil.request.ImageRequest

@Composable
internal fun PosterArt(media: UiMedia, modifier: Modifier = Modifier, backdrop: Boolean = false) {
    Box(modifier.background(Brush.linearGradient(listOf(Color(0xFF313131), Color(0xFF1A1A1A))))) {
        Column(Modifier.align(Alignment.Center).padding(14.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Outlined.Movie, null, tint = Color(0xFF888888), modifier = Modifier.size(30.dp))
            Spacer(Modifier.height(12.dp))
            Text(media.title, color = Color(0xFFCCCCCC), fontSize = 12.sp, fontWeight = FontWeight.Medium,
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
    val scale = rememberPressScale(interactionSource)
    Column(modifier.graphicsLayer { scaleX = scale; scaleY = scale }) {
        Card(
            onClick = onOpen,
            interactionSource = interactionSource,
            modifier = Modifier.fillMaxWidth().semantics {
                contentDescription = media.title
                role = Role.Button
            },
            shape = RoundedCornerShape(6.dp),
            colors = CardDefaults.cardColors(containerColor = MaviePanel),
        ) {
            Box(Modifier.fillMaxWidth().aspectRatio(if (media.kind == "live") 1.25f else 2f / 3f)) {
                PosterArt(media, Modifier.fillMaxSize())
                if (!compact) IconButton(
                    onClick = onFavorite,
                    modifier = Modifier.align(Alignment.TopEnd).size(48.dp),
                ) {
                    Icon(
                        if (media.favorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder,
                        if (media.favorite) "${media.title} favorilerden kaldır" else "${media.title} favorilere ekle",
                        tint = if (media.favorite) MavieCoral else Color.White,
                        modifier = Modifier.size(20.dp),
                    )
                }
                if (media.kind == "live") Surface(Modifier.align(Alignment.BottomStart).padding(8.dp),
                    color = MavieCoral, shape = RoundedCornerShape(4.dp)) {
                    Text("CANLI", Modifier.padding(horizontal = 6.dp, vertical = 3.dp), fontSize = 9.sp,
                        fontWeight = FontWeight.Bold, color = Color.White, letterSpacing = .7.sp)
                }
                if (media.progressPositionMs > 0) LinearProgressIndicator(
                    progress = { media.progressFraction }, modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(3.dp),
                    color = MavieCoral, trackColor = Color.White.copy(alpha = .18f))
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
internal fun ContinueCard(media: UiMedia, onOpen: () -> Unit, onPlay: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val scale = rememberPressScale(interactionSource)
    Card(
        onClick = onOpen,
        interactionSource = interactionSource,
        modifier = Modifier.width(168.dp).graphicsLayer { scaleX = scale; scaleY = scale },
        shape = RoundedCornerShape(6.dp),
        colors = CardDefaults.cardColors(containerColor = MaviePanel),
    ) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f)) {
            PosterArt(media, Modifier.fillMaxSize(), backdrop = true)
            Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .20f)))
            FilledIconButton(
                onClick = onPlay,
                modifier = Modifier.align(Alignment.Center).size(48.dp),
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = Color.Black.copy(alpha = .66f), contentColor = Color.White),
            ) {
                Icon(Icons.Filled.PlayArrow, "${media.title} izlemeye devam et", Modifier.size(28.dp))
            }
            if (media.progressPositionMs > 0 && media.progressFraction < .95f) LinearProgressIndicator(progress = { media.progressFraction },
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(3.dp),
                color = MavieCoral, trackColor = Color.White.copy(alpha = .25f))
        }
        Column(Modifier.padding(8.dp)) {
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
        if (onAll != null) TextButton(onClick = onAll, modifier = Modifier.heightIn(min = 48.dp)) { Text("Tümü", fontSize = 12.sp) }
    }
}

@Composable
internal fun MessagePanel(title: String, message: String, modifier: Modifier = Modifier,
                          action: String? = null, onAction: (() -> Unit)? = null) {
    Column(modifier.fillMaxWidth().padding(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Outlined.Movie, null, tint = MavieCoral, modifier = Modifier.size(32.dp))
        Spacer(Modifier.height(15.dp))
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(message, Modifier.padding(top = 8.dp), style = MaterialTheme.typography.bodyMedium, color = MavieMuted)
        if (action != null && onAction != null) {
            Spacer(Modifier.height(16.dp))
            OutlinedButton(onClick = onAction, modifier = Modifier.heightIn(min = 48.dp)) { Text(action) }
        }
    }
}

@Composable
internal fun LoadingStageBanner(
    title: String = "Sahne Hazırlanıyor",
    subtitle: String = "Kütüphanen, afişler ve yayın akışları yükleniyor…",
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth().border(1.dp, Color.White.copy(alpha = .09f), RoundedCornerShape(14.dp)),
        color = Color(0xFF1A1E29),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                CircularProgressIndicator(Modifier.size(18.dp), color = MavieCoral, strokeWidth = 2.4.dp)
                Text(title, color = Color.White, fontWeight = FontWeight.Bold, fontSize = 14.sp)
            }
            Text(subtitle, color = MavieMuted, fontSize = 12.sp)
            LinearProgressIndicator(
                modifier = Modifier.fillMaxWidth().height(3.dp).clip(RoundedCornerShape(99.dp)),
                color = MavieCoral,
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
            Modifier.fillMaxWidth().aspectRatio(2f / 3f).clip(RoundedCornerShape(10.dp))
                .background(Brush.verticalGradient(listOf(MaviePanel.copy(alpha = alpha), Color(0xFF141821).copy(alpha = alpha)))),
            contentAlignment = Alignment.BottomStart,
        ) {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Box(Modifier.fillMaxWidth(.7f).height(8.dp).clip(RoundedCornerShape(3.dp)).background(Color.White.copy(alpha = .10f * alpha)))
                Box(Modifier.fillMaxWidth(.45f).height(6.dp).clip(RoundedCornerShape(3.dp)).background(Color.White.copy(alpha = .07f * alpha)))
            }
        }
        Spacer(Modifier.height(9.dp))
        Box(Modifier.fillMaxWidth(.8f).height(12.dp).clip(RoundedCornerShape(4.dp)).background(MaviePanel.copy(alpha = alpha)))
        Spacer(Modifier.height(6.dp))
        Box(Modifier.fillMaxWidth(.5f).height(8.dp).clip(RoundedCornerShape(4.dp)).background(MaviePanel.copy(alpha = alpha * .85f)))
    }
}
