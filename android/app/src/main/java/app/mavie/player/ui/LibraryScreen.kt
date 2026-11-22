package app.mavie.player.ui

import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.lazy.grid.rememberLazyGridState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.rounded.FolderOpen
import androidx.compose.material.icons.rounded.Search
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Shuffle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.flow.distinctUntilChanged

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MavieLibraryScreen(
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
    activeProfileName: String = "Ana Profil",
    activeProfileColor: String = "#7C3AED",
    onOpenProfiles: () -> Unit = {},
    onSurprise: () -> Unit = {},
    onOpenLocalFile: () -> Unit = {},
    sportsContent: @Composable () -> Unit,
) {
    val reducedMotion = rememberReducedMotion()
    val navTabs = remember { listOf(LibraryTab.HOME, LibraryTab.SPORTS, LibraryTab.SEARCH, LibraryTab.FAVORITES) }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val isTablet = maxWidth >= 600.dp
        val isCompactTopBar = maxWidth < 400.dp
        Scaffold(
            containerColor = MavieBackground,
            bottomBar = {
                if (!isTablet) {
                    Column(Modifier.fillMaxWidth().background(Color(0xD90E1324))) {
                        HorizontalDivider(thickness = 1.dp, color = Color.White.copy(alpha = 0.12f))
                        NavigationBar(containerColor = Color.Transparent, tonalElevation = 0.dp, modifier = Modifier.heightIn(max = 86.dp)) {
                            navTabs.forEach { tab ->
                                val selected = state.tab == tab ||
                                    tab == LibraryTab.FAVORITES && state.tab == LibraryTab.PLAYLISTS ||
                                    tab == LibraryTab.HOME && state.tab in listOf(LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)
                                NavigationBarItem(
                                    selected = selected, onClick = { onTab(tab) },
                                    icon = {
                                        if (tab == LibraryTab.FAVORITES) ProfileAvatar(activeProfileColor, selected, Modifier.size(24.dp))
                                        else Icon(if (tab == LibraryTab.HOME && selected) Icons.Filled.Home else tabIcon(tab), null, Modifier.size(24.dp))
                                    },
                                    label = { Text(tab.title, fontSize = 10.sp, fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium, maxLines = 1) },
                                    colors = NavigationBarItemDefaults.colors(
                                        selectedIconColor = Color.White,
                                        selectedTextColor = Color.White,
                                        indicatorColor = MaviePurple.copy(alpha = 0.24f),
                                        unselectedIconColor = MavieMuted,
                                        unselectedTextColor = MavieMuted,
                                    ),
                                )
                            }
                        }
                    }
                }
            },
        ) { padding ->
            Row(Modifier.fillMaxSize().padding(padding)) {
                if (isTablet) {
                    Row(Modifier.fillMaxHeight().background(Color(0xD90E1324))) {
                        NavigationRail(containerColor = Color.Transparent, modifier = Modifier.fillMaxHeight().padding(top = 10.dp)) {
                            navTabs.forEach { tab ->
                                val selected = state.tab == tab ||
                                    tab == LibraryTab.FAVORITES && state.tab == LibraryTab.PLAYLISTS ||
                                    tab == LibraryTab.HOME && state.tab in listOf(LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)
                                NavigationRailItem(
                                    selected = selected, onClick = { onTab(tab) },
                                    icon = {
                                        if (tab == LibraryTab.FAVORITES) ProfileAvatar(activeProfileColor, selected, Modifier.size(24.dp))
                                        else Icon(if (tab == LibraryTab.HOME && selected) Icons.Filled.Home else tabIcon(tab), null, Modifier.size(24.dp))
                                    },
                                    label = { Text(tab.title, fontSize = 10.sp, maxLines = 1) },
                                    colors = NavigationRailItemDefaults.colors(
                                        selectedIconColor = Color.White,
                                        selectedTextColor = Color.White,
                                        indicatorColor = MaviePurple.copy(alpha = 0.24f),
                                        unselectedIconColor = MavieMuted,
                                        unselectedTextColor = MavieMuted,
                                    ),
                                )
                            }
                        }
                        VerticalDivider(thickness = 1.dp, color = Color.White.copy(alpha = 0.12f))
                    }
                }
                Column(Modifier.weight(1f).fillMaxHeight()) {
                    Column(Modifier.fillMaxWidth().background(Color(0xBA0D1222))) {
                        Row(
                            Modifier.fillMaxWidth().padding(
                                start = if (isCompactTopBar) 12.dp else 16.dp,
                                end = if (isCompactTopBar) 4.dp else 6.dp,
                                top = if (isCompactTopBar) 4.dp else 3.dp,
                                bottom = 4.dp,
                            ),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            if (state.tab in listOf(LibraryTab.HOME, LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)) {
                                MavieWordmark(Modifier.weight(1f), compact = isCompactTopBar)
                            } else {
                                Text(
                                    if (state.tab == LibraryTab.PLAYLISTS) LibraryTab.FAVORITES.title else state.tab.title,
                                    Modifier.weight(1f),
                                    fontSize = if (isCompactTopBar) 20.sp else 24.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    color = Color.White,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                            MavieTooltipIconButton(
                                label = "Rastgele içerik seç",
                                icon = Icons.Rounded.Shuffle,
                                onClick = onSurprise,
                            )
                            MavieTooltipIconButton(
                                label = "Cihazdan video aç",
                                icon = Icons.Rounded.FolderOpen,
                                onClick = onOpenLocalFile,
                            )
                            if (state.tab != LibraryTab.SEARCH) {
                                MavieTooltipIconButton(
                                    label = "Kütüphanede ara",
                                    icon = Icons.Rounded.Search,
                                    onClick = { onTab(LibraryTab.SEARCH) },
                                )
                            }
                            val profileTint = runCatching { Color(android.graphics.Color.parseColor(activeProfileColor)) }.getOrDefault(MaviePurple)
                            TooltipBox(
                                positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
                                tooltip = { PlainTooltip { Text("Profil değiştir: $activeProfileName") } },
                                state = rememberTooltipState(),
                            ) {
                                Box(
                                    modifier = Modifier
                                        .size(48.dp)
                                        .clip(CircleShape)
                                        .clickable(role = Role.Button, onClickLabel = "Profil seç", onClick = onOpenProfiles)
                                        .semantics(mergeDescendants = true) {
                                            contentDescription = "Profil değiştir: $activeProfileName"
                                        },
                                    contentAlignment = Alignment.Center,
                                ) {
                                    Box(
                                        Modifier
                                            .size(32.dp)
                                            .clip(CircleShape)
                                            .background(profileTint)
                                            .border(1.5.dp, Color.White.copy(alpha = 0.45f), CircleShape),
                                        contentAlignment = Alignment.Center,
                                    ) {
                                        Text(activeProfileName.take(1).uppercase(), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                                    }
                                }
                            }
                            MavieTooltipIconButton(
                                label = "Ayarlar",
                                icon = Icons.Rounded.Settings,
                                onClick = onSettings,
                            )
                        }
                        if (state.refreshing) {
                            LinearProgressIndicator(
                                modifier = Modifier.fillMaxWidth().height(2.dp),
                                color = MavieTurquoise,
                                trackColor = Color.Transparent,
                            )
                        } else {
                            HorizontalDivider(thickness = 1.dp, color = Color.White.copy(alpha = 0.08f))
                        }
                    }
                    val glassChipColors = FilterChipDefaults.filterChipColors(
                        containerColor = Color(0x80182038),
                        labelColor = MavieMuted,
                        selectedContainerColor = MaviePurple.copy(alpha = 0.88f),
                        selectedLabelColor = Color.White,
                    )
                    val glassChipBorder = FilterChipDefaults.filterChipBorder(
                        enabled = true,
                        selected = false,
                        borderColor = Color.White.copy(alpha = 0.14f),
                        selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                    )
                    if (state.tab in listOf(LibraryTab.HOME, LibraryTab.FILMS, LibraryTab.SERIES, LibraryTab.LIVE)) {
                        LazyRow(contentPadding = PaddingValues(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(listOf(LibraryTab.SERIES, LibraryTab.FILMS, LibraryTab.LIVE), key = { it.name }) { tab ->
                                FilterChip(
                                    selected = state.tab == tab,
                                    onClick = { onTab(if (state.tab == tab) LibraryTab.HOME else tab) },
                                    label = { Text(tab.title, fontSize = 13.sp) },
                                    shape = CircleShape,
                                    colors = glassChipColors,
                                    border = FilterChipDefaults.filterChipBorder(
                                        enabled = true,
                                        selected = state.tab == tab,
                                        borderColor = Color.White.copy(alpha = 0.14f),
                                        selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                                    ),
                                )
                            }
                        }
                    }
                    if (state.tab == LibraryTab.SEARCH) {
                        OutlinedTextField(
                            value = state.query, onValueChange = onQuery,
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                            placeholder = { Text("Film, dizi veya kanal ara", fontSize = 14.sp, color = MavieMuted) },
                            leadingIcon = { Icon(Icons.Outlined.Search, null, Modifier.size(22.dp), tint = MavieMuted) },
                            trailingIcon = if (state.query.isNotEmpty()) {
                                {
                                    IconButton(onClick = { onQuery("") }, modifier = Modifier.size(48.dp)) {
                                        Icon(Icons.Outlined.Close, "Aramayı temizle")
                                    }
                                }
                            } else null,
                            singleLine = true, shape = RoundedCornerShape(16.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                unfocusedContainerColor = Color(0x99161D31),
                                focusedContainerColor = Color(0xCC1B243D),
                                unfocusedBorderColor = Color.White.copy(alpha = 0.14f),
                                focusedBorderColor = MavieTurquoise,
                            ),
                        )
                        Spacer(Modifier.height(6.dp))
                    }
                    if (state.tab in listOf(LibraryTab.FAVORITES, LibraryTab.PLAYLISTS) && state.query.isBlank()) {
                        Row(Modifier.padding(horizontal = 20.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip(
                                selected = state.tab == LibraryTab.FAVORITES,
                                onClick = { onTab(LibraryTab.FAVORITES) },
                                label = { Text("Favorilerim") },
                                shape = CircleShape,
                                colors = glassChipColors,
                                border = FilterChipDefaults.filterChipBorder(
                                    enabled = true,
                                    selected = state.tab == LibraryTab.FAVORITES,
                                    borderColor = Color.White.copy(alpha = 0.14f),
                                    selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                                ),
                            )
                            FilterChip(
                                selected = state.tab == LibraryTab.PLAYLISTS,
                                onClick = { onTab(LibraryTab.PLAYLISTS) },
                                label = { Text("Listelerim") },
                                shape = CircleShape,
                                colors = glassChipColors,
                                border = FilterChipDefaults.filterChipBorder(
                                    enabled = true,
                                    selected = state.tab == LibraryTab.PLAYLISTS,
                                    borderColor = Color.White.copy(alpha = 0.14f),
                                    selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                                ),
                            )
                        }
                    }
                    if (state.tab != LibraryTab.HOME && state.tab != LibraryTab.PLAYLISTS && state.categories.isNotEmpty()) {
                        LazyRow(contentPadding = PaddingValues(horizontal = 20.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            item("all") {
                                FilterChip(
                                    selected = state.selectedCategoryId.isBlank(),
                                    onClick = { onCategory("") },
                                    label = { Text("Tümü") },
                                    shape = CircleShape,
                                    colors = glassChipColors,
                                    border = glassChipBorder,
                                )
                            }
                            items(state.categories, key = { it.id }) { category ->
                                FilterChip(
                                    selected = category.id == state.selectedCategoryId,
                                    onClick = { onCategory(category.id) },
                                    shape = CircleShape,
                                    colors = glassChipColors,
                                    border = FilterChipDefaults.filterChipBorder(
                                        enabled = true,
                                        selected = category.id == state.selectedCategoryId,
                                        borderColor = Color.White.copy(alpha = 0.14f),
                                        selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                                    ),
                                    label = {
                                        Text(category.title, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 230.dp))
                                    },
                                )
                            }
                        }
                    }
                    // Keep the schedule out of overlapping Crossfade content so a single panel owns each fetch.
                    if (state.tab == LibraryTab.SPORTS) Box(Modifier.weight(1f)) { sportsContent() }
                    else Crossfade(
                        targetState = state.tab to state.query.isNotBlank(),
                        modifier = Modifier.weight(1f),
                        animationSpec = tween(if (reducedMotion) 0 else 190),
                        label = "library-tab",
                    ) { (tab, searching) ->
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
private fun ProfileAvatar(profileColor: String, selected: Boolean, modifier: Modifier = Modifier) {
    val parsedColor = runCatching { Color(android.graphics.Color.parseColor(profileColor)) }.getOrNull()
    val shape = RoundedCornerShape(8.dp)
    Box(
        modifier
            .clip(shape)
            .let { mod ->
                if (parsedColor != null) mod.background(parsedColor)
                else mod.background(MavieBrandDiagonalGradient)
            }
            .border(1.dp, Color.White.copy(alpha = if (selected) 0.7f else 0.3f), shape),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Icons.Outlined.Person, null, tint = Color.White, modifier = Modifier.fillMaxSize(.82f))
    }
}

@Composable
private fun HomeContent(
    state: LibraryUiState,
    onTab: (LibraryTab) -> Unit,
    onMedia: (UiMedia) -> Unit,
    onPlay: (UiMedia) -> Unit,
    onFavorite: (UiMedia) -> Unit,
    onRefresh: () -> Unit,
    onAddToCollection: (UiMedia) -> Unit,
) {
    val reducedMotion = rememberReducedMotion()
    LazyColumn(contentPadding = PaddingValues(top = 5.dp, bottom = 30.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
        val featured = state.featured ?: state.items.firstOrNull()
        if (state.showcase.isNotEmpty()) item("showcase") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SectionTitle("Yeni Çıkanlar")
                val pager = rememberPagerState(pageCount = { state.showcase.size })
                HorizontalPager(state = pager, key = { state.showcase[it].id }) { page ->
                    HeroCard(state.showcase[page], onMedia, onPlay, onAddToCollection)
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        repeat(state.showcase.size) { index ->
                            val active = pager.currentPage == index
                            val dotWidth by animateDpAsState(
                                targetValue = if (active) 20.dp else 6.dp,
                                animationSpec = tween(durationMillis = if (reducedMotion) 0 else 220),
                                label = "showcase-dot-$index",
                            )
                            Box(
                                Modifier
                                    .height(6.dp)
                                    .width(dotWidth)
                                    .clip(CircleShape)
                                    .background(if (active) MavieCyanDot else Color.White.copy(alpha = 0.28f)),
                            )
                        }
                    }
                    Box(
                        Modifier.mavieGlassSurface(CircleShape, topColor = MavieGlassPillFill, bottomColor = MavieGlassFillBottom),
                    ) {
                        Text(
                            text = "${pager.currentPage + 1} / ${state.showcase.size}",
                            color = MavieMuted,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
                        )
                    }
                }
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
        items(state.recommendations, key = { "recommendation-" + it.id }) { shelf ->
            MediaRow(shelf.title, shelf.items, onMedia, onFavorite, null, subtitle = shelf.subtitle)
        }
        if (state.recommendations.isNotEmpty()) item("discovery-credit") {
            Text("Keşif: Cinemeta ve Netflix Türkiye Top 10 listeleri yerel kütüphanen ve izleme geçmişinle eşleştirilir", Modifier.padding(horizontal = 20.dp), color = Color.Gray, fontSize = 11.sp)
        }
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
        val coverInteraction = remember { MutableInteractionSource() }
        val coverFocused by coverInteraction.collectIsFocusedAsState()
        Card(
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier.fillMaxWidth().height(heroHeight),
            border = BorderStroke(
                width = if (coverFocused) 2.dp else 1.dp,
                brush = if (coverFocused) MavieBrandDiagonalGradient else MavieSpecularBorderBrush,
            ),
            colors = CardDefaults.cardColors(containerColor = MaviePanel),
        ) {
            Box(Modifier.fillMaxSize()) {
                PosterArt(
                    media,
                    Modifier.fillMaxSize().clickable(
                        interactionSource = coverInteraction,
                        indication = LocalIndication.current,
                        onClickLabel = "Ayrıntılar",
                    ) { onMedia(media) },
                    backdrop = wide,
                )
                Box(Modifier.fillMaxSize().background(Brush.verticalGradient(
                    0f to Color.Transparent, .42f to Color.Transparent,
                    .75f to MavieBackground.copy(alpha = .68f), 1f to MavieBackground.copy(alpha = .94f))))
                Column(
                    Modifier.align(Alignment.BottomCenter).widthIn(max = 500.dp).fillMaxWidth().padding(18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        media.title, fontSize = 32.sp, lineHeight = 34.sp,
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        fontWeight = FontWeight.Black, maxLines = 3, overflow = TextOverflow.Ellipsis, color = Color.White,
                    )
                    Text(
                        listOf(media.year, mediaKind(media.kind), media.category).filter { it.isNotBlank() }.joinToString("  ·  "),
                        Modifier.padding(top = 8.dp), color = Color(0xFFDADADA), fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.height(12.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        MavieGradientButton(
                            onClick = { if (media.kind == "series") onMedia(media) else onPlay(media) },
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                            shape = RoundedCornerShape(16.dp),
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 11.dp),
                        ) {
                            Icon(Icons.Filled.PlayArrow, null, Modifier.size(23.dp), tint = Color.White); Spacer(Modifier.width(5.dp))
                            Text(if (media.canResume) "Devam Et" else "Oynat", fontSize = 14.sp, maxLines = 1, color = Color.White)
                        }
                        MavieGlassPillButton(
                            onClick = { onAddToCollection(media) },
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                            shape = RoundedCornerShape(16.dp),
                            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 11.dp),
                        ) {
                            Icon(Icons.Outlined.Add, null, Modifier.size(22.dp), tint = Color.White); Spacer(Modifier.width(5.dp))
                            Text("Listeme Ekle", fontSize = 13.sp, maxLines = 1, color = Color.White)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MediaRow(
    title: String,
    media: List<UiMedia>,
    onMedia: (UiMedia) -> Unit,
    onFavorite: (UiMedia) -> Unit,
    onAll: (() -> Unit)?,
    subtitle: String? = null,
) {
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
    LazyColumn(contentPadding = PaddingValues(bottom = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (suggestions.isEmpty()) item("prompt") {
            Text("İzlemek istediğin içeriğin adını yaz.", Modifier.padding(16.dp), color = MavieMuted)
        }
        else item("heading") { SectionTitle("Göz at") }
        items(suggestions, key = { it.id }) { media ->
            val interactionSource = remember { MutableInteractionSource() }
            val focused by interactionSource.collectIsFocusedAsState()
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp)
                    .mavieGlassSurface(RoundedCornerShape(16.dp), focused = focused)
                    .clickable(interactionSource = interactionSource, indication = LocalIndication.current) { onMedia(media) }
                    .padding(end = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PosterArt(media, Modifier.size(width = 128.dp, height = 72.dp).clip(RoundedCornerShape(16.dp)), backdrop = true)
                Text(media.title, Modifier.weight(1f).padding(horizontal = 12.dp), fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Icon(Icons.Outlined.PlayCircleOutline, "Ayrıntılar", tint = MavieCyanDot)
            }
        }
    }
}

@Composable
private fun CatalogContent(
    state: LibraryUiState,
    onMedia: (UiMedia) -> Unit,
    onFavorite: (UiMedia) -> Unit,
    onRefresh: () -> Unit,
    onLoadMore: () -> Unit,
    onCloseCollection: () -> Unit = {},
) {
    val gridState = rememberLazyGridState()
    val isTablet = androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp >= 600
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
    LazyVerticalGrid(
        state = gridState,
        columns = GridCells.Adaptive(if (isTablet) 144.dp else 108.dp),
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 9.dp, bottom = 28.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(21.dp),
    ) {
        item("heading", span = { GridItemSpan(maxLineSpan) }) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (state.tab == LibraryTab.PLAYLISTS && state.title.isNotBlank() && state.query.isBlank()) {
                    TextButton(onClick = onCloseCollection, modifier = Modifier.heightIn(min = 48.dp), contentPadding = PaddingValues(horizontal = 8.dp)) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Tüm listelerim", fontSize = 12.sp)
                    }
                }
                Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        if (state.query.isNotBlank()) "Arama sonuçları" else state.title.ifBlank { state.tab.title },
                        style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f),
                    )
                    if (state.totalCount > 0) Text("${state.totalCount} içerik", fontSize = 11.sp, color = MavieMuted, modifier = Modifier.padding(bottom = 4.dp))
                }
            }
        }
        if (state.error != null) item("error", span = { GridItemSpan(maxLineSpan) }) {
            MessagePanel("İçerikler yüklenemedi", state.error, action = "Yeniden dene", onAction = onRefresh)
        }
        if (state.loading && state.items.isEmpty()) {
            item("loading-banner", span = { GridItemSpan(maxLineSpan) }) {
                LoadingStageBanner(
                    title = "${state.tab.title} Hazırlanıyor",
                    subtitle = "Kütüphanendeki içerikler, kapaklar ve yayın bilgileri senkronize ediliyor…",
                )
            }
            items(9, key = { "loading-$it" }) { LoadingPoster() }
        }
        else gridItems(state.items, key = { it.id }, contentType = { "poster" }) { item -> PosterCard(item, { onMedia(item) }, { onFavorite(item) }) }
        if (!state.loading && state.items.isEmpty() && state.error == null) item("empty", span = { GridItemSpan(maxLineSpan) }) {
            MessagePanel(
                if (state.query.isNotBlank()) "Bir eşleşme bulamadık" else if (state.tab == LibraryTab.FAVORITES) "Sevdiklerini bir araya getir" else "Henüz burada içerik yok",
                if (state.query.isNotBlank()) "Başka bir adla aramayı veya farklı bir kategori seçmeyi deneyebilirsin."
                else if (state.tab == LibraryTab.FAVORITES) "Bir afişteki kalbe dokun. Favorilerin burada seni beklesin."
                else "Kütüphaneni yenileyerek tekrar deneyebilirsin.",
            )
        }
        if (state.hasMore) item("more", span = { GridItemSpan(maxLineSpan) }) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                OutlinedButton(onClick = onLoadMore, enabled = !state.loading, modifier = Modifier.heightIn(min = 48.dp)) {
                    if (state.loading) { CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)) }
                    Text("Daha fazla göster")
                }
            }
        }
    }
}

@Composable
private fun CollectionContent(
    state: LibraryUiState,
    onCollection: (UiCollection) -> Unit,
    onCreate: () -> Unit,
    onDelete: (UiCollection) -> Unit = {},
) {
    LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item("title") {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text("Kendi seçkilerin", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
                FilledTonalIconButton(onClick = onCreate, modifier = Modifier.size(48.dp)) {
                    Icon(Icons.Outlined.Add, "Yeni liste oluştur")
                }
            }
        }
        if (state.collections.isEmpty()) item("empty") {
            MessagePanel("Bir listeyle başla", "Hafta sonuna sakladıklarını veya bir bölüm daha dediklerini aynı yerde topla.", action = "İlk listemi oluştur", onAction = onCreate)
        }
        items(state.collections, key = { it.id }) { collection ->
            val interactionSource = remember { MutableInteractionSource() }
            val focused by interactionSource.collectIsFocusedAsState()
            Card(
                onClick = { onCollection(collection) },
                interactionSource = interactionSource,
                shape = RoundedCornerShape(18.dp),
                border = BorderStroke(if (focused) 2.dp else 1.dp, if (focused) MavieBrandDiagonalGradient else MavieSpecularBorderBrush),
                colors = CardDefaults.cardColors(containerColor = Color(0xB8141B2E)),
            ) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Outlined.Folder, null, tint = MavieTurquoise, modifier = Modifier.size(30.dp))
                    Column(Modifier.weight(1f).padding(start = 16.dp)) {
                        Text(collection.title, fontWeight = FontWeight.SemiBold)
                        Text("${collection.count} içerik", fontSize = 12.sp, color = MavieMuted, modifier = Modifier.padding(top = 4.dp))
                    }
                    MavieTooltipIconButton(
                        label = "${collection.title} listesini sil",
                        icon = Icons.Outlined.DeleteOutline,
                        onClick = { onDelete(collection) },
                        tint = MavieMuted,
                    )
                    Icon(Icons.Outlined.ChevronRight, null, tint = MavieMuted)
                }
            }
        }
    }
}
