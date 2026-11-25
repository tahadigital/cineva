package app.mavie.player

import android.app.PictureInPictureParams
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.Rational
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.LocalActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.mavie.player.data.MediaKind
import app.mavie.player.player.PlayerScreen
import app.mavie.player.player.UpNextEpisode
import app.mavie.player.sports.MavieSportsScreen
import app.mavie.player.ui.*
import java.time.LocalDate

class MainActivity : ComponentActivity() {
    private val model: MainViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
        )
        if (Build.VERSION.SDK_INT >= 29) window.isNavigationBarContrastEnforced = false
        val restoredInstanceState = savedInstanceState != null
        setContent { MavieTheme { MavieApplication(model, restoredInstanceState) } }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && model.player != null) {
            runCatching {
                enterPictureInPictureMode(
                    PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build()
                )
            }
        }
    }
}

@Composable
fun MavieApplication(model: MainViewModel, restoredInstanceState: Boolean = false) {
    val account by model.account.collectAsStateWithLifecycle()
    val reducedMotion = rememberReducedMotion()
    val sportsState = rememberSaveableStateHolder()
    var launch by rememberSaveable { mutableStateOf(!restoredInstanceState && !model.splashCompleted) }
    var syncDialog by rememberSaveable { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val exportFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(model::exportTo) }
    val importFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::importFrom) }
    val localVideoFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::playLocalUri) }
    fun <I> launchSaf(launcher: ActivityResultLauncher<I>, input: I) {
        runCatching { launcher.launch(input) }.onFailure {
            model.notice = "Bu cihazda dosya seçici bulunamadı."
        }
    }
    LaunchedEffect(model.notice) { model.notice?.let { message -> snackbar.showSnackbar(message); if (model.notice == message) model.notice = null } }
    LaunchedEffect(model.syncSuccess) {
        if (model.syncSuccess) {
            syncDialog = false
            model.syncSuccess = false
        }
    }
    val playing = model.player
    if (launch) {
        val window = LocalActivity.current?.window
        val view = LocalView.current
        DisposableEffect(window, view) {
            val insets = window?.let { WindowCompat.getInsetsController(it, view) }
            insets?.hide(WindowInsetsCompat.Type.systemBars())
            onDispose { insets?.show(WindowInsetsCompat.Type.systemBars()) }
        }
        MavieLaunchScreen(onFinished = {
            model.splashCompleted = true
            launch = false
        })
    } else if (playing != null) {
        PlayerScreen(
            title = playing.item.name, sourceUrl = playing.url, startPositionMs = playing.positionMs,
            isLive = playing.item.kind == MediaKind.LIVE,
            durationHintMs = ((playing.item.progress?.durationSeconds?.takeIf { it > 0 } ?: playing.item.durationSeconds) * 1000).toLong(),
            initialAudioTrack = playing.preference.audioId,
            initialSubtitleTrack = if (playing.preference.subtitleOff) -1 else playing.preference.subtitleId,
            nextEpisode = playing.nextEpisode?.let { UpNextEpisode(it.name, it.season, it.episode, it.backdrop.ifBlank { it.poster }) },
            onNextEpisode = { model.playNext(playing.generation) },
            onProgress = { position, duration -> model.saveProgress(playing.accountId, playing.item, position, duration, playing.profileId) },
            onTrackSelection = { audio, subtitle -> model.saveTracks(playing.accountId, playing.item.id, audio, subtitle, playing.profileId) },
            episodes = playing.episodes,
            currentEpisodeId = playing.item.id,
            onSelectEpisode = model::playEpisodeById,
            onBack = model::closePlayer,
        )
    } else {
        BackHandler(enabled = model.settings || model.detail != null || account != null && model.library.tab != LibraryTab.HOME) {
            when {
                model.settings -> model.settings = false
                model.detail != null -> model.closeDetail()
                model.library.tab == LibraryTab.PLAYLISTS && model.library.title.isNotBlank() -> model.closeCollection()
                else -> model.changeTab(LibraryTab.HOME)
            }
        }
        Box(Modifier.fillMaxSize()) {
            Crossfade(
                targetState = when { account == null -> "setup"; model.settings -> "settings"; model.detail != null -> "detail"; else -> "library" },
                animationSpec = tween(if (reducedMotion) 0 else 220),
                label = "mavie-navigation",
            ) { screen ->
                when (screen) {
                    "setup" -> MavieSetupScreen(
                        loading = model.setupLoading,
                        error = model.setupError,
                        onSubmit = model::login,
                        onM3uSubmit = model::loginM3u,
                        onDemo = model::loginDemo,
                        onOpenLocalFile = { launchSaf(localVideoFile, arrayOf("video/*")) },
                        errorCode = model.setupErrorCode,
                    )
                    "settings" -> MavieSettingsScreen(
                        accountName = account?.let { "${it.name} · ${it.username}" }.orEmpty(),
                        catalogSummary = "Doğrudan cihaz içi oynatma · Hesap ve masaüstü gerektirmez",
                        refreshing = model.library.refreshing,
                        error = model.library.error,
                        onBack = { model.settings = false },
                        onRefresh = model::refresh,
                        onExport = { launchSaf(exportFile, "Mavie-Yedek-${LocalDate.now()}.json") },
                        onImport = { launchSaf(importFile, arrayOf("application/json", "text/plain")) },
                        onSync = {
                            model.syncError = null
                            model.syncSuccess = false
                            syncDialog = true
                        },
                        onLogout = model::logout,
                        versionName = BuildConfig.VERSION_NAME,
                        errorCode = model.library.errorCode,
                        epgUrl = account?.epgUrl.orEmpty(),
                        onSaveEpgUrl = model::updateEpgUrl,
                    )
                    "detail" -> model.detail?.let { state ->
                        MavieDetailScreen(
                            state, model::closeDetail, model::play, model::favorite, model::play, model::season,
                            { model.addToCollection(it) }, { model.detail?.media?.let(model::openDetail) }, model::clearProgress,
                        )
                    }
                    else -> MavieLibraryScreen(
                        model.library, model::changeTab, model::search, model::category, model::openDetail, model::play,
                        model::favorite, model::refresh, { model.settings = true }, model::openCollection,
                        { model.addToCollection(null) }, model::loadMore, model::addToCollection, model::deleteCollection,
                        model::closeCollection, model.activeProfile.name, model.activeProfile.avatarColor,
                        { model.profileError = null; model.showProfilePicker = true }, model::surpriseMe,
                        { launchSaf(localVideoFile, arrayOf("video/*")) },
                    ) {
                        sportsState.SaveableStateProvider("sports") {
                            MavieSportsScreen(findChannels = model::findSportsChannels, onWatch = model::watchSportsChannel, epgUrl = account?.epgUrl.orEmpty())
                        }
                    }
                }
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 90.dp, start = 18.dp, end = 18.dp))
        }
    }
    if (model.showCollectionPicker) MavieCollectionPicker(model.collections, model::chooseCollection, model::createCollection) { model.showCollectionPicker = false }
    if (model.showProfilePicker) ProfilePickerDialog(model.profiles, model.profileError, model::switchProfile, model::createProfile, model::deleteProfile) { model.showProfilePicker = false }
    if (syncDialog) {
        DesktopSyncDialog(
            loading = model.syncLoading,
            error = model.syncError,
            onDismiss = { if (!model.syncLoading) syncDialog = false },
            onSync = model::syncMac,
        )
    }
}

@Composable
private fun DesktopSyncDialog(
    loading: Boolean,
    error: String?,
    onDismiss: () -> Unit,
    onSync: (String, String) -> Unit,
) {
    var address by rememberSaveable { mutableStateOf("") }
    // Ephemeral 6-digit pairing code stays out of Android's saved instance state.
    var code by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = { if (!loading) onDismiss() },
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        title = { Text("Masaüstü ile kayıtları birleştir") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("İsteğe bağlıdır. Aynı Wi-Fi ağında masaüstü Mavie uygulaması açıkken favoriler, listeler ve en yeni izleme konumları birleştirilir.")
                OutlinedTextField(
                    value = address,
                    onValueChange = { address = it },
                    label = { Text("Masaüstü yerel ağ adresi") },
                    placeholder = { Text("http://192.168.1.10:8844") },
                    enabled = !loading,
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                )
                OutlinedTextField(
                    value = code,
                    onValueChange = { code = it.filter(Char::isDigit).take(6) },
                    label = { Text("Altı haneli eşleştirme kodu") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    enabled = !loading,
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                )
                if (loading) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MavieTurquoise)
                        Text("Masaüstü ile eşleştiriliyor…", color = MavieMuted, style = MaterialTheme.typography.bodySmall)
                    }
                }
                if (!error.isNullOrBlank()) {
                    Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSync(address, code) },
                enabled = !loading && address.isNotBlank() && code.length == 6,
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text(if (loading) "Eşitleniyor…" else "Birleştir") }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                enabled = !loading,
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text("Vazgeç") }
        },
    )
}
