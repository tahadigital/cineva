package app.cineva.player.ui

import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.distinctUntilChanged

@Composable
fun AkisLibraryScreen(
    state: LibraryUiState,
    onTab: (LibraryTab) -> Unit,
    onQuery: (String) -> Unit,
    onCategory: (String) -> Unit,
    onMedia: (UiMedia) -> Unit,
    onPlay: (UiMedia) -> Unit,
    onFavorite: (UiMedia) -> Unit,
    onRefresh: () -> Unit,
    onSettings: () -> Unit,
    onCollection: (UiCollection) -> Unit,
    onCreateCollection: () -> Unit,
    onLoadMore: () -> Unit,
    onAddToCollection: (UiMedia) -> Unit,
    onDeleteCollection: (UiCollection) -> Unit = {},
    onCloseCollection: () -> Unit = {},
    sportsContent: @Composable () -> Unit,
) {
    val reducedMotion = rememberReducedMotion()
    val navTabs = remember { listOf(LibraryTab.HOME, LibraryTab.SPORTS, LibraryTab.SEARCH, LibraryTab.FAVORITES) }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val isTablet = maxWidth >= 600.dp
        Scaffold(
            containerColor = AkisBackground,
            bottomBar = {
                if (!isTablet) {
                    NavigationBar(containerColor = Color(0xFF0C0E13), tonalElevation = 0.dp, modifier = Modifier.heightIn(max = 86.dp)) {
                        navTabs.forEach { tab ->
                            val selected = state.tab == tab ||
                                tab == LibraryTab.FAVORITES && state.tab == LibraryTab.PLAYLISTS ||
                                tab == LibraryTab.HOME && state.tab in listOf(LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)
                            NavigationBarItem(
                                selected = selected, onClick = { onTab(tab) },
                                icon = {
                                    if (tab == LibraryTab.FAVORITES) ProfileAvatar(Modifier.size(24.dp))
                                    else Icon(if (tab == LibraryTab.HOME && selected) Icons.Filled.Home else tabIcon(tab), null, Modifier.size(24.dp))
                                },
                                label = { Text(tab.title, fontSize = 10.sp, fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium, maxLines = 1) },
                                colors = NavigationBarItemDefaults.colors(selectedIconColor = Color.White, selectedTextColor = Color.White,
                                    indicatorColor = Color.Transparent, unselectedIconColor = AkisMuted, unselectedTextColor = AkisMuted),
                            )
                        }
                    }
                }
            },
        ) { padding ->
            Row(Modifier.fillMaxSize().padding(padding)) {
                if (isTablet) {
                    NavigationRail(containerColor = Color(0xFF0C0E13), modifier = Modifier.fillMaxHeight().padding(top = 10.dp)) {
                        navTabs.forEach { tab ->
                            val selected = state.tab == tab ||
                                tab == LibraryTab.FAVORITES && state.tab == LibraryTab.PLAYLISTS ||
                                tab == LibraryTab.HOME && state.tab in listOf(LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)
                            NavigationRailItem(
                                selected = selected, onClick = { onTab(tab) },
                                icon = {
                                    if (tab == LibraryTab.FAVORITES) ProfileAvatar(Modifier.size(24.dp))
                                    else Icon(if (tab == LibraryTab.HOME && selected) Icons.Filled.Home else tabIcon(tab), null, Modifier.size(24.dp))
                                },
                                label = { Text(tab.title, fontSize = 10.sp, maxLines = 1) },
                                colors = NavigationRailItemDefaults.colors(selectedIconColor = Color.White, selectedTextColor = Color.White,
                                    indicatorColor = CinevaCoral.copy(alpha = 0.16f), unselectedIconColor = AkisMuted, unselectedTextColor = AkisMuted),
                            )
                        }
                    }
                }
                Column(Modifier.weight(1f).fillMaxHeight()) {
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp, top = 3.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                if (state.tab in listOf(LibraryTab.HOME, LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)) {
                    AkisWordmark(Modifier.weight(1f))
                } else {
                    Text(if (state.tab == LibraryTab.PLAYLISTS) LibraryTab.FAVORITES.title else state.tab.title,
                        Modifier.weight(1f), fontSize = 25.sp, fontWeight = FontWeight.ExtraBold, color = Color.White)
                }
                if (state.refreshing) CircularProgressIndicator(Modifier.padding(14.dp).size(19.dp), color = AkisRed, strokeWidth = 2.dp)
                if (state.tab != LibraryTab.SEARCH) IconButton(onClick = { onTab(LibraryTab.SEARCH) }) {
                    Icon(Icons.Outlined.Search, "Ara", tint = Color.White)
                }
                IconButton(onClick = onSettings) { Icon(Icons.Outlined.Settings, "Ayarlar", tint = Color.White) }
            }
            if (state.tab in listOf(LibraryTab.HOME, LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)) {
                LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(listOf(LibraryTab.SERIES, LibraryTab.FILMS, LibraryTab.LIVE), key = { it.name }) { tab ->
                        FilterChip(selected = state.tab == tab, onClick = { onTab(if (state.tab == tab) LibraryTab.HOME else tab) },
                            label = { Text(tab.title, fontSize = 13.sp) }, shape = CircleShape)
                    }
                }
            }
            if (state.tab == LibraryTab.SEARCH) {
                OutlinedTextField(value = state.query, onValueChange = onQuery,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                    placeholder = { Text("Film, dizi veya kanal ara", fontSize = 14.sp) },
                    leadingIcon = { Icon(Icons.Outlined.Search, null, Modifier.size(22.dp), tint = AkisMuted) },
                    trailingIcon = if (state.query.isNotEmpty()) {{ IconButton(onClick = { onQuery("") }) { Icon(Icons.Outlined.Close, "Aramayı temizle") } }} else null,
                    singleLine = true, shape = RoundedCornerShape(6.dp),
                    colors = OutlinedTextFieldDefaults.colors(unfocusedContainerColor = Color(0xFF2D2D2D),
                        focusedContainerColor = Color(0xFF2D2D2D), unfocusedBorderColor = Color.Transparent,
                        focusedBorderColor = Color.White.copy(alpha = .34f)))
                Spacer(Modifier.height(9.dp))
            }
            if (state.tab in listOf(LibraryTab.FAVORITES, LibraryTab.PLAYLISTS) && state.query.isBlank()) {
                Row(Modifier.padding(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = state.tab == LibraryTab.FAVORITES, onClick = { onTab(LibraryTab.FAVORITES) }, label = { Text("Favorilerim") })
                    FilterChip(selected = state.tab == LibraryTab.PLAYLISTS, onClick = { onTab(LibraryTab.PLAYLISTS) }, label = { Text("Listelerim") })
                }
            }
            if (state.tab != LibraryTab.HOME && state.tab != LibraryTab.PLAYLISTS && state.categories.isNotEmpty()) {
                LazyRow(contentPadding = PaddingValues(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    item("all") { FilterChip(selected = state.selectedCategoryId.isBlank(), onClick = { onCategory("") }, label = { Text("Tümü") }) }
                    items(state.categories, key = { it.id }) { category ->
                        FilterChip(selected = category.id == state.selectedCategoryId, onClick = { onCategory(category.id) }, label = {
                            Text(category.title, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 230.dp))
                        })
                    }
                }
            }
            // Keep the schedule out of overlapping Crossfade content so a single panel owns each fetch.
            if (state.tab == LibraryTab.SPORTS) Box(Modifier.weight(1f)) { sportsContent() }
            else Crossfade(targetState = state.tab to state.query.isNotBlank(), modifier = Modifier.weight(1f),
                animationSpec = tween(if (reducedMotion) 0 else 190), label = "library-tab") { (tab, searching) ->
                when {
                    tab == LibraryTab.HOME && !searching -> HomeContent(state, onTab, onMedia, onPlay, onFavorite, onRefresh, onAddToCollection)
                    tab == LibraryTab.SEARCH && !searching -> SearchLanding(state, onMedia)
                    tab == LibraryTab.PLAYLISTS && !searching && state.title.isBlank() -> CollectionContent(state, onCollection, onCreateCollection, onDeleteCollection)
                    else -> CatalogContent(state, onMedia, onFavorite, onRefresh, onLoadMore, onCloseCollection)
                }
            }
        }
            }
        }
    }
}

private fun tabIcon(tab: LibraryTab): ImageVector = when (tab) {
    LibraryTab.HOME -> Icons.Outlined.Home
    LibraryTab.LIVE -> Icons.Outlined.LiveTv
    LibraryTab.FILMS -> Icons.Outlined.Movie
    LibraryTab.SERIES -> Icons.Outlined.VideoLibrary
    LibraryTab.SPORTS -> Icons.Outlined.SportsSoccer
    LibraryTab.SEARCH -> Icons.Outlined.Search
    LibraryTab.FAVORITES -> Icons.Outlined.FavoriteBorder
    LibraryTab.PLAYLISTS -> Icons.Outlined.Folder
}

@Composable
private fun ProfileAvatar(modifier: Modifier = Modifier) {
    Box(modifier.clip(RoundedCornerShape(4.dp)).background(Color(0xFF177784)), contentAlignment = Alignment.Center) {
        Icon(Icons.Outlined.Person, null, tint = Color.White, modifier = Modifier.fillMaxSize(.84f))
    }
}

@Composable
private fun HomeContent(state: LibraryUiState, onTab: (LibraryTab) -> Unit, onMedia: (UiMedia) -> Unit,
                        onPlay: (UiMedia) -> Unit, onFavorite: (UiMedia) -> Unit, onRefresh: () -> Unit,
                        onAddToCollection: (UiMedia) -> Unit) {
    LazyColumn(contentPadding = PaddingValues(top = 5.dp, bottom = 30.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
        val featured = state.featured ?: state.items.firstOrNull()
        if (state.showcase.isNotEmpty()) item("showcase") {
            Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
                SectionTitle("Yeni Çıkanlar")
                val pager=rememberPagerState(pageCount={state.showcase.size})
                HorizontalPager(state=pager,key={state.showcase[it].id}) { page -> HeroCard(state.showcase[page],onMedia,onPlay,onAddToCollection) }
                Text("${pager.currentPage+1} / ${state.showcase.size} · Diğer kapaklar için kaydır",Modifier.padding(horizontal=20.dp),color=Color.LightGray,fontSize=11.sp)
            }
        }
        else if (featured != null) item("hero") { HeroCard(featured, onMedia, onPlay, onAddToCollection) }
        else if (!state.loading && state.error == null) item("welcome") {
            Column(Modifier.padding(horizontal = 24.dp, vertical = 22.dp)) {
                Text("İzlemek için bir şeyler bul", style = MaterialTheme.typography.headlineLarge)
            }
        }
        if (state.error != null) item("error") {
            MessagePanel("Kütüphane şu an yenilenemedi", state.error, action = "Yeniden dene", onAction = onRefresh)
        }
        if (state.loading && state.items.isEmpty()) item("loading") {
            Column(verticalArrangement = Arrangement.spacedBy(15.dp)) {
                SectionTitle("Kütüphanen hazırlanıyor")
                LazyRow(contentPadding = PaddingValues(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(4) { LoadingPoster(Modifier.width(124.dp)) }
                }
            }
        }
        if (state.continueWatching.isNotEmpty()) item("continue") {
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                SectionTitle("İzlemeye Devam Et")
                LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(state.continueWatching, key = { it.id }) { item -> ContinueCard(item, { onMedia(item) }, { onPlay(item) }) }
                }
            }
        }
        items(state.recommendations,key={"recommendation-"+it.id}) { shelf ->
            MediaRow(shelf.title,shelf.items,onMedia,onFavorite,null,subtitle=shelf.subtitle)
        }
        if(state.recommendations.isNotEmpty())item("discovery-credit") { Text("Keşif: Kişisel kütüphane ve izleme geçmişin üzerinden hazırlanır",Modifier.padding(horizontal=20.dp),color=Color.Gray,fontSize=11.sp) }
        if (state.items.isNotEmpty()) item("movies") {
            MediaRow("Kütüphanene Yeni Eklenen Filmler", state.items, onMedia, onFavorite, { onTab(LibraryTab.FILMS) })
        }
        if (state.seriesItems.isNotEmpty()) item("series") {
            MediaRow("Kütüphanene Yeni Eklenen Diziler", state.seriesItems, onMedia, onFavorite, { onTab(LibraryTab.SERIES) })
        }
        if (state.favorites.isNotEmpty()) item("favorites") {
            MediaRow("Favorilerim", state.favorites, onMedia, onFavorite, { onTab(LibraryTab.FAVORITES) })
        }
    }
}

@Composable
private fun HeroCard(media: UiMedia, onMedia: (UiMedia) -> Unit, onPlay: (UiMedia) -> Unit, onAddToCollection: (UiMedia) -> Unit) {
    BoxWithConstraints(Modifier.padding(horizontal = 16.dp).fillMaxWidth()) {
        val wide = maxWidth > 580.dp
        val heroHeight = if (wide) 405.dp else (maxWidth * 1.23f).coerceIn(360.dp, 490.dp)
        Card(shape = RoundedCornerShape(9.dp), modifier = Modifier.fillMaxWidth().height(heroHeight),
            border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(alpha = .16f)),
            colors = CardDefaults.cardColors(containerColor = AkisPanel)) {
            Box(Modifier.fillMaxSize()) {
                PosterArt(media, Modifier.fillMaxSize().clickable(onClickLabel = "Ayrıntılar") { onMedia(media) }, backdrop = wide)
                Box(Modifier.fillMaxSize().background(Brush.verticalGradient(
                    0f to Color.Transparent, .42f to Color.Transparent,
                    .75f to Color.Black.copy(alpha = .66f), 1f to Color.Black.copy(alpha = .96f))))
                Column(Modifier.align(Alignment.BottomCenter).widthIn(max = 500.dp).fillMaxWidth().padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(media.title, fontSize = 32.sp, lineHeight = 34.sp, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        fontWeight = FontWeight.Black, maxLines = 3, overflow = TextOverflow.Ellipsis, color = Color.White)
                    Text(listOf(media.year, mediaKind(media.kind), media.category).filter { it.isNotBlank() }.joinToString("  ·  "),
                        Modifier.padding(top = 8.dp), color = Color(0xFFDADADA), fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Spacer(Modifier.height(12.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = { if (media.kind == "series") onMedia(media) else onPlay(media) },
                            modifier = Modifier.weight(1f), shape = RoundedCornerShape(4.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black),
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 11.dp)) {
                            Icon(Icons.Filled.PlayArrow, null, Modifier.size(23.dp)); Spacer(Modifier.width(5.dp))
                            Text(if (media.canResume) "Devam Et" else "Oynat", fontSize = 14.sp, maxLines = 1)
                        }
                        Button(onClick = { onAddToCollection(media) }, modifier = Modifier.weight(1f), shape = RoundedCornerShape(4.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xE6353535), contentColor = Color.White),
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 11.dp)) {
                            Icon(Icons.Outlined.Add, null, Modifier.size(22.dp)); Spacer(Modifier.width(5.dp)); Text("Listeme Ekle", fontSize = 13.sp, maxLines = 1)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MediaRow(title: String, media: List<UiMedia>, onMedia: (UiMedia) -> Unit,
                     onFavorite: (UiMedia) -> Unit, onAll: (() -> Unit)?, subtitle: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle(title, subtitle = subtitle, onAll = onAll)
        LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
            items(media, key = { it.id }) { item -> PosterCard(item, { onMedia(item) }, { onFavorite(item) }, Modifier.width(112.dp), compact = true) }
        }
    }
}

@Composable
private fun SearchLanding(state: LibraryUiState, onMedia: (UiMedia) -> Unit) {
    val suggestions = (listOfNotNull(state.featured) + state.continueWatching + state.seriesItems).distinctBy { it.id }.take(12)
    LazyColumn(contentPadding = PaddingValues(bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (suggestions.isEmpty()) item("prompt") {
            Text("İzlemek istediğin içeriğin adını yaz.", Modifier.padding(16.dp), color = AkisMuted)
        }
        else item("heading") { SectionTitle("Göz at") }
        items(suggestions, key = { it.id }) { media ->
            Row(Modifier.fillMaxWidth().background(AkisPanel).clickable { onMedia(media) }.padding(end = 14.dp),
                verticalAlignment = Alignment.CenterVertically) {
                PosterArt(media, Modifier.size(width = 128.dp, height = 72.dp), backdrop = true)
                Text(media.title, Modifier.weight(1f).padding(horizontal = 12.dp), fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Icon(Icons.Outlined.PlayCircleOutline, "Ayrıntılar", tint = Color.White)
            }
        }
    }
}

@Composable
private fun CatalogContent(state: LibraryUiState, onMedia: (UiMedia) -> Unit, onFavorite: (UiMedia) -> Unit,
                           onRefresh: () -> Unit, onLoadMore: () -> Unit, onCloseCollection: () -> Unit = {}) {
    val gridState = rememberLazyGridState()
    val latestLoadMore by rememberUpdatedState(onLoadMore)
    var requestedMore by remember(state.items.size, state.query, state.selectedCategoryId, state.tab) { mutableStateOf(false) }
    LaunchedEffect(state.items.size, state.loading, state.hasMore, state.query, state.selectedCategoryId) {
        if (state.hasMore && !state.loading && state.items.isNotEmpty()) {
            snapshotFlow { gridState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
                .distinctUntilChanged().collect { visibleEnd ->
                    if (!requestedMore && visibleEnd >= state.items.size - 5) {
                        requestedMore = true
                        latestLoadMore()
                    }
                }
        }
    }
    LazyVerticalGrid(state = gridState, columns = GridCells.Adaptive(106.dp), contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 9.dp, bottom = 28.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(21.dp)) {
        item("heading", span = { GridItemSpan(maxLineSpan) }) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (state.tab == LibraryTab.PLAYLISTS && state.title.isNotBlank() && state.query.isBlank()) {
                    TextButton(onClick = onCloseCollection, contentPadding = PaddingValues(0.dp)) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Tüm listelerim", fontSize = 12.sp)
                    }
                }
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(if (state.query.isNotBlank()) "Arama sonuçları" else state.title.ifBlank { state.tab.title },
                        style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    if (state.totalCount > 0) Text("${state.totalCount} içerik", fontSize = 11.sp, color = AkisMuted, modifier = Modifier.padding(bottom = 4.dp))
                }
            }
        }
        if (state.error != null) item("error", span = { GridItemSpan(maxLineSpan) }) {
            MessagePanel("İçerikler yüklenemedi", state.error, action = "Yeniden dene", onAction = onRefresh)
        }
        if (state.loading && state.items.isEmpty()) items(9, key = { "loading-$it" }) { LoadingPoster() }
        else gridItems(state.items, key = { it.id }, contentType = { "poster" }) { item -> PosterCard(item, { onMedia(item) }, { onFavorite(item) }) }
        if (!state.loading && state.items.isEmpty() && state.error == null) item("empty", span = { GridItemSpan(maxLineSpan) }) {
            MessagePanel(if (state.query.isNotBlank()) "Bir eşleşme bulamadık" else if (state.tab == LibraryTab.FAVORITES) "Sevdiklerini bir araya getir" else "Henüz burada içerik yok",
                if (state.query.isNotBlank()) "Başka bir adla aramayı veya farklı bir kategori seçmeyi deneyebilirsin."
                else if (state.tab == LibraryTab.FAVORITES) "Bir afişteki kalbe dokun. Favorilerin burada seni beklesin."
                else "Kütüphaneni yenileyerek tekrar deneyebilirsin.")
        }
        if (state.hasMore) item("more", span = { GridItemSpan(maxLineSpan) }) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                OutlinedButton(onClick = onLoadMore, enabled = !state.loading) {
                    if (state.loading) { CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)) }
                    Text("Daha fazla göster")
                }
            }
        }
    }
}

@Composable
private fun CollectionContent(state: LibraryUiState, onCollection: (UiCollection) -> Unit, onCreate: () -> Unit, onDelete: (UiCollection) -> Unit = {}) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item("title") {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("Kendi seçkilerin", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
                FilledTonalIconButton(onClick = onCreate) { Icon(Icons.Outlined.Add, "Yeni liste oluştur") }
            }
        }
        if (state.collections.isEmpty()) item("empty") {
            MessagePanel("Bir listeyle başla", "Hafta sonuna sakladıklarını veya bir bölüm daha dediklerini aynı yerde topla.", action = "İlk listemi oluştur", onAction = onCreate)
        }
        items(state.collections, key = { it.id }) { collection ->
            Card(onClick = { onCollection(collection) }, shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = AkisPanel)) {
                Row(Modifier.fillMaxWidth().padding(18.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Folder, null, tint = AkisRed, modifier = Modifier.size(30.dp))
                    Column(Modifier.weight(1f).padding(start = 16.dp)) {
                        Text(collection.title, fontWeight = FontWeight.SemiBold)
                        Text("${collection.count} içerik", fontSize = 12.sp, color = AkisMuted, modifier = Modifier.padding(top = 4.dp))
                    }
                    IconButton(onClick = { onDelete(collection) }) {
                        Icon(Icons.Outlined.DeleteOutline, "Listeyi sil", tint = AkisMuted)
                    }
                    Icon(Icons.Outlined.ChevronRight, null, tint = AkisMuted)
                }
            }
        }
    }
}
