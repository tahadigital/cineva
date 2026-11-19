package app.vrelio.player

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
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.*
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
import app.vrelio.player.data.MediaKind
import app.vrelio.player.player.PlayerScreen
import app.vrelio.player.player.UpNextEpisode
import app.vrelio.player.sports.VrelioSportsScreen
import app.vrelio.player.ui.*
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
        setContent { VrelioTheme { VrelioApplication(model) } }
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
fun VrelioApplication(model: MainViewModel) {
    val account by model.account.collectAsStateWithLifecycle()
    val reducedMotion = rememberReducedMotion()
    val sportsState = rememberSaveableStateHolder()
    var launch by rememberSaveable { mutableStateOf(true) }
    var syncDialog by rememberSaveable { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val exportFile = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri -> uri?.let(model::exportTo) }
    val importFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::importFrom) }
    val localVideoFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::playLocalUri) }
    LaunchedEffect(model.notice) { model.notice?.let { message -> snackbar.showSnackbar(message); if (model.notice == message) model.notice = null } }
    val playing = model.player
    if (launch) {
        val window = LocalActivity.current?.window
        val view = LocalView.current
        DisposableEffect(window, view) {
            val insets = window?.let { WindowCompat.getInsetsController(it, view) }
            insets?.hide(WindowInsetsCompat.Type.systemBars())
            onDispose { insets?.show(WindowInsetsCompat.Type.systemBars()) }
        }
        VrelioLaunchScreen(onFinished = { launch = false })
    } else if (playing != null) {
        PlayerScreen(
            title = playing.item.name, sourceUrl = playing.url, startPositionMs = playing.positionMs,
            isLive = playing.item.kind == MediaKind.LIVE,
            durationHintMs = ((playing.item.progress?.durationSeconds?.takeIf { it > 0 } ?: playing.item.durationSeconds) * 1000).toLong(),
            initialAudioTrack = playing.preference.audioId,
            initialSubtitleTrack = if (playing.preference.subtitleOff) -1 else playing.preference.subtitleId,
            nextEpisode = playing.nextEpisode?.let { UpNextEpisode(it.name, it.season, it.episode, it.backdrop.ifBlank { it.poster }) },
            onNextEpisode = { model.playNext(playing.generation) },
            onProgress = { position, duration -> model.saveProgress(playing.accountId, playing.item, position, duration) },
            onTrackSelection = { audio, subtitle -> model.saveTracks(playing.accountId, playing.item.id, audio, subtitle) },
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
                label = "vrelio-navigation",
            ) { screen ->
                when (screen) {
                    "setup" -> VrelioSetupScreen(
                        model.setupLoading, model.setupError, model::login, model::loginM3u, model::loginDemo,
                    ) { localVideoFile.launch(arrayOf("video/*")) }
                    "settings" -> VrelioSettingsScreen(
                        accountName = account?.let { "${it.name} · ${it.username}" }.orEmpty(),
                        catalogSummary = "Doğrudan cihaz içi oynatma · Bulut/masaüstü gerektirmez",
                        refreshing = model.library.refreshing,
                        error = model.library.error,
                        onBack = { model.settings = false },
                        onRefresh = model::refresh,
                        onExport = { exportFile.launch("Vrelio-Yedek-${LocalDate.now()}.json") },
                        onImport = { importFile.launch(arrayOf("application/json", "text/plain")) },
                        onSync = { syncDialog = true },
                        onLogout = model::logout,
                        versionName = BuildConfig.VERSION_NAME,
                        cloudState = model.cloudState,
                        cloudAuthStep = model.cloudAuthStep,
                        cloudPendingEmail = model.cloudPendingEmail,
                        cloudBusy = model.cloudBusy,
                        cloudError = model.cloudError,
                        cloudInfo = model.cloudInfo,
                        onSetAuthStep = model::setCloudAuthStep,
                        onCloudRegister = model::cloudRegister,
                        onCloudLogin = model::cloudLogin,
                        onCloudVerifyEmail = model::cloudVerifyEmail,
                        onCloudResendVerification = model::cloudResendVerification,
                        onCloudForgotPassword = model::cloudForgotPassword,
                        onCloudVerifyResetCode = model::cloudVerifyResetCode,
                        onCloudResetPassword = model::cloudResetPassword,
                        onCloudRedeem = model::cloudRedeem,
                        onCloudRemoveDevice = model::cloudRemoveDevice,
                        onCloudRefresh = model::refreshCloudStatus,
                        onCloudSync = model::cloudSync,
                        onCloudLogout = model::cloudLogout,
                    )
                    "detail" -> model.detail?.let { state ->
                        VrelioDetailScreen(
                            state, model::closeDetail, model::play, model::favorite, model::play, model::season,
                            { model.addToCollection(it) }, { model.detail?.media?.let(model::openDetail) }, model::clearProgress,
                        )
                    }
                    else -> VrelioLibraryScreen(
                        model.library, model::changeTab, model::search, model::category, model::openDetail, model::play,
                        model::favorite, model::refresh, { model.settings = true }, model::openCollection,
                        { model.addToCollection(null) }, model::loadMore, model::addToCollection, model::deleteCollection,
                        model::closeCollection, model.activeProfile.name, model.activeProfile.avatarColor,
                        { model.profileError = null; model.showProfilePicker = true }, model::surpriseMe,
                        { localVideoFile.launch(arrayOf("video/*")) },
                    ) {
                        sportsState.SaveableStateProvider("sports") {
                            VrelioSportsScreen(findChannels = model::findSportsChannels, onWatch = model::watchSportsChannel, epgUrl = account?.epgUrl.orEmpty())
                        }
                    }
                }
            }
            SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 90.dp, start = 18.dp, end = 18.dp))
        }
    }
    if (model.showCollectionPicker) VrelioCollectionPicker(model.collections, model::chooseCollection, model::createCollection) { model.showCollectionPicker = false }
    if (model.showProfilePicker) ProfilePickerDialog(model.profiles, model.profileError, model::switchProfile, model::createProfile, model::deleteProfile) { model.showProfilePicker = false }
    if (syncDialog) DesktopSyncDialog(onDismiss = { syncDialog = false }, onSync = { address, code -> syncDialog = false; model.syncMac(address, code) })
}

@Composable
private fun DesktopSyncDialog(onDismiss: () -> Unit, onSync: (String, String) -> Unit) {
    var address by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Masaüstü ile kayıtları birleştir") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("İsteğe bağlıdır. Aynı Wi-Fi ağında masaüstü Vrelio uygulaması açıkken favoriler, listeler ve en yeni izleme konumları birleştirilir.")
                OutlinedTextField(value = address, onValueChange = { address = it }, label = { Text("Masaüstü yerel ağ adresi") }, placeholder = { Text("http://192.168.1.10:8844") }, singleLine = true)
                OutlinedTextField(value = code, onValueChange = { code = it.filter(Char::isDigit).take(6) }, label = { Text("Altı haneli eşleştirme kodu") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true)
            }
        },
        confirmButton = { TextButton(onClick = { onSync(address, code) }, enabled = address.isNotBlank() && code.length == 6, modifier = Modifier.heightIn(min = 48.dp)) { Text("Birleştir") } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Vazgeç") } },
    )
}
