package app.cineva.player.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.cineva.player.data.UserProfile

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
    val colors = remember { listOf("#FF4B45", "#FF9933", "#34C759", "#5E5CE6", "#0A84FF") }
    var selectedColor by remember { mutableStateOf(colors.first()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF171A22),
        titleContentColor = Color.White,
        title = { Text("Profiller", fontWeight = FontWeight.Bold) },
        text = {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Her profilin favorileri, izleme geçmişi ve listeleri ayrı tutulur.", color = AkisMuted, fontSize = 12.sp)
                profiles.forEach { profile ->
                    val badgeColor = runCatching { Color(android.graphics.Color.parseColor(profile.avatarColor)) }.getOrDefault(AkisRed)
                    Row(
                        Modifier.fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(Color(0xFF212633))
                            .border(1.5.dp, if (profile.active) AkisRed else Color.Transparent, RoundedCornerShape(10.dp))
                            .clickable {
                                if (profile.hasPin && !profile.active) { pinTarget = profile; pinInput = "" }
                                else onSwitch(profile.id, "")
                            }
                            .padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Box(Modifier.size(36.dp).clip(CircleShape).background(badgeColor), contentAlignment = Alignment.Center) {
                            Text(profile.name.take(1).uppercase(), color = Color.White, fontWeight = FontWeight.Bold)
                        }
                        Column(Modifier.weight(1f)) {
                            Text(profile.name, color = Color.White, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                            val tags = listOfNotNull(if (profile.isKids) "Çocuk Modu" else null, if (profile.active) "Aktif" else null).joinToString(" · ")
                            if (tags.isNotBlank()) Text(tags, color = AkisMuted, fontSize = 11.sp)
                        }
                        if (profile.hasPin) Icon(Icons.Outlined.Lock, "PIN Korumalı", tint = AkisMuted, modifier = Modifier.size(16.dp))
                        if (profile.id != "default") {
                            IconButton(onClick = { onDelete(profile.id) }, modifier = Modifier.size(32.dp)) {
                                Icon(Icons.Outlined.Delete, "Profili sil", tint = AkisMuted, modifier = Modifier.size(18.dp))
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
                        Button(onClick = { onSwitch(target.id, pinInput) }, colors = ButtonDefaults.buttonColors(containerColor = AkisRed)) {
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
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Checkbox(checked = newIsKids, onCheckedChange = { newIsKids = it })
                    Text("Çocuk Profili (+18/korku gizlenir)", color = Color.White, fontSize = 12.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    colors.forEach { hex ->
                        val c = runCatching { Color(android.graphics.Color.parseColor(hex)) }.getOrDefault(AkisRed)
                        Box(
                            Modifier.size(28.dp).clip(CircleShape).background(c)
                                .border(2.dp, if (selectedColor == hex) Color.White else Color.Transparent, CircleShape)
                                .clickable { selectedColor = hex },
                        )
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
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = AkisRed, contentColor = Color.White),
                ) { Text("Profil Oluştur") }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Kapat", color = Color.White) } },
    )
}
