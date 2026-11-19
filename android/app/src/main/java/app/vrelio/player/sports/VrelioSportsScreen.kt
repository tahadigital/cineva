package app.vrelio.player.sports

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.vrelio.player.ui.VrelioCoral
import app.vrelio.player.ui.VrelioMuted
import app.vrelio.player.ui.VrelioTooltipIconButton
import kotlinx.coroutines.CancellationException
import java.time.LocalDate
import java.time.LocalTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private val Card = RoundedCornerShape(6.dp)
private val DateLabel = DateTimeFormatter.ofPattern("d MMM EEE", Locale.forLanguageTag("tr-TR"))
private val Clock = DateTimeFormatter.ofPattern("HH:mm")

@Composable
fun VrelioSportsScreen(
    findChannels: suspend (List<String>) -> Map<String, String>,
    onWatch: (String) -> Unit,
    epgUrl: String = "",
) {
    val today = remember { LocalDate.now(Istanbul) }
    var dayString by rememberSaveable { mutableStateOf(today.toString()) }
    val day = LocalDate.parse(dayString)
    val dates = remember(today) { (-1L..8L).map(today::plusDays) }
    var refresh by remember { mutableIntStateOf(0) }
    var result by remember { mutableStateOf<SportsListings?>(null) }
    var channels by remember { mutableStateOf<Map<String, String>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var search by rememberSaveable { mutableStateOf("") }
    var category by rememberSaveable { mutableStateOf("") }

    LaunchedEffect(day, refresh, epgUrl) {
        result = null
        channels = null
        error = null
        try {
            result = SportsGuide.load(day, force = refresh != 0, epgUrl = epgUrl)
            val labels = result?.events.orEmpty().flatMap { it.channels }.distinct()
            channels = try {
                findChannels(labels)
            } catch (error: CancellationException) {
                throw error
            } catch (_: Exception) {
                emptyMap()
            }
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (failure: Exception) {
            error = failure.message ?: "Yayın akışı yüklenemedi."
        }
    }

    val events = result?.events.orEmpty()
    val categories = remember(events) {
        events.map { it.sport }.distinct().sortedWith(java.text.Collator.getInstance(Locale.forLanguageTag("tr-TR")))
    }
    val filtered = remember(events, category, search) {
        val term = SportsChannels.fold(search.trim())
        events.filter { entry ->
            (category.isEmpty() || entry.sport == category) &&
                (term.isEmpty() || SportsChannels.fold(
                    listOf(entry.title, entry.league, entry.sport).plus(entry.channels).joinToString(" ")
                ).contains(term))
        }
    }
    val spotlight = remember(events, day, today) {
        val current = LocalTime.now(Istanbul)
        val now = current.format(Clock)
        val cutoff = current.minusHours(2).format(Clock).let { if (it <= now) it else "00:00" }
        events.asSequence().filter { day > today || day == today && it.time >= cutoff }.maxByOrNull {
            if (it.featured) 1 else 0
        }
    }

    LazyColumn(
        Modifier.fillMaxSize().testTag("sportsGuide"),
        contentPadding = PaddingValues(bottom = 18.dp),
    ) {
        item("intro") {
            Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 10.dp)) {
                Text("VRELIO REHBER", color = VrelioCoral, fontWeight = FontWeight.Bold, fontSize = 11.sp, letterSpacing = 2.sp)
                Text("Canlı Yayın & EPG Rehberi", style = MaterialTheme.typography.headlineLarge, fontWeight = FontWeight.ExtraBold)
                Text("XMLTV program akışı ve eşleşen canlı yayınlar", color = VrelioMuted, fontSize = 13.sp)
            }
        }
        item("dates") {
            LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(dates, key = { it.toString() }) { date ->
                    val label = when (date) {
                        today.minusDays(1) -> "Dün"
                        today -> "Bugün"
                        today.plusDays(1) -> "Yarın"
                        else -> date.format(DateLabel)
                    }
                    SportsChip(label, day == date) {
                        if (day != date) {
                            result = null
                            channels = null
                            error = null
                            category = ""
                            refresh = 0
                            dayString = date.toString()
                        }
                    }
                }
            }
        }
        if (result == null) {
            item("status") {
                Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    if (error == null) {
                        CircularProgressIndicator(Modifier.size(27.dp), strokeWidth = 2.dp)
                        Text("Yayın akışı yükleniyor…", Modifier.padding(top = 12.dp), color = VrelioMuted)
                    } else {
                        Text(error.orEmpty(), color = VrelioMuted)
                        TextButton(onClick = { refresh++ }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Tekrar dene") }
                    }
                }
            }
        } else {
            if (result?.stale == true) item("stale") {
                Text("Son alınan yayın akışı gösteriliyor.", Modifier.padding(horizontal = 16.dp), color = VrelioMuted)
            }
            if (spotlight != null) item("spotlight") {
                Column(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 9.dp)
                        .background(Brush.horizontalGradient(listOf(Color(0xFF1D1724), Color(0xFF3E1C22))), Card)
                        .border(1.dp, Color(0xFF5D343C), Card).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(5.dp),
                ) {
                    Text("ÖNE ÇIKAN YAYIN", color = VrelioCoral, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.5.sp)
                    Text(spotlight.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.ExtraBold)
                    Text("${spotlight.time} · ${spotlight.league.ifBlank { spotlight.sport }}", color = Color(0xFFDDDDDD), fontSize = 13.sp)
                    ChannelButtons(spotlight, channels, onWatch)
                }
            }
            item("filters") {
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("Yayın Akışı", Modifier.weight(1f), style = MaterialTheme.typography.titleLarge)
                        VrelioTooltipIconButton(
                            label = "Yayın akışını yenile",
                            icon = Icons.Outlined.Refresh,
                            onClick = { refresh++ },
                        )
                    }
                    if (events.isNotEmpty()) OutlinedTextField(
                        value = search, onValueChange = { search = it }, singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("Program veya kanal ara") },
                        leadingIcon = { Icon(Icons.Outlined.Search, null) },
                        shape = Card,
                    )
                }
            }
            if (categories.isNotEmpty()) item("disciplines") {
                LazyRow(
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 5.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    item("all") { SportsChip("Tümü", category.isEmpty()) { category = "" } }
                    items(categories, key = { it }) { name -> SportsChip(name, category == name) { category = name } }
                }
            }
            if (filtered.isEmpty()) item("empty") {
                Text(
                    when {
                        result?.configured == false -> "Henüz bir XMLTV yayın rehberi (EPG) bağlanmadı. Ayarlardan veya M3U listenden bir rehber adresi ekleyebilirsin."
                        events.isEmpty() -> "Bu gün için yayın bilgisi listelenmiyor."
                        else -> "Bu filtreye uyan yayın yok."
                    },
                    Modifier.padding(16.dp), color = VrelioMuted,
                )
            }
            items(filtered, key = { "event-${it.id}" }) { event ->
                Column(Modifier.padding(horizontal = 16.dp)) {
                    HorizontalDivider(color = Color(0xFF282D3B))
                    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(event.time, Modifier.width(48.dp), fontWeight = FontWeight.ExtraBold, fontSize = 14.sp)
                        Column(Modifier.weight(1f)) {
                            Text(listOf(event.sport, event.league).filter(String::isNotBlank).joinToString(" · "),
                                color = VrelioMuted, fontSize = 11.sp)
                            Text(event.title, style = MaterialTheme.typography.titleMedium)
                            ChannelButtons(event, channels, onWatch)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SportsChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(
        selected, onClick, label = { Text(label, maxLines = 1) }, shape = RoundedCornerShape(32.dp),
        colors = FilterChipDefaults.filterChipColors(selectedContainerColor = Color.White, selectedLabelColor = Color.Black),
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChannelButtons(event: SportBroadcast, matches: Map<String, String>?, onWatch: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        event.channels.forEach { channel ->
            val match = matches?.get(channel)
            if (match != null) {
                Button(
                    onClick = { onWatch(match) },
                    modifier = Modifier.defaultMinSize(minHeight = 48.dp)
                        .semantics { contentDescription = "${event.title} · $channel kanalını aç" },
                    shape = Card, colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFF1F1F1), contentColor = Color.Black),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                ) {
                    Icon(Icons.Filled.PlayArrow, null, Modifier.size(15.dp))
                    Spacer(Modifier.width(5.dp))
                    Text(channel, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                }
            } else {
                Row(
                    Modifier.padding(vertical = 6.dp)
                        .border(1.dp, Color(0xFF4B5163), Card)
                        .padding(horizontal = 8.dp, vertical = 7.dp)
                        .semantics(mergeDescendants = true) {
                            contentDescription = "$channel (IPTV listende bulunamadı)"
                        },
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(channel, fontSize = 12.sp)
                    if (matches != null) Text("Listende yok", color = VrelioMuted, fontSize = 10.sp)
                }
            }
        }
    }
}
