package app.mavie.player.ui

import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.mavie.player.data.MavieErrorCode
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.util.Locale

internal sealed interface ParsedSetupInput {
    data class UseM3u(val m3uUrl: String) : ParsedSetupInput
    data class UseXtream(val host: String, val username: String, val password: String) : ParsedSetupInput
    data object KeepXtream : ParsedSetupInput
}

internal fun normalizeSetupUrl(rawInput: String): String {
    val trimmed = rawInput.trim()
    val raw = if ('?' in trimmed) trimmed else trimmed.trimEnd('/')
    return if (raw.isNotBlank() && !raw.contains("://")) "http://$raw" else raw
}

internal fun detectXtreamOrM3uInput(
    rawHost: String,
    currentUser: String = "",
    currentPass: String = "",
): ParsedSetupInput {
    val trimmed = rawHost.trim()
    if (trimmed.isBlank()) return ParsedSetupInput.KeepXtream
    val normalized = normalizeSetupUrl(trimmed)
    val parsed = normalized.toHttpUrlOrNull() ?: return ParsedSetupInput.KeepXtream
    val pathLower = parsed.encodedPath.lowercase(Locale.ROOT)
    val typeParam = parsed.queryParameter("type").orEmpty().lowercase(Locale.ROOT)
    if (pathLower.endsWith(".m3u") ||
        pathLower.endsWith(".m3u8") ||
        pathLower.endsWith("/get.php") ||
        pathLower == "/get.php" ||
        typeParam.startsWith("m3u")
    ) {
        return ParsedSetupInput.UseM3u(normalized)
    }
    if (pathLower.endsWith("/player_api.php") || pathLower == "/player_api.php") {
        val prefix = parsed.encodedPath.substringBeforeLast("/player_api.php").trimEnd('/')
        val baseHost = parsed.newBuilder()
            .encodedPath(if (prefix.isEmpty()) "/" else "$prefix/")
            .query(null)
            .fragment(null)
            .build()
            .toString()
            .trimEnd('/')
        val user = parsed.queryParameter("username")?.takeIf { it.isNotBlank() } ?: currentUser.trim()
        val pass = parsed.queryParameter("password")?.takeIf { it.isNotBlank() } ?: currentPass
        return ParsedSetupInput.UseXtream(baseHost, user, pass)
    }
    return ParsedSetupInput.KeepXtream
}

@Composable
fun MavieSetupScreen(
    loading: Boolean,
    error: String?,
    onSubmit: (String, String, String, String) -> Unit,
    onM3uSubmit: (String, String, String) -> Unit = { _, _, _ -> },
    onDemo: () -> Unit = {},
    onOpenLocalFile: () -> Unit = {},
    errorCode: MavieErrorCode? = null,
) {
    var mode by rememberSaveable { mutableStateOf("m3u") }
    var name by rememberSaveable { mutableStateOf("Kişisel Liste") }
    // Credential-bearing URLs stay out of Android's instance-state bundle.
    var m3uUrl by remember { mutableStateOf("") }
    var host by rememberSaveable { mutableStateOf("") }
    var username by rememberSaveable { mutableStateOf("") }
    // Password is deliberately not saveable in Android's instance-state bundle.
    var password by remember { mutableStateOf("") }
    var epgUrl by remember { mutableStateOf("") }
    var reveal by remember { mutableStateOf(false) }
    var localError by remember { mutableStateOf<String?>(null) }
    val keyboard = LocalSoftwareKeyboardController.current

    fun normalize(rawInput: String): String = normalizeSetupUrl(rawInput)

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
        when (val detected = detectXtreamOrM3uInput(host, username, password)) {
            is ParsedSetupInput.UseM3u -> {
                keyboard?.hide()
                onM3uSubmit(name.trim().ifBlank { "M3U Listesi" }, detected.m3uUrl, normalizedEpg)
                return
            }
            is ParsedSetupInput.UseXtream -> {
                host = detected.host
                if (detected.username.isNotBlank()) username = detected.username
                if (detected.password.isNotBlank()) password = detected.password
            }
            ParsedSetupInput.KeepXtream -> Unit
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

    val glassFieldColors = OutlinedTextFieldDefaults.colors(
        focusedBorderColor = MavieTurquoise,
        unfocusedBorderColor = Color.White.copy(alpha = 0.16f),
        unfocusedContainerColor = Color(0x660E1322),
        focusedContainerColor = Color(0x99131A2E),
    )

    Box(Modifier.fillMaxSize().background(MavieBackground)) {
        MavieAmbientBackdrop()
        Column(
            Modifier.fillMaxSize().systemBarsPadding().imePadding().verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.height(16.dp))
            MavieWordmark(large = true)
            Spacer(Modifier.height(22.dp))
            Text("Kendi ekranına hoş geldin.", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(
                "Filmler, diziler ve canlı yayınlar.\nKendi kaynağınla bağlan ya da açık sinema demosuyla hemen izle.",
                Modifier.padding(top = 10.dp), color = MavieMuted, style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(18.dp))
            MavieGlassPillButton(
                onClick = { if (!loading) onDemo() },
                enabled = !loading,
                modifier = Modifier.fillMaxWidth().widthIn(max = 520.dp).heightIn(min = 48.dp),
                shape = RoundedCornerShape(16.dp),
            ) {
                Icon(Icons.Filled.PlayArrow, null, Modifier.size(20.dp), tint = MavieCyanDot)
                Spacer(Modifier.width(8.dp))
                Text("Açık Sinema ile Hemen Dene (Demo)", color = Color.White)
            }
            Spacer(Modifier.height(10.dp))
            TextButton(
                onClick = { if (!loading) onOpenLocalFile() },
                enabled = !loading,
                modifier = Modifier.fillMaxWidth().widthIn(max = 520.dp).heightIn(min = 48.dp),
            ) {
                Icon(Icons.Outlined.FolderOpen, null, Modifier.size(18.dp), tint = MavieMuted)
                Spacer(Modifier.width(8.dp))
                Text("Cihazdan Yerel Video Aç (.mp4, .mkv, .avi)", color = Color.White)
            }
            Spacer(Modifier.height(14.dp))
            Box(Modifier.widthIn(max = 520.dp).mavieGlassSurface(RoundedCornerShape(24.dp))) {
                Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Text("Medya kaynağı bağla", style = MaterialTheme.typography.titleMedium)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        val chipColors = FilterChipDefaults.filterChipColors(
                            containerColor = Color(0x80182038),
                            labelColor = MavieMuted,
                            selectedContainerColor = MaviePurple.copy(alpha = 0.88f),
                            selectedLabelColor = Color.White,
                        )
                        FilterChip(
                            selected = mode == "m3u",
                            onClick = { mode = "m3u"; localError = null },
                            label = { Text("M3U / Liste") },
                            shape = CircleShape,
                            colors = chipColors,
                            border = FilterChipDefaults.filterChipBorder(
                                enabled = true,
                                selected = mode == "m3u",
                                borderColor = Color.White.copy(alpha = 0.14f),
                                selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                            ),
                        )
                        FilterChip(
                            selected = mode == "xtream",
                            onClick = { mode = "xtream"; localError = null },
                            label = { Text("Xtream Sunucu") },
                            shape = CircleShape,
                            colors = chipColors,
                            border = FilterChipDefaults.filterChipBorder(
                                enabled = true,
                                selected = mode == "xtream",
                                borderColor = Color.White.copy(alpha = 0.14f),
                                selectedBorderColor = MavieCyanDot.copy(alpha = 0.7f),
                            ),
                        )
                    }
                    if (mode == "m3u") {
                        OutlinedTextField(
                            value = name, onValueChange = { name = it; localError = null }, label = { Text("Liste adı") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = m3uUrl, onValueChange = { m3uUrl = it; localError = null }, label = { Text("M3U / M3U8 adresi") },
                            placeholder = { Text("https://example.com/playlist.m3u8", fontSize = 13.sp) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                        )
                    } else {
                        OutlinedTextField(
                            value = host,
                            onValueChange = { raw ->
                                localError = null
                                when (val detected = detectXtreamOrM3uInput(raw, username, password)) {
                                    is ParsedSetupInput.UseM3u -> {
                                        m3uUrl = detected.m3uUrl
                                        mode = "m3u"
                                    }
                                    is ParsedSetupInput.UseXtream -> {
                                        host = detected.host
                                        if (detected.username.isNotBlank()) username = detected.username
                                        if (detected.password.isNotBlank()) password = detected.password
                                    }
                                    ParsedSetupInput.KeepXtream -> host = raw
                                }
                            },
                            label = { Text("Sunucu adresi") },
                            placeholder = { Text("http://sunucun:8080", fontSize = 13.sp) }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = username, onValueChange = { username = it; localError = null }, label = { Text("Kullanıcı adı") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text, autoCorrectEnabled = false, imeAction = ImeAction.Next),
                        )
                        OutlinedTextField(
                            value = password, onValueChange = { password = it; localError = null }, label = { Text("Parola") },
                            singleLine = true, modifier = Modifier.fillMaxWidth(), enabled = !loading,
                            shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
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
                        shape = RoundedCornerShape(14.dp), colors = glassFieldColors,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done),
                        keyboardActions = KeyboardActions(onDone = { submit() }),
                    )
                    val message = localError ?: error
                    val activeCode = if (localError != null) null else errorCode
                    if (message != null) {
                        val hint = errorHintFor(activeCode)
                        val activeSourceInput = if (mode == "m3u") m3uUrl.trim() else host.trim()
                        val showHttpRetry = activeCode == MavieErrorCode.TLS_FAILED &&
                            activeSourceInput.startsWith("https://", ignoreCase = true)
                        val showDemoRecovery = activeCode in setOf(MavieErrorCode.OFFLINE, MavieErrorCode.KEYSTORE_ERROR)
                        Column(
                            modifier = Modifier.fillMaxWidth()
                                .mavieGlassSurface(RoundedCornerShape(14.dp), topColor = Color(0x552E1525), bottomColor = Color(0x441B1020))
                                .padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                        ) {
                            Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                            if (!hint.isNullOrBlank()) {
                                Text(hint, color = MavieMuted, style = MaterialTheme.typography.bodySmall)
                            }
                            if (showHttpRetry || showDemoRecovery) {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    if (showHttpRetry) {
                                        MavieGlassPillButton(
                                            onClick = {
                                                if (mode == "m3u") {
                                                    m3uUrl = "http://" + m3uUrl.trim().substring(8)
                                                } else {
                                                    host = "http://" + host.trim().substring(8)
                                                }
                                                localError = null
                                                submit()
                                            },
                                            modifier = Modifier.heightIn(min = 48.dp),
                                            shape = RoundedCornerShape(12.dp),
                                        ) {
                                            Text("HTTP ile Dene", color = Color.White, fontSize = 12.sp)
                                        }
                                    }
                                    if (showDemoRecovery) {
                                        OutlinedButton(
                                            onClick = { if (!loading) onDemo() },
                                            enabled = !loading,
                                            modifier = Modifier.heightIn(min = 48.dp),
                                            shape = RoundedCornerShape(12.dp),
                                            border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                                            colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
                                        ) {
                                            Text("Açık Sinema Demosu", fontSize = 12.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    MavieGradientButton(
                        onClick = { submit() },
                        enabled = !loading,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        if (loading) {
                            CircularProgressIndicator(Modifier.size(19.dp), strokeWidth = 2.dp, color = Color.White)
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(if (loading) "Kütüphanen hazırlanıyor…" else "Bağlan", color = Color.White)
                    }
                }
            }
            Spacer(Modifier.height(18.dp))
            Row(Modifier.fillMaxWidth().widthIn(max = 520.dp), verticalAlignment = Alignment.Top) {
                Icon(Icons.Outlined.Lock, null, Modifier.padding(top = 2.dp).size(15.dp), tint = MavieMuted)
                Text(
                    "Mavie telifli yayın barındırmaz; yalnızca kendi eklediğin yasal kaynakları veya açık sinema demosunu oynatır.",
                    Modifier.padding(start = 9.dp), color = MavieMuted, fontSize = 11.sp, lineHeight = 17.sp,
                )
            }
        }
    }
}

@Composable
fun MavieSettingsScreen(
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
    versionName: String = "2.2.0",
    errorCode: MavieErrorCode? = null,
    epgUrl: String = "",
    onSaveEpgUrl: (String) -> Unit = {},
) {
    val context = LocalContext.current
    var confirmLogout by remember { mutableStateOf(false) }
    var showLicenses by remember { mutableStateOf(false) }
    var showEpgDialog by remember { mutableStateOf(false) }
    val noticeText = remember {
        runCatching { context.assets.open("NOTICE.txt").bufferedReader().use { it.readText() } }
            .getOrDefault("Mavie · Apache 2.0 / LibVLC (LGPL-2.1+)")
    }
    Scaffold(containerColor = MavieBackground) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())) {
            Row(Modifier.fillMaxWidth().padding(start = 8.dp, end = 20.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                MavieTooltipIconButton(
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
                    if (catalogSummary.isNotBlank()) Text(catalogSummary, style = MaterialTheme.typography.bodySmall, color = MavieMuted)
                    MavieGradientButton(
                        onClick = onRefresh,
                        enabled = !refreshing,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                    ) {
                        if (refreshing) CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp, color = Color.White)
                        else Icon(Icons.Outlined.Refresh, null, Modifier.size(19.dp), tint = Color.White)
                        Spacer(Modifier.width(8.dp)); Text(if (refreshing) "Yenileniyor…" else "Kütüphaneyi yenile", color = Color.White)
                    }
                    Text(
                        if (epgUrl.isNotBlank()) "XMLTV EPG: Bağlı" else "XMLTV EPG: Eklenmedi",
                        style = MaterialTheme.typography.bodySmall,
                        color = MavieMuted,
                    )
                    OutlinedButton(
                        onClick = { showEpgDialog = true },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
                    ) {
                        Icon(Icons.Outlined.Tv, null, Modifier.size(19.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("XMLTV EPG Düzenle")
                    }
                    if (error != null) {
                        val hint = errorHintFor(errorCode)
                        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                            if (!hint.isNullOrBlank()) {
                                Text(hint, color = MavieMuted, style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
                SettingsCard("Kütüphanen seninle", "Favorilerini, listelerini ve izleme kayıtlarını taşı.") {
                    OutlinedButton(
                        onClick = onExport,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
                    ) {
                        Icon(Icons.Outlined.FileDownload, null, Modifier.size(19.dp)); Spacer(Modifier.width(8.dp)); Text("Yedek dışa aktar")
                    }
                    OutlinedButton(
                        onClick = onImport,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
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
                SettingsCard("Yasal Bilgiler & Lisanslar", "Tamamen ücretsiz, hesapsız ve yerel öncelikli oynatıcı.") {
                    Text(
                        "Mavie tamamen ücretsizdir ve hesap gerektirmez. Telifli içerik sağlamaz, barındırmaz veya dağıtmaz; yalnızca kullanıcının eklediği açık veya yasal kaynakları oynatır.",
                        color = MavieMuted, style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedButton(
                        onClick = { showLicenses = true },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        shape = RoundedCornerShape(16.dp),
                        border = BorderStroke(1.dp, MavieSpecularBorderBrush),
                        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0x73182038), contentColor = Color.White),
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
                    MavieWordmark()
                    Text("Sürüm $versionName · Android · Ücretsiz", Modifier.padding(top = 7.dp), color = MavieMuted, fontSize = 11.sp)
                }
            }
        }
    }
    if (showLicenses) AlertDialog(
        onDismissRequest = { showLicenses = false },
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        title = { Text("Yasal Bilgiler & Lisanslar") },
        text = { Text(noticeText, modifier = Modifier.heightIn(max = 360.dp).verticalScroll(rememberScrollState()), fontSize = 12.sp, lineHeight = 18.sp) },
        confirmButton = { TextButton(onClick = { showLicenses = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Kapat") } },
    )
    if (showEpgDialog) {
        var epgInput by remember(epgUrl) { mutableStateOf(epgUrl) }
        var epgLocalError by remember { mutableStateOf<String?>(null) }
        AlertDialog(
            onDismissRequest = { showEpgDialog = false },
            containerColor = MavieGlassDialogFill,
            shape = RoundedCornerShape(24.dp),
            title = { Text("XMLTV EPG Adresi") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        "Spor ve canlı yayın rehberi için isteğe bağlı XMLTV EPG bağlantısı ekleyebilir veya silebilirsin.",
                        color = MavieMuted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedTextField(
                        value = epgInput,
                        onValueChange = { epgInput = it; epgLocalError = null },
                        label = { Text("XMLTV EPG adresi") },
                        placeholder = { Text("https://example.com/guide.xml", fontSize = 13.sp) },
                        singleLine = true,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    if (epgLocalError != null) {
                        Text(epgLocalError!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                    }
                    if (epgInput.isNotBlank()) {
                        TextButton(
                            onClick = {
                                showEpgDialog = false
                                onSaveEpgUrl("")
                            },
                            modifier = Modifier.heightIn(min = 48.dp),
                        ) {
                            Text("Temizle", color = MaterialTheme.colorScheme.error)
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        val trimmed = epgInput.trim()
                        if (trimmed.isEmpty()) {
                            showEpgDialog = false
                            onSaveEpgUrl("")
                        } else {
                            val normalized = normalizeSetupUrl(trimmed)
                            val uri = runCatching { Uri.parse(normalized) }.getOrNull()
                            if (uri?.scheme !in listOf("http", "https") || uri?.host.isNullOrBlank()) {
                                epgLocalError = "EPG adresi http:// veya https:// ile başlamalı."
                            } else {
                                showEpgDialog = false
                                onSaveEpgUrl(normalized)
                            }
                        }
                    },
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text("Kaydet") }
            },
            dismissButton = {
                TextButton(onClick = { showEpgDialog = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Vazgeç") }
            },
        )
    }
    if (confirmLogout) AlertDialog(
        onDismissRequest = { confirmLogout = false },
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        title = { Text("Kaynaktan çıkılsın mı?") },
        text = { Text("Bu cihazda yeniden izlemek için kaynak bilgilerini tekrar girmen veya demo modunu seçmen gerekir.") },
        confirmButton = { TextButton(onClick = { confirmLogout = false; onLogout() }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Çıkış yap") } },
        dismissButton = { TextButton(onClick = { confirmLogout = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Vazgeç") } },
    )
}

@Composable
private fun SettingsCard(title: String, subtitle: String, content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxWidth().mavieGlassSurface(RoundedCornerShape(20.dp))) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(subtitle, color = MavieMuted, style = MaterialTheme.typography.bodySmall)
            content()
        }
    }
}

@Composable
fun MavieCollectionPicker(
    collections: List<UiCollection>,
    onSelect: (UiCollection) -> Unit,
    onCreate: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    var name by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        title = { Text("Listeye ekle") },
        text = {
            Column(Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState())) {
                collections.forEach { collection ->
                    TextButton(
                        onClick = { onSelect(collection) },
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    ) {
                        Icon(Icons.Outlined.Folder, null, Modifier.size(20.dp), tint = MavieTurquoise)
                        Text(collection.title, Modifier.weight(1f).padding(start = 10.dp), color = Color.White)
                        Text("${collection.count}", color = MavieMuted)
                    }
                }
                if (collections.isNotEmpty()) HorizontalDivider(Modifier.padding(vertical = 12.dp), color = Color.White.copy(alpha = 0.12f))
                OutlinedTextField(
                    value = name, onValueChange = { name = it.take(100) }, label = { Text("Yeni liste adı") },
                    placeholder = { Text("Örneğin: Hafta sonu", fontSize = 12.sp) }, singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = { TextButton(onClick = { onCreate(name.trim()) }, enabled = name.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp)) { Text("Liste oluştur") } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Kapat") } },
    )
}
