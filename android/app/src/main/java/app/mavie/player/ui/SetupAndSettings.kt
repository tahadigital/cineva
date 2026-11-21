package app.mavie.player.ui

import android.net.Uri
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

@Composable
fun MavieSetupScreen(
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

    Box(Modifier.fillMaxSize().background(MavieBackground)) {
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
            Surface(shape = RoundedCornerShape(8.dp), color = MaviePanel, modifier = Modifier.widthIn(max = 520.dp)) {
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
) {
    val context = LocalContext.current
    var confirmLogout by remember { mutableStateOf(false) }
    var showLicenses by remember { mutableStateOf(false) }
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
                SettingsCard("Yasal Bilgiler & Lisanslar", "Tamamen ücretsiz, hesapsız ve yerel öncelikli oynatıcı.") {
                    Text(
                        "Mavie tamamen ücretsizdir ve hesap gerektirmez. Telifli içerik sağlamaz, barındırmaz veya dağıtmaz; yalnızca kullanıcının eklediği açık veya yasal kaynakları oynatır.",
                        color = MavieMuted, style = MaterialTheme.typography.bodySmall,
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
                    MavieWordmark()
                    Text("Sürüm $versionName · Android · Ücretsiz", Modifier.padding(top = 7.dp), color = MavieMuted, fontSize = 11.sp)
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
private fun SettingsCard(title: String, subtitle: String, content: @Composable ColumnScope.() -> Unit) {
    Surface(color = MaviePanel, shape = RoundedCornerShape(8.dp)) {
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
        onDismissRequest = onDismiss, title = { Text("Listeye ekle") }, text = {
            Column(Modifier.heightIn(max = 400.dp).verticalScroll(rememberScrollState())) {
                collections.forEach { collection ->
                    TextButton(onClick = { onSelect(collection) }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
                        Icon(Icons.Outlined.Folder, null, Modifier.size(20.dp))
                        Text(collection.title, Modifier.weight(1f).padding(start = 10.dp))
                        Text("${collection.count}", color = MavieMuted)
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
