package app.mavie.player.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.mavie.player.data.UserProfile

@Composable
fun ProfilePickerDialog(
    profiles: List<UserProfile>,
    error: String?,
    onSwitch: (id: String, pin: String) -> Unit,
    onCreate: (name: String, color: String, isKids: Boolean, pin: String) -> Unit,
    onDelete: (id: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var pinTarget by remember { mutableStateOf<UserProfile?>(null) }
    var pinInput by remember { mutableStateOf("") }
    var newName by remember { mutableStateOf("") }
    var newPin by remember { mutableStateOf("") }
    var newIsKids by remember { mutableStateOf(false) }
    var awaitingCreate by remember { mutableStateOf(false) }
    var previousCount by remember { mutableIntStateOf(profiles.size) }
    LaunchedEffect(profiles.size, error) {
        if (awaitingCreate) {
            if (error != null) {
                awaitingCreate = false
            } else if (profiles.size > previousCount) {
                awaitingCreate = false
                newName = ""
                newPin = ""
                newIsKids = false
            }
        }
        previousCount = profiles.size
    }
    val colorOptions = remember {
        listOf(
            "#7C3AED" to "Mavie Moru",
            "#06B6D4" to "Okyanus Turkuazı",
            "#34C759" to "Zümrüt Yeşili",
            "#5E5CE6" to "Mor İndigo",
            "#0A84FF" to "Gökyüzü Mavisi",
        )
    }
    var selectedColor by remember { mutableStateOf(colorOptions.first().first) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = MavieGlassDialogFill,
        shape = RoundedCornerShape(24.dp),
        titleContentColor = Color.White,
        title = { Text("Profiller", fontWeight = FontWeight.Bold) },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Her profilin favorileri, izleme geçmişi ve listeleri ayrı tutulur.", color = MavieMuted, fontSize = 12.sp)
                profiles.forEach { profile ->
                    val badgeColor = runCatching { Color(android.graphics.Color.parseColor(profile.avatarColor)) }.getOrDefault(MaviePurple)
                    var rowFocused by remember { mutableStateOf(false) }
                    val tileShape = RoundedCornerShape(16.dp)
                    Card(
                        onClick = {
                            if (profile.hasPin && !profile.active) { pinTarget = profile; pinInput = "" }
                            else onSwitch(profile.id, "")
                        },
                        shape = tileShape,
                        border = BorderStroke(
                            width = if (profile.active || rowFocused) 2.5.dp else 1.dp,
                            brush = if (profile.active || rowFocused) MavieTvFocusBrush else MavieSpecularBorderBrush,
                        ),
                        colors = CardDefaults.cardColors(
                            containerColor = if (rowFocused) Color(0xD91A223B) else Color(0xB8141B2E),
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .mavieTvFocusable(
                                shape = tileShape,
                                showFocusBorder = false,
                                addFocusable = false,
                                onFocusChange = { rowFocused = it },
                            ),
                    ) {
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .heightIn(min = 56.dp)
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Box(Modifier.size(36.dp).clip(CircleShape).background(badgeColor), contentAlignment = Alignment.Center) {
                                Text(profile.name.take(1).uppercase(), color = Color.White, fontWeight = FontWeight.Bold)
                            }
                            Column(Modifier.weight(1f)) {
                                Text(profile.name, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                                val tags = listOfNotNull(if (profile.isKids) "Çocuk Modu" else null, if (profile.active) "Aktif" else null).joinToString(" · ")
                                if (tags.isNotBlank()) Text(tags, color = MavieMuted, fontSize = 11.sp)
                            }
                            if (profile.hasPin) Icon(Icons.Outlined.Lock, "PIN Korumalı", tint = MavieMuted, modifier = Modifier.size(16.dp))
                            if (profile.id != "default") {
                                IconButton(
                                    onClick = { onDelete(profile.id) },
                                    modifier = Modifier
                                        .size(48.dp)
                                        .mavieTvFocusable(shape = CircleShape, addFocusable = false),
                                ) {
                                    Icon(Icons.Outlined.Delete, "${profile.name} profilini sil", tint = MavieMuted, modifier = Modifier.size(20.dp))
                                }
                            }
                        }
                    }
                }
                pinTarget?.let { target ->
                    HorizontalDivider(color = Color.White.copy(alpha = .12f))
                    Text("${target.name} için PIN gir", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = pinInput,
                            onValueChange = { pinInput = it.filter(Char::isDigit).take(8) },
                            label = { Text("PIN") },
                            visualTransformation = PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        MavieGradientButton(
                            onClick = { onSwitch(target.id, pinInput) },
                            modifier = Modifier.heightIn(min = 48.dp),
                            shape = RoundedCornerShape(14.dp),
                        ) {
                            Text("Aç", color = Color.White)
                        }
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp) }
                HorizontalDivider(color = Color.White.copy(alpha = .12f))
                Text("Yeni Profil Ekle", color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                OutlinedTextField(value = newName, onValueChange = { newName = it }, label = { Text("Profil adı") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(
                    value = newPin,
                    onValueChange = { newPin = it.filter(Char::isDigit).take(8) },
                    label = { Text("PIN (isteğe bağlı, 4-8 rakam)") },
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .mavieTvFocusable(shape = RoundedCornerShape(10.dp), addFocusable = false)
                        .clip(RoundedCornerShape(10.dp))
                        .toggleable(
                            value = newIsKids,
                            role = Role.Checkbox,
                            onValueChange = { newIsKids = it },
                        )
                        .padding(horizontal = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Checkbox(checked = newIsKids, onCheckedChange = null)
                    Text("Çocuk Profili (+18/korku gizlenir)", color = Color.White, fontSize = 12.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    colorOptions.forEach { (hex, colorName) ->
                        val c = runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(MavieCoral)
                        val selected = selectedColor == hex
                        Box(
                            modifier = Modifier
                                .size(48.dp)
                                .mavieTvFocusable(shape = CircleShape, addFocusable = false)
                                .clip(CircleShape)
                                .selectable(
                                    selected = selected,
                                    role = Role.RadioButton,
                                    onClick = { selectedColor = hex },
                                )
                                .semantics { contentDescription = "Profil rengi: $colorName" },
                            contentAlignment = Alignment.Center,
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(30.dp)
                                    .clip(CircleShape)
                                    .background(c)
                                    .border(2.dp, if (selected) Color.White else Color.Transparent, CircleShape),
                                contentAlignment = Alignment.Center,
                            ) {
                                if (selected) {
                                    Icon(
                                        imageVector = Icons.Rounded.Check,
                                        contentDescription = null,
                                        tint = Color.White,
                                        modifier = Modifier.size(16.dp),
                                    )
                                }
                            }
                        }
                    }
                }
                MavieGradientButton(
                    onClick = {
                        if (newName.isNotBlank()) {
                            awaitingCreate = true
                            previousCount = profiles.size
                            onCreate(newName.trim(), selectedColor, newIsKids, newPin)
                        }
                    },
                    enabled = newName.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    shape = RoundedCornerShape(14.dp),
                ) { Text("Profil Oluştur", color = Color.White) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.heightIn(min = 48.dp).mavieTvFocusable(shape = RoundedCornerShape(12.dp), addFocusable = false),
            ) {
                Text("Kapat", color = Color.White)
            }
        },
    )
}
