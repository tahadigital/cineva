package app.cineva.player.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun AkisDetailScreen(
    state: DetailUiState,
    onBack: () -> Unit,
    onPlay: (UiMedia) -> Unit,
    onFavorite: (UiMedia) -> Unit,
    onEpisode: (UiMedia) -> Unit,
    onSeason: (String) -> Unit,
    onAddToCollection: (UiMedia) -> Unit,
    onRetry: () -> Unit,
    onClearProgress: (UiMedia) -> Unit = {},
) {
    val media = state.media
    val season = state.seasons.firstOrNull { it.id == state.selectedSeasonId } ?: state.seasons.firstOrNull()
    val reducedMotion = rememberReducedMotion()
    var seasonsOpen by remember(media.id) { mutableStateOf(false) }
    val featuredEpisode = season?.episodes?.let { episodes ->
        episodes.firstOrNull { it.canResume } ?: episodes.firstOrNull { it.progressFraction < .95f } ?: episodes.firstOrNull()
    }
    Scaffold(containerColor = AkisBackground) { padding ->
        BoxWithConstraints(Modifier.fillMaxSize().padding(padding)) {
            val twoPaneTablet = maxWidth >= 700.dp && media.kind == "series"
            val coverBlock: @Composable () -> Unit = {
                Box(Modifier.fillMaxWidth().height(if (twoPaneTablet) 240.dp else 335.dp)) {
                    PosterArt(media, Modifier.fillMaxSize(), backdrop = true)
                    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(
                        0f to Color.Transparent, .48f to Color.Transparent, .84f to AkisBackground.copy(alpha = .82f), 1f to AkisBackground)))
                    Column(Modifier.align(Alignment.BottomStart).padding(horizontal = 16.dp)) {
                        Text(media.title, style = MaterialTheme.typography.headlineLarge,
                            color = Color.White, maxLines = 3, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
            val metadataBlock: @Composable () -> Unit = {
                Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    val meta = listOf(media.year, if (media.rating > 0) "★ %.1f".format(media.rating) else "",
                        if (state.durationMs > 0) "${state.durationMs / 60_000} dk" else "", state.genre)
                        .filter { it.isNotBlank() }.joinToString("  ·  ")
                    if (meta.isNotBlank()) Text(meta, color = AkisMuted, fontSize = 12.sp, lineHeight = 18.sp)
                    val playbackTarget = if (media.kind == "series") featuredEpisode else media
                    if (playbackTarget != null) {
                        Button(onClick = { if (media.kind == "series") onEpisode(playbackTarget) else onPlay(media) },
                            modifier = Modifier.fillMaxWidth().height(48.dp), shape = RoundedCornerShape(4.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black)) {
                            Icon(Icons.Filled.PlayArrow, null, Modifier.size(25.dp)); Spacer(Modifier.width(8.dp))
                            Text(when {
                                media.kind == "live" -> "Yayını aç"
                                playbackTarget.canResume -> "Devam et · ${playbackTime(playbackTarget.progressPositionMs)}"
                                media.kind == "series" && playbackTarget.episodeNumber > 0 -> "${playbackTarget.episodeNumber}. bölümü oynat"
                                else -> "İzlemeye başla"
                            })
                        }
                        if (playbackTarget.canResume && playbackTarget.progressDurationMs > 0) {
                            LinearProgressIndicator(progress = { playbackTarget.progressFraction }, modifier = Modifier.fillMaxWidth().height(3.dp),
                                color = AkisRed, trackColor = Color(0xFF3A3A3A))
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        TextButton(onClick = { onFavorite(media) }, shape = RoundedCornerShape(4.dp), modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.textButtonColors(contentColor = Color.White)) {
                            AnimatedContent(targetState = media.favorite,
                                transitionSpec = { fadeIn(tween(if (reducedMotion) 0 else 130)) togetherWith fadeOut(tween(if (reducedMotion) 0 else 100)) }, label = "favorite") { favorite ->
                                Icon(if (favorite) Icons.Filled.Favorite else Icons.Outlined.FavoriteBorder, null,
                                    tint = if (favorite) AkisRed else MaterialTheme.colorScheme.onSurface, modifier = Modifier.size(19.dp))
                            }
                            Spacer(Modifier.width(8.dp)); Text(if (media.favorite) "Favorilerimde" else "Favorilere ekle", fontSize = 12.sp)
                        }
                        TextButton(onClick = { onAddToCollection(media) }, shape = RoundedCornerShape(4.dp),
                            colors = ButtonDefaults.textButtonColors(contentColor = Color.White)) {
                            Icon(Icons.Outlined.Add, null, Modifier.size(20.dp)); Spacer(Modifier.width(5.dp)); Text("Listeme ekle", fontSize = 12.sp)
                        }
                        if (media.progressPositionMs > 0) {
                            IconButton(onClick = { onClearProgress(media) }) {
                                Icon(Icons.Outlined.Refresh, "İzleme kaydını sıfırla", tint = Color.White, modifier = Modifier.size(19.dp))
                            }
                        }
                    }
                    if (state.overview.isNotBlank()) Text(state.overview, style = MaterialTheme.typography.bodyMedium, color = Color(0xFFD7D7D7))
                    else if (!state.loading) Text("Bu içerik için sağlayıcıdan açıklama gelmedi.", style = MaterialTheme.typography.bodySmall, color = AkisMuted)
                    if (state.cast.isNotBlank()) CreditLine("Oyuncular", state.cast)
                    if (state.director.isNotBlank()) CreditLine("Yönetmen", state.director)
                }
            }
            if (twoPaneTablet) {
                Row(Modifier.fillMaxSize()) {
                    LazyColumn(Modifier.weight(0.44f).fillMaxHeight(), contentPadding = PaddingValues(bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                        item("cover") { coverBlock() }
                        item("metadata") { metadataBlock() }
                        if (state.loading) item("loading") {
                            Row(Modifier.fillMaxWidth().padding(22.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                                Text("Ayrıntılar hazırlanıyor…", color = AkisMuted, fontSize = 12.sp)
                            }
                        }
                        if (state.error != null) item("error") { MessagePanel("Ayrıntılar alınamadı", state.error, action = "Yeniden dene", onAction = onRetry) }
                    }
                    VerticalDivider(color = Color(0xFF282B34), thickness = 1.dp)
                    LazyColumn(Modifier.weight(0.56f).fillMaxHeight(), contentPadding = PaddingValues(top = 12.dp, bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                        item("season-heading") {
                            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                SectionTitle("Bölümler")
                                if (season != null) Box(Modifier.padding(horizontal = 16.dp)) {
                                    TextButton(onClick = { seasonsOpen = true }, enabled = state.seasons.size > 1,
                                        colors = ButtonDefaults.textButtonColors(contentColor = Color.White, disabledContentColor = Color.White)) {
                                        Text(season.title, fontWeight = FontWeight.Bold)
                                        if (state.seasons.size > 1) Icon(Icons.Outlined.ArrowDropDown, null)
                                    }
                                    DropdownMenu(expanded = seasonsOpen, onDismissRequest = { seasonsOpen = false }) {
                                        state.seasons.forEach { entry ->
                                            DropdownMenuItem(text = { Text(entry.title) }, onClick = { onSeason(entry.id); seasonsOpen = false })
                                        }
                                    }
                                }
                            }
                        }
                        items(season?.episodes.orEmpty(), key = { it.id }) { episode ->
                            EpisodeRow(episode, { onEpisode(episode) }, { onAddToCollection(episode) })
                        }
                        if (!state.loading && season?.episodes.isNullOrEmpty() && state.error == null) item("no-episodes") {
                            MessagePanel("Bölümler henüz görünmüyor", "Bu dizi için sağlayıcının sunduğu bölümler burada listelenir.")
                        }
                    }
                }
            } else {
                LazyColumn(contentPadding = PaddingValues(bottom = 28.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
                    item("cover") { coverBlock() }
                    item("metadata") { metadataBlock() }
                    if (state.loading) item("loading") {
                        Row(Modifier.fillMaxWidth().padding(22.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                            Text("Ayrıntılar hazırlanıyor…", color = AkisMuted, fontSize = 12.sp)
                        }
                    }
                    if (state.error != null) item("error") { MessagePanel("Ayrıntılar alınamadı", state.error, action = "Yeniden dene", onAction = onRetry) }
                    if (media.kind == "series") {
                        item("season-heading") {
                            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                                HorizontalDivider(thickness = 1.dp, color = Color(0xFF303030))
                                SectionTitle("Bölümler")
                                if (season != null) Box(Modifier.padding(horizontal = 16.dp)) {
                                    TextButton(onClick = { seasonsOpen = true }, enabled = state.seasons.size > 1,
                                        colors = ButtonDefaults.textButtonColors(contentColor = Color.White, disabledContentColor = Color.White)) {
                                        Text(season.title, fontWeight = FontWeight.Bold)
                                        if (state.seasons.size > 1) Icon(Icons.Outlined.ArrowDropDown, null)
                                    }
                                    DropdownMenu(expanded = seasonsOpen, onDismissRequest = { seasonsOpen = false }) {
                                        state.seasons.forEach { entry ->
                                            DropdownMenuItem(text = { Text(entry.title) }, onClick = { onSeason(entry.id); seasonsOpen = false })
                                        }
                                    }
                                }
                            }
                        }
                        items(season?.episodes.orEmpty(), key = { it.id }) { episode ->
                            EpisodeRow(episode, { onEpisode(episode) }, { onAddToCollection(episode) })
                        }
                        if (!state.loading && season?.episodes.isNullOrEmpty() && state.error == null) item("no-episodes") {
                            MessagePanel("Bölümler henüz görünmüyor", "Bu dizi için sağlayıcının sunduğu bölümler burada listelenir.")
                        }
                    }
                }
            }
            Row(Modifier.align(Alignment.TopStart).fillMaxWidth().background(Brush.verticalGradient(listOf(Color.Black.copy(alpha = .64f), Color.Transparent)))
                .padding(horizontal = 9.dp, vertical = 8.dp)) {
                FilledIconButton(onClick = onBack, shape = CircleShape, colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = Color.Black.copy(alpha = .48f), contentColor = Color.White)) {
                    Icon(Icons.AutoMirrored.Outlined.ArrowBack, "Geri")
                }
            }
        }
    }
}

@Composable
private fun CreditLine(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, fontWeight = FontWeight.Medium, color = AkisMuted, fontSize = 11.sp, modifier = Modifier.width(64.dp))
        Text(value, color = AkisMuted, fontSize = 11.sp, lineHeight = 18.sp, modifier = Modifier.weight(1f))
    }
}

@Composable
private fun EpisodeRow(episode: UiMedia, onPlay: () -> Unit, onAdd: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClickLabel = "Bölümü oynat", onClick = onPlay).padding(horizontal = 16.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(width = 114.dp, height = 64.dp).clip(RoundedCornerShape(3.dp))) {
                PosterArt(episode, Modifier.fillMaxSize(), backdrop = true)
                Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = .22f)))
                Icon(Icons.Outlined.PlayCircleOutline, null, tint = Color.White, modifier = Modifier.align(Alignment.Center).size(29.dp))
                if (episode.canResume) LinearProgressIndicator(progress = { episode.progressFraction },
                    modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(3.dp), color = AkisRed, trackColor = Color(0xFF454545))
            }
            Column(Modifier.weight(1f)) {
                Text(if (episode.episodeNumber > 0) "${episode.episodeNumber}. ${episode.title}" else episode.title,
                    fontSize = 13.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(when {
                    episode.canResume -> "${playbackTime((episode.progressDurationMs - episode.progressPositionMs).coerceAtLeast(0))} kaldı"
                    episode.progressFraction >= .95f -> "İzlendi"
                    episode.progressDurationMs >= 60_000 -> "${episode.progressDurationMs / 60_000} dk"
                    else -> ""
                }, color = AkisMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp))
            }
            IconButton(onClick = onAdd) { Icon(Icons.Outlined.Add, "Bölümü listeye ekle", tint = AkisMuted, modifier = Modifier.size(20.dp)) }
        }
        if (episode.overview.isNotBlank()) Text(episode.overview, Modifier.padding(top = 7.dp),
            color = AkisMuted, fontSize = 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}
