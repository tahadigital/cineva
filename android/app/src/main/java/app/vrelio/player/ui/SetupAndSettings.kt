package app.vrelio.player.ui

import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.*
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.DeleteOutline
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Verified
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.vrelio.player.CloudAuthStep
import app.vrelio.player.data.CloudAccountState
import kotlinx.coroutines.delay
import java.time.Duration
import java.time.Instant

const val DEFAULT_CLOUD_URL = "https://cineva-app.netlify.app"

@Composable
fun VrelioSetupScreen(
    loading: Boolean,
    error: String?,
    onSubmit: (String, String, String, String) -> Unit,
    onM3uSubmit: (String, String, String) -> Unit = { _, _, _ -> },
    onDemo: () -> Unit = {},
    onOpenLocalFile: () -> Unit = {},
) {
    var mode by rememberSaveable { mutableStateOf("m3u") }
    var name by rememberSaveable { mutableStateOf("Kişisel Liste") }
    var m3uUrl by rememberSaveable { mutableStateOf("") }
    var host by rememberSaveable { mutableStateOf("") }
    var username by rememberSaveable { mutableStateOf("") }
    // Password is deliberately not saveable in Android's instance-state bundle.
    var password by remember { mutableStateOf("") }
    var epgUrl by rememberSaveable { mutableStateOf("") }
    var reveal by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    val keyboard = LocalSoftwareKeyboardController.current

    fun normalize(rawInput: String): String {
        val raw = rawInput.trim().trimEnd('/')
        return if (raw.isNotBlank() && !raw.contains("://")) "http://$raw" else raw
    }

    fun submit() {
        if (loading) return
        val normalizedEpg = epgUrl.trim().takeIf { it.isNotBlank() }?.let(::normalize).orEmpty()
        if (normalizedEpg.isNotBlank()) {
            val epgUri = runCatching { Uri.parse(normalizedEpg) }.getOrNull()
            if (epgUri?.scheme !in listOf("http", "https") || epgUri?.host.isNullOrBlank()) {
                localError = "EPG adresi http:// veya https:// ile başlamalı."
                return
            }
        }
        if (mode == "m3u") {
            val normalizedM3u = normalize(m3uUrl)
            val uri = runCatching { Uri.parse(normalizedM3u) }.getOrNull()
            localError = if (uri?.scheme !in listOf("http", "https") || uri?.host.isNullOrBlank()) {
                "Geçerli bir M3U / M3U8 liste adresi gir."
            } else null
            if (localError == null) {
                keyboard?.hide()
                onM3uSubmit(name.trim().ifBlank { "M3U Listesi" }, normalizedM3u, normalizedEpg)
            }
            return
        }
        val normalizedHost = normalize(host)
        val uri = runCatching { Uri.parse(normalizedHost) }.getOrNull()
        localError = when {
            uri?.scheme !in listOf("http", "https") || uri?.host.isNullOrBlank() -> "http:// veya https:// ile başlayan sunucu adresini gir."
            username.isBlank() -> "Kullanıcı adını gir."
            password.isBlank() -> "Parolanı gir."
            else -> null
        }
        if (localError == null) {
            keyboard?.hide()
            onSubmit(normalizedHost, username.trim(), password, normalizedEpg)
        }
    }

    Box(Modifier.fillMaxSize().background(VrelioBackground)) {
        Column(
            Modifier.fillMaxSize().systemBarsPadding().imePadding().verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(16.dp))
            VrelioWordmark(large = true)
            Spacer(Modifier.height(22.dp))
            Text("Kendi ekranına hoş geldin.", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(
                "Filmler, diziler ve canlı yayınlar.\nKendi kaynağınla bağlan ya da açık sinema demosuyla hemen izle.",
                Modifier.padding(top = 10.dp), color = VrelioMuted, style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(18.dp))
            OutlinedButton(
                onClick = { if (!loading) onDemo() },
                enabled = !loading,
                modifier = Modifier.fillMaxWidth().widthIn(max = 520.dp).height(48.dp),
                shape = RoundedCornerShape(6.dp),
            ) {
                Icon(Icons.Filled.PlayArrow, null, Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("Açık Sinema ile Hemen Dene (Demo)")
            }
            Spacer(Modifier.height(10.dp))
            TextButton(
                onClick = { if (!loading) onOpenLocalFile() },
                enabled = !loading,
                modifier = Modifier.fillMaxWidth().widthIn(max = 520.dp).heightIn(min = 48.dp),
            ) {
                Icon(Icons.Outlined.FolderOpen, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("Cihazdan Yerel Video Aç (.mp4, .mkv, .avi)")
            }
            Spacer(Modifier.height(14.dp))
            Surface(shape = RoundedCornerShape(8.dp), color = VrelioPanel, modifier = Modifier.widthIn(max = 520.dp)) {
                Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("Medya kaynağı bağla", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = mode == "m3u", onClick = { mode = "m3u"; localError = null }, label = { Text("M3U / Liste") })
                        FilterChip(selected = mode == "xtream", onClick = { mode = "xtream"; localError = null }, label = { Text("Xtream Sunucu") })
                    }
                    if (mode == "m3u") {
                        OutlinedTextField(
                            value = name, onValueChange = { name = it; localError = null }, label = { Text("Liste adı") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = m3uUrl, onValueChange = { m3uUrl = it; localError = null }, label = { Text("M3U / M3U8 adresi") },
                            placeholder = { Text("https://example.com/playlist.m3u8", fontSize = 13.sp) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                        )
                    } else {
                        OutlinedTextField(
                            value = host, onValueChange = { host = it; localError = null }, label = { Text("Sunucu adresi") },
                            placeholder = { Text("https://sunucun:8080", fontSize = 13.sp) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = username, onValueChange = { username = it; localError = null }, label = { Text("Kullanıcı adı") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, autoCorrectEnabled = false, imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = password, onValueChange = { password = it; localError = null }, label = { Text("Parola") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            visualTransformation = if (reveal) VisualTransformation.None else PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Next),
                            trailingIcon = {
                                IconButton(onClick = { reveal = !reveal }, modifier = Modifier.size(48.dp)) {
                                    Icon(if (reveal) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility, if (reveal) "Parolayı gizle" else "Parolayı göster")
                                }
                            },
                        )
                    }
                    OutlinedTextField(
                        value = epgUrl, onValueChange = { epgUrl = it; localError = null }, label = { Text("XMLTV EPG adresi (İsteğe bağlı)") },
                        placeholder = { Text("https://example.com/guide.xml", fontSize = 13.sp) }, singleLine = true,
                        modifier = Modifier.fillMaxWidth(), enabled = !loading,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { submit() }),
                    )
                    val message = localError ?: error
                    if (message != null) Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    Button(onClick = { submit() }, enabled = !loading, modifier = Modifier.fillMaxWidth().height(50.dp), shape = RoundedCornerShape(6.dp)) {
                        if (loading) {
                            CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(if (loading) "Kütüphanen hazırlanıyor…" else "Bağlan")
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
            Row(Modifier.fillMaxWidth().widthIn(max = 520.dp), verticalAlignment = Alignment.Top) {
                Icon(Icons.Outlined.Lock, null, Modifier.padding(top = 2.dp).size(15.dp), tint = VrelioMuted)
                Text(
                    "Vrelio telifli yayın barındırmaz; yalnızca kendi eklediğin yasal kaynakları veya açık sinema demosunu oynatır.",
                    Modifier.padding(start = 9.dp), color = VrelioMuted, fontSize = 11.sp, lineHeight = 17.sp,
                )
            }
        }
    }
}

@Composable
fun VrelioSettingsScreen(
    accountName: String,
    catalogSummary: String,
    refreshing: Boolean,
    error: String?,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onExport: () -> Unit,
    onImport: () -> Unit,
    onSync: () -> Unit,
    onLogout: () -> Unit,
    versionName: String = "2.1.0",
    cloudState: CloudAccountState = CloudAccountState(),
    cloudAuthStep: CloudAuthStep = CloudAuthStep.IDLE,
    cloudPendingEmail: String = "",
    cloudBusy: Boolean = false,
    cloudError: String? = null,
    cloudInfo: String? = null,
    onSetAuthStep: (CloudAuthStep, String?) -> Unit = { _, _ -> },
    onCloudRegister: (url: String, email: String, password: String, displayName: String) -> Unit = { _, _, _, _ -> },
    onCloudLogin: (url: String, email: String, password: String) -> Unit = { _, _, _ -> },
    onCloudVerifyEmail: (url: String, email: String, code: String) -> Unit = { _, _, _ -> },
    onCloudResendVerification: (url: String, email: String) -> Unit = { _, _ -> },
    onCloudForgotPassword: (url: String, email: String) -> Unit = { _, _ -> },
    onCloudVerifyResetCode: (url: String, email: String, code: String) -> Unit = { _, _, _ -> },
    onCloudResetPassword: (url: String, email: String, code: String, newPassword: String) -> Unit = { _, _, _, _ -> },
    onCloudRedeem: (code: String) -> Unit = {},
    onCloudRemoveDevice: (deviceId: String) -> Unit = {},
    onCloudRefresh: () -> Unit = {},
    onCloudSync: () -> Unit = {},
    onCloudLogout: () -> Unit = {},
) {
    val context = LocalContext.current
    var confirmLogout by remember { mutableStateOf(false) }
    var showLicenses by remember { mutableStateOf(false) }
    val noticeText = remember {
        runCatching { context.assets.open("NOTICE.txt").bufferedReader().use { it.readText() } }
            .getOrDefault("Vrelio · Apache 2.0 / LibVLC (LGPL-2.1+)")
    }
    Scaffold(containerColor = VrelioBackground) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())) {
            Row(Modifier.fillMaxWidth().padding(start = 8.dp, end = 20.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                VrelioTooltipIconButton(
                    label = "Geri dön",
                    icon = Icons.AutoMirrored.Outlined.ArrowBack,
                    onClick = onBack,
                )
                Text("Ayarlar", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(start = 8.dp))
            }
            Column(Modifier.padding(20.dp).widthIn(max = 720.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                SettingsCard("Senin bağlantın", "Yayınlar bu cihazda doğrudan oynatılır.") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.CheckCircle, null, tint = Color(0xFF8DCDB2), modifier = Modifier.size(20.dp))
                        Text(accountName.ifBlank { "Medya kaynağı" }, Modifier.padding(start = 10.dp), fontWeight = FontWeight.SemiBold)
                    }
                    if (catalogSummary.isNotBlank()) Text(catalogSummary, style = MaterialTheme.typography.bodySmall, color = VrelioMuted)
                    Button(
                        onClick = onRefresh,
                        enabled = !refreshing,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(6.dp),
                    ) {
                        if (refreshing) CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                        else Icon(Icons.Outlined.Refresh, null, Modifier.size(19.dp))
                        Spacer(Modifier.width(8.dp)); Text(if (refreshing) "Yenileniyor…" else "Kütüphaneyi yenile")
                    }
                    if (error != null) Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
                SettingsCard("Kütüphanen seninle", "Favorilerini, listelerini ve izleme kayıtlarını taşı.") {
                    OutlinedButton(
                        onClick = onExport,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(6.dp),
                    ) {
                        Icon(Icons.Outlined.FileDownload, null, Modifier.size(19.dp)); Spacer(Modifier.width(8.dp)); Text("Yedek dışa aktar")
                    }
                    OutlinedButton(
                        onClick = onImport,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(6.dp),
                    ) {
                        Icon(Icons.Outlined.FileUpload, null, Modifier.size(19.dp)); Spacer(Modifier.width(8.dp)); Text("Yedek içe aktar")
                    }
                    TextButton(
                        onClick = onSync,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) {
                        Icon(Icons.Outlined.Devices, null, Modifier.size(19.dp)); Spacer(Modifier.width(8.dp)); Text("Masaüstü ile eşitle")
                    }
                }
                CloudAccountCard(
                    cloudState = cloudState,
                    cloudAuthStep = cloudAuthStep,
                    cloudPendingEmail = cloudPendingEmail,
                    cloudBusy = cloudBusy,
                    cloudError = cloudError,
                    cloudInfo = cloudInfo,
                    onSetAuthStep = onSetAuthStep,
                    onCloudRegister = onCloudRegister,
                    onCloudLogin = onCloudLogin,
                    onCloudVerifyEmail = onCloudVerifyEmail,
                    onCloudResendVerification = onCloudResendVerification,
                    onCloudForgotPassword = onCloudForgotPassword,
                    onCloudVerifyResetCode = onCloudVerifyResetCode,
                    onCloudResetPassword = onCloudResetPassword,
                    onCloudRedeem = onCloudRedeem,
                    onCloudRemoveDevice = onCloudRemoveDevice,
                    onCloudRefresh = onCloudRefresh,
                    onCloudSync = onCloudSync,
                    onCloudLogout = onCloudLogout,
                )
                SettingsCard("Yasal Bilgiler & Lisanslar", "Gizlilik, kullanım koşulları ve açık kaynak bildirimleri.") {
                    Text(
                        "Vrelio telifli içerik sağlamaz, barındırmaz veya dağıtmaz. Yalnızca kullanıcının eklediği açık veya yasal kaynakları oynatır.",
                        color = VrelioMuted, style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedButton(
                        onClick = { showLicenses = true },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(6.dp),
                    ) {
                        Icon(Icons.Outlined.Description, null, Modifier.size(19.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Açık Kaynak Lisansları ve Bildirimler")
                    }
                }
                TextButton(
                    onClick = { confirmLogout = true },
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                ) {
                    Icon(Icons.AutoMirrored.Outlined.Logout, null, Modifier.size(19.dp)); Spacer(Modifier.width(8.dp)); Text("Kaynaktan çıkış yap")
                }
                Column(Modifier.fillMaxWidth().padding(vertical = 16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    VrelioWordmark()
                    Text("Sürüm $versionName · Android", Modifier.padding(top = 7.dp), color = VrelioMuted, fontSize = 11.sp)
                }
            }
        }
    }
    if (showLicenses) AlertDialog(
        onDismissRequest = { showLicenses = false },
        title = { Text("Yasal Bilgiler & Lisanslar") },
        text = { Text(noticeText, modifier = Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()), fontSize = 12.sp, lineHeight = 18.sp) },
        confirmButton = { TextButton(onClick = { showLicenses = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Kapat") } },
    )
    if (confirmLogout) AlertDialog(
        onDismissRequest = { confirmLogout = false },
        title = { Text("Kaynaktan çıkılsın mı?") },
        text = { Text("Bu cihazda yeniden izlemek için kaynak bilgilerini tekrar girmen veya demo modunu seçmen gerekir.") },
        confirmButton = { TextButton(onClick = { confirmLogout = false; onLogout() }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Çıkış yap") } },
        dismissButton = { TextButton(onClick = { confirmLogout = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Vazgeç") } },
    )
}

@Composable
private fun CloudAccountCard(
    cloudState: CloudAccountState,
    cloudAuthStep: CloudAuthStep,
    cloudPendingEmail: String,
    cloudBusy: Boolean,
    cloudError: String?,
    cloudInfo: String?,
    onSetAuthStep: (CloudAuthStep, String?) -> Unit,
    onCloudRegister: (String, String, String, String) -> Unit,
    onCloudLogin: (String, String, String) -> Unit,
    onCloudVerifyEmail: (String, String, String) -> Unit,
    onCloudResendVerification: (String, String) -> Unit,
    onCloudForgotPassword: (String, String) -> Unit,
    onCloudVerifyResetCode: (String, String, String) -> Unit,
    onCloudResetPassword: (String, String, String, String) -> Unit,
    onCloudRedeem: (String) -> Unit,
    onCloudRemoveDevice: (String) -> Unit,
    onCloudRefresh: () -> Unit,
    onCloudSync: () -> Unit,
    onCloudLogout: () -> Unit,
) {
    SettingsCard(
        "Vrelio Hesabı & Pro Plan (İsteğe Bağlı)",
        "Yalnızca plan, profil senkronizasyonu ve cihaz limiti bulutta tutulur; medya kaynaklarınız cihazınızda kalır.",
    ) {
        if (cloudState.announcementMessage.isNotBlank()) {
            Surface(
                color = VrelioCoral.copy(alpha = 0.16f),
                shape = RoundedCornerShape(6.dp),
                border = BorderStroke(1.dp, VrelioCoral.copy(alpha = 0.45f)),
            ) {
                Text(
                    "${cloudState.announcementTitle}: ${cloudState.announcementMessage}",
                    color = Color.White,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.fillMaxWidth().padding(10.dp),
                )
            }
        }
        AnimatedVisibility(visible = !cloudInfo.isNullOrBlank()) {
            Surface(
                color = Color(0xFF1A3429),
                shape = RoundedCornerShape(6.dp),
                border = BorderStroke(1.dp, Color(0xFF3E8E6E)),
            ) {
                Text(cloudInfo.orEmpty(), color = Color(0xFFC5F4DE), fontSize = 12.sp, modifier = Modifier.fillMaxWidth().padding(10.dp))
            }
        }
        AnimatedVisibility(visible = !cloudError.isNullOrBlank()) {
            Surface(
                color = Color(0xFF3B1A1D),
                shape = RoundedCornerShape(6.dp),
                border = BorderStroke(1.dp, Color(0xFFB84A52)),
            ) {
                Text(cloudError.orEmpty(), color = Color(0xFFFFD5D8), fontSize = 12.sp, modifier = Modifier.fillMaxWidth().padding(10.dp))
            }
        }

        if (cloudState.signedIn) {
            var licenseInput by rememberSaveable { mutableStateOf("") }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(cloudState.displayName.ifBlank { cloudState.email }, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Text(cloudState.email, color = VrelioMuted, fontSize = 12.sp)
                }
                Surface(
                    color = when {
                        cloudState.trialActive -> VrelioAmber.copy(alpha = 0.2f)
                        cloudState.isPro -> VrelioCoral.copy(alpha = 0.22f)
                        else -> Color(0xFF282D3A)
                    },
                    shape = RoundedCornerShape(99.dp),
                    border = BorderStroke(
                        1.dp,
                        when {
                            cloudState.trialActive -> VrelioAmber
                            cloudState.isPro -> VrelioCoral
                            else -> Color(0xFF4B5163)
                        },
                    ),
                ) {
                    Text(
                        text = when {
                            cloudState.trialActive -> "3 GÜNLÜK PRO DENEME"
                            cloudState.isPro -> "VRELIO PRO"
                            else -> "NORMAL PLAN"
                        },
                        color = Color.White,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    )
                }
            }
            if (cloudState.emailVerified) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Rounded.Verified, null, tint = Color(0xFF8DCDB2), modifier = Modifier.size(16.dp))
                    Text("E-posta doğrulandı · Max ${cloudState.maxDevices} cihaz", color = Color(0xFF8DCDB2), fontSize = 12.sp)
                }
            }

            if (cloudState.trialActive && cloudState.trialEndsAt.isNotBlank()) {
                TrialCountdownBanner(trialEndsAt = cloudState.trialEndsAt)
            }

            if (!cloudState.isPro) {
                PlanComparisonCard()
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = licenseInput,
                    onValueChange = { licenseInput = it.uppercase() },
                    label = { Text("Pro Lisans Anahtarı") },
                    placeholder = { Text("VRELIO-XXXX-XXXX-XXXX") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    enabled = !cloudBusy,
                )
                Button(
                    onClick = {
                        if (licenseInput.isNotBlank()) {
                            onCloudRedeem(licenseInput.trim())
                            licenseInput = ""
                        }
                    },
                    enabled = licenseInput.isNotBlank() && !cloudBusy,
                    modifier = Modifier.heightIn(min = 52.dp),
                ) { Text("Etkinleştir") }
            }

            OutlinedButton(
                onClick = onCloudSync,
                enabled = !cloudBusy,
                modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                shape = RoundedCornerShape(6.dp),
            ) {
                Icon(if (cloudState.isPro) Icons.Outlined.Refresh else Icons.Rounded.Lock, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(if (cloudState.isPro) "Hesap Verilerini Şimdi Eşitle (Bulut)" else "Bulut Eşitleme (Vrelio Pro)")
            }

            HorizontalDivider(color = Color.White.copy(alpha = 0.08f))
            Text(
                "Kayıtlı Cihazlar (${cloudState.devices.size} / ${cloudState.maxDevices})",
                fontWeight = FontWeight.SemiBold,
                fontSize = 13.sp,
            )
            if (cloudState.devices.isEmpty()) {
                Text("Bu hesapta henüz kayıtlı cihaz listelenmedi.", color = VrelioMuted, fontSize = 12.sp)
            } else {
                cloudState.devices.forEach { dev ->
                    Surface(
                        color = Color(0xFF1E222E),
                        shape = RoundedCornerShape(6.dp),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(dev.name, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                Text(dev.platform.uppercase(), color = VrelioMuted, fontSize = 11.sp)
                            }
                            TextButton(
                                onClick = { onCloudRemoveDevice(dev.id) },
                                enabled = !cloudBusy,
                                modifier = Modifier.heightIn(min = 48.dp).semantics {
                                    contentDescription = "${dev.name} cihazını kaldır"
                                },
                                colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                            ) {
                                Icon(Icons.Rounded.DeleteOutline, null, Modifier.size(17.dp))
                                Spacer(Modifier.width(4.dp))
                                Text("Kaldır", fontSize = 12.sp)
                            }
                        }
                    }
                }
            }

            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = onCloudRefresh, enabled = !cloudBusy, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text("Planı Yenile")
                }
                TextButton(onClick = onCloudLogout, enabled = !cloudBusy, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text("Hesaptan Çık", color = MaterialTheme.colorScheme.error)
                }
            }
        } else {
            var cloudUrl by rememberSaveable { mutableStateOf(cloudState.cloudUrl.ifBlank { DEFAULT_CLOUD_URL }) }
            var authTab by rememberSaveable { mutableStateOf("login") }
            var clName by rememberSaveable { mutableStateOf("") }
            var clEmail by rememberSaveable { mutableStateOf(cloudPendingEmail) }
            var clPass by remember { mutableStateOf("") }
            var verifyCode by rememberSaveable { mutableStateOf("") }
            var resetCode by rememberSaveable { mutableStateOf("") }
            var resetNewPass by remember { mutableStateOf("") }
            var revealCloudPass by remember { mutableStateOf(false) }

            LaunchedEffect(cloudPendingEmail) {
                if (cloudPendingEmail.isNotBlank() && clEmail.isBlank()) clEmail = cloudPendingEmail
            }

            OutlinedTextField(
                value = cloudUrl,
                onValueChange = { cloudUrl = it },
                label = { Text("Portal Sunucu Adresi") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
                enabled = !cloudBusy,
            )

            when (cloudAuthStep) {
                CloudAuthStep.IDLE -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(
                            selected = authTab == "login",
                            onClick = { authTab = "login" },
                            label = { Text("Giriş Yap") },
                        )
                        FilterChip(
                            selected = authTab == "register",
                            onClick = { authTab = "register" },
                            label = { Text("Kayıt Ol (3 Gün Pro Deneme)") },
                        )
                    }
                    if (authTab == "register") {
                        OutlinedTextField(
                            value = clName,
                            onValueChange = { clName = it },
                            label = { Text("Görünen Ad (İsteğe bağlı)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !cloudBusy,
                        )
                    }
                    OutlinedTextField(
                        value = clEmail,
                        onValueChange = { clEmail = it },
                        label = { Text("E-posta") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !cloudBusy,
                    )
                    OutlinedTextField(
                        value = clPass,
                        onValueChange = { clPass = it },
                        label = { Text(if (authTab == "register") "Parola (en az 8 karakter)" else "Parola") },
                        visualTransformation = if (revealCloudPass) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !cloudBusy,
                        trailingIcon = {
                            IconButton(onClick = { revealCloudPass = !revealCloudPass }, modifier = Modifier.size(48.dp)) {
                                Icon(
                                    if (revealCloudPass) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
                                    if (revealCloudPass) "Parolayı gizle" else "Parolayı göster",
                                )
                            }
                        },
                    )
                    Button(
                        onClick = {
                            if (authTab == "register") onCloudRegister(cloudUrl, clEmail, clPass, clName)
                            else onCloudLogin(cloudUrl, clEmail, clPass)
                        },
                        enabled = clEmail.isNotBlank() && (if (authTab == "register") clPass.length >= 8 else clPass.isNotBlank()) && !cloudBusy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) {
                        if (cloudBusy) {
                            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Color.White)
                            Spacer(Modifier.width(8.dp))
                        }
                        Text(if (authTab == "register") "Kayıt Ol ve Doğrulama Kodu Al" else "Giriş Yap")
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        TextButton(
                            onClick = { onSetAuthStep(CloudAuthStep.FORGOT_PASSWORD, clEmail) },
                            enabled = !cloudBusy,
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) { Text("Parolamı Unuttum") }
                        if (cloudPendingEmail.isNotBlank()) {
                            TextButton(
                                onClick = { onSetAuthStep(CloudAuthStep.VERIFY_EMAIL, cloudPendingEmail) },
                                enabled = !cloudBusy,
                                modifier = Modifier.heightIn(min = 48.dp),
                            ) { Text("Doğrulama Kodu Gir") }
                        }
                    }
                    PlanComparisonCard()
                }
                CloudAuthStep.VERIFY_EMAIL -> {
                    val targetEmail = cloudPendingEmail.ifBlank { clEmail }
                    Text(
                        "E-posta Doğrulama — 6 haneli kodu $targetEmail adresinden alıp girin.",
                        color = Color.White,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 13.sp,
                    )
                    OutlinedTextField(
                        value = verifyCode,
                        onValueChange = { verifyCode = it.filter(Char::isDigit).take(6) },
                        label = { Text("6 Haneli Doğrulama Kodu") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !cloudBusy,
                    )
                    Button(
                        onClick = { onCloudVerifyEmail(cloudUrl, targetEmail, verifyCode) },
                        enabled = targetEmail.isNotBlank() && verifyCode.length == 6 && !cloudBusy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) { Text("Doğrula ve 3 Günlük Pro Denemeyi Başlat") }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        TextButton(
                            onClick = { onCloudResendVerification(cloudUrl, targetEmail) },
                            enabled = targetEmail.isNotBlank() && !cloudBusy,
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) { Text("Kodu Tekrar Gönder") }
                        TextButton(
                            onClick = { onSetAuthStep(CloudAuthStep.IDLE, null) },
                            enabled = !cloudBusy,
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) { Text("Girişe Dön") }
                    }
                }
                CloudAuthStep.FORGOT_PASSWORD -> {
                    Text("Parola Sıfırlama Kodu İste", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    OutlinedTextField(
                        value = clEmail,
                        onValueChange = { clEmail = it },
                        label = { Text("Kayıtlı E-posta") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !cloudBusy,
                    )
                    Button(
                        onClick = { onCloudForgotPassword(cloudUrl, clEmail) },
                        enabled = clEmail.isNotBlank() && !cloudBusy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) { Text("Sıfırlama Kodu Gönder") }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        TextButton(
                            onClick = { onSetAuthStep(CloudAuthStep.RESET_PASSWORD, clEmail) },
                            enabled = !cloudBusy,
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) { Text("Kodum Var") }
                        TextButton(
                            onClick = { onSetAuthStep(CloudAuthStep.IDLE, null) },
                            enabled = !cloudBusy,
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) { Text("Girişe Dön") }
                    }
                }
                CloudAuthStep.RESET_PASSWORD -> {
                    val targetEmail = clEmail.ifBlank { cloudPendingEmail }
                    Text("Yeni Parola Belirle ($targetEmail)", fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = resetCode,
                            onValueChange = { resetCode = it.filter(Char::isDigit).take(6) },
                            label = { Text("6 Haneli Sıfırlama Kodu") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                            enabled = !cloudBusy,
                        )
                        OutlinedButton(
                            onClick = { onCloudVerifyResetCode(cloudUrl, targetEmail, resetCode) },
                            enabled = targetEmail.isNotBlank() && resetCode.length == 6 && !cloudBusy,
                            modifier = Modifier.heightIn(min = 52.dp),
                        ) { Text("Kodu Kontrol Et") }
                    }
                    OutlinedTextField(
                        value = resetNewPass,
                        onValueChange = { resetNewPass = it },
                        label = { Text("Yeni Parola (en az 8 karakter)") },
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !cloudBusy,
                    )
                    Button(
                        onClick = { onCloudResetPassword(cloudUrl, targetEmail, resetCode, resetNewPass) },
                        enabled = targetEmail.isNotBlank() && resetCode.length == 6 && resetNewPass.length >= 8 && !cloudBusy,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) { Text("Parolayı Güncelle") }
                    TextButton(
                        onClick = { onSetAuthStep(CloudAuthStep.IDLE, null) },
                        enabled = !cloudBusy,
                        modifier = Modifier.heightIn(min = 48.dp),
                    ) { Text("Girişe Dön") }
                }
            }
        }
    }
}

@Composable
private fun TrialCountdownBanner(trialEndsAt: String) {
    var remainingText by remember(trialEndsAt) { mutableStateOf(formatRemainingTrial(trialEndsAt)) }
    LaunchedEffect(trialEndsAt) {
        while (true) {
            remainingText = formatRemainingTrial(trialEndsAt)
            delay(30_000)
        }
    }
    Surface(
        color = VrelioAmber.copy(alpha = 0.14f),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, VrelioAmber.copy(alpha = 0.55f)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(Icons.Rounded.AutoAwesome, null, tint = VrelioAmber, modifier = Modifier.size(20.dp))
            Column(Modifier.weight(1f)) {
                Text("3 Günlük Pro Denemeniz Aktif", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = Color.White)
                Text(remainingText, fontSize = 12.sp, color = Color(0xFFFFD8A8))
            }
        }
    }
}

private fun formatRemainingTrial(iso: String): String = runCatching {
    val end = Instant.parse(iso)
    val diff = Duration.between(Instant.now(), end)
    if (diff.isNegative || diff.isZero) "Deneme süresi sona erdi"
    else {
        val days = diff.toDays()
        val hours = diff.minusDays(days).toHours()
        val mins = diff.minusDays(days).minusHours(hours).toMinutes()
        "${days} gün ${hours} saat ${mins} dk kaldı"
    }
}.getOrDefault("Pro deneme aktif")

@Composable
private fun PlanComparisonCard() {
    Surface(
        color = Color(0xFF1D212D),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, Color.White.copy(alpha = 0.08f)),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Normal vs Vrelio Pro", fontWeight = FontWeight.Bold, fontSize = 12.sp, color = Color.White)
            Text("• Normal (Ücretsiz): 1 cihaz · Yerel oynatma · 1 profil", fontSize = 11.sp, color = VrelioMuted)
            Text("• Vrelio Pro (3 Gün Deneme Dahil): 5 cihaz · Bulut eşitleme · Sınırsız profil & PIN · Gelişmiş EPG & ses/altyazı", fontSize = 11.sp, color = Color(0xFFE6E8F0))
        }
    }
}

@Composable
private fun SettingsCard(title: String, subtitle: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(color = VrelioPanel, shape = RoundedCornerShape(8.dp)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(subtitle, color = VrelioMuted, style = MaterialTheme.typography.bodySmall)
            content()
        }
    }
}

@Composable
fun VrelioCollectionPicker(
    collections: List<UiCollection>,
    onSelect: (UiCollection) -> Unit,
    onCreate: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text("Listeye ekle") }, text = {
            Column(Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState())) {
                collections.forEach { collection ->
                    TextButton(onClick = { onSelect(collection) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                        Icon(Icons.Outlined.Folder, null, Modifier.size(20.dp))
                        Text(collection.title, Modifier.weight(1f).padding(start = 10.dp))
                        Text("${collection.count}", color = VrelioMuted)
                    }
                }
                if (collections.isNotEmpty()) HorizontalDivider(Modifier.padding(vertical = 12.dp))
                OutlinedTextField(
                    value = name, onValueChange = { name = it.take(100) }, label = { Text("Yeni liste adı") },
                    placeholder = { Text("Örneğin: Hafta sonu", fontSize = 12.sp) }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { TextButton(onClick = { onCreate(name.trim()) }, enabled = name.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp)) { Text("Liste oluştur") } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Kapat") } },
    )
}
