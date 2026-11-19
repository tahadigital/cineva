package app.vrelio.player.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import app.vrelio.player.data.UserProfile

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
    val colorOptions = remember {
        listOf(
            "#FF4B45" to "Mercan Kırmızısı",
            "#FF9933" to "Amber Turuncusu",
            "#34C759" to "Zümrüt Yeşili",
            "#5E5CE6" to "Mor İndigo",
            "#0A84FF" to "Gökyüzü Mavisi",
        )
    }
    var selectedColor by remember { mutableStateOf(colorOptions.first().first) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF171A22),
        titleContentColor = Color.White,
        title = { Text("Profiller", fontWeight = FontWeight.Bold) },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Her profilin favorileri, izleme geçmişi ve listeleri ayrı tutulur.", color = VrelioMuted, fontSize = 12.sp)
                profiles.forEach { profile ->
                    val badgeColor = runCatching { Color(android.graphics.Color.parseColor(profile.avatarColor)) }.getOrDefault(VrelioCoral)
                    Row(
                        Modifier.fillMaxWidth()
                            .heightIn(min = 56.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(Color(0xFF212633))
                            .border(1.5.dp, if (profile.active) VrelioCoral else Color.Transparent, RoundedCornerShape(10.dp))
                            .clickable(
                                role = Role.Button,
                                onClickLabel = "${profile.name} profiline geç",
                            ) {
                                if (profile.hasPin && !profile.active) { pinTarget = profile; pinInput = "" }
                                else onSwitch(profile.id, "")
                            }
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
                            if (tags.isNotBlank()) Text(tags, color = VrelioMuted, fontSize = 11.sp)
                        }
                        if (profile.hasPin) Icon(Icons.Outlined.Lock, "PIN Korumalı", tint = VrelioMuted, modifier = Modifier.size(16.dp))
                        if (profile.id != "default") {
                            IconButton(
                                onClick = { onDelete(profile.id) },
                                modifier = Modifier.size(48.dp),
                            ) {
                                Icon(Icons.Outlined.Delete, "${profile.name} profilini sil", tint = VrelioMuted, modifier = Modifier.size(20.dp))
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
                        Button(
                            onClick = { onSwitch(target.id, pinInput) },
                            modifier = Modifier.heightIn(min = 48.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = VrelioCoral),
                        ) {
                            Text("Aç")
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
                        .clip(RoundedCornerShape(8.dp))
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
                        val c = runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(VrelioCoral)
                        val selected = selectedColor == hex
                        Box(
                            modifier = Modifier
                                .size(48.dp)
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
                Button(
                    onClick = {
                        if (newName.isNotBlank()) {
                            onCreate(newName.trim(), selectedColor, newIsKids, newPin)
                            newName = ""
                            newPin = ""
                        }
                    },
                    enabled = newName.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = VrelioCoral, contentColor = Color.White),
                ) { Text("Profil Oluştur") }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) {
                Text("Kapat", color = Color.White)
            }
        },
    )
}
