package app.mavie.player

import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.mavie.player.data.CloudAccountState
import app.mavie.player.data.CloudDevice
import app.mavie.player.data.CloudFeatures
import app.mavie.player.data.UserProfile
import app.mavie.player.player.PlayerScreen
import app.mavie.player.player.UpNextEpisode
import app.mavie.player.ui.DetailUiState
import app.mavie.player.ui.LibraryTab
import app.mavie.player.ui.LibraryUiState
import app.mavie.player.ui.ProfilePickerDialog
import app.mavie.player.ui.UiCollection
import app.mavie.player.ui.UiMedia
import app.mavie.player.ui.UiSeason
import app.mavie.player.ui.MavieDetailScreen
import app.mavie.player.ui.MavieLibraryScreen
import app.mavie.player.ui.MavieSettingsScreen
import app.mavie.player.ui.MavieTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.time.Instant

@RunWith(AndroidJUnit4::class)
class AccessibilityAndCloudUiTest {
    @get:Rule
    val rule = createAndroidComposeRule<MainActivity>()

    @Test
    fun libraryScreenControlsHaveLabelsAndMinimumTouchTargets() {
        val sampleMovie = UiMedia(
            id = "vod:1",
            title = "Büyük Macera",
            kind = "vod",
            year = "2025",
            rating = 8.4,
            progressPositionMs = 120_000L,
            progressDurationMs = 600_000L,
        )
        val state = LibraryUiState(
            tab = LibraryTab.HOME,
            items = listOf(sampleMovie),
            continueWatching = listOf(sampleMovie),
            showcase = listOf(sampleMovie),
            featured = sampleMovie,
            collections = listOf(UiCollection("c1", "Hafta Sonu", 1)),
            loading = false,
        )

        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    MavieLibraryScreen(
                        state = state,
                        onTab = {},
                        onQuery = {},
                        onCategory = {},
                        onMedia = {},
                        onPlay = {},
                        onFavorite = {},
                        onRefresh = {},
                        onSettings = {},
                        onCollection = {},
                        onCreateCollection = {},
                        onLoadMore = {},
                        onAddToCollection = {},
                        activeProfileName = "Ana Profil",
                        activeProfileColor = "#7C3AED",
                        sportsContent = {},
                    )
                }
            }
        }

        val topBarDescriptions = listOf(
            "Rastgele içerik seç",
            "Cihazdan video aç",
            "Kütüphanede ara",
            "Profil değiştir: Ana Profil",
            "Ayarlar",
        )
        topBarDescriptions.forEach { label ->
            rule.onNodeWithContentDescription(label)
                .assertIsDisplayed()
                .assertWidthIsAtLeast(48.dp)
                .assertHeightIsAtLeast(48.dp)
        }

        rule.onNodeWithText("Devam Et")
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Listeme Ekle")
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithContentDescription("Büyük Macera izlemeye devam et")
            .performScrollTo()
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun detailScreenControlsHaveLabelsAndMinimumTouchTargets() {
        val episode1 = UiMedia(
            id = "ep:1",
            title = "1. Bölüm",
            kind = "episode",
            episodeNumber = 1,
            progressPositionMs = 60_000L,
            progressDurationMs = 1_800_000L,
        )
        val series = UiMedia(
            id = "series:1",
            title = "Örnek Dizi",
            kind = "series",
            year = "2025",
            rating = 8.9,
            overview = "Kısa açıklama metni.",
            progressPositionMs = 60_000L,
            progressDurationMs = 1_800_000L,
        )
        val detail = DetailUiState(
            media = series,
            genre = "Bilim Kurgu",
            seasons = listOf(UiSeason("1", "1. Sezon", listOf(episode1))),
            selectedSeasonId = "1",
        )

        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    MavieDetailScreen(
                        state = detail,
                        onBack = {},
                        onPlay = {},
                        onFavorite = {},
                        onEpisode = {},
                        onSeason = {},
                        onAddToCollection = {},
                        onRetry = {},
                        onClearProgress = {},
                    )
                }
            }
        }

        rule.onNodeWithContentDescription("Geri dön")
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Favorilere ekle")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Listeme ekle")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithContentDescription("İzleme kaydını sıfırla")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithContentDescription("1. Bölüm bölümünü listeye ekle")
            .performScrollTo()
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun profilePickerDialogSwatchesCheckboxAndActionsHaveMinimumTouchTargets() {
        val profiles = listOf(
            UserProfile("default", "Ana Profil", "#7C3AED", isKids = false, hasPin = false, active = true),
            UserProfile("kids", "Çocuk", "#34C759", isKids = true, hasPin = true, active = false),
        )

        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    ProfilePickerDialog(
                        profiles = profiles,
                        error = null,
                        onSwitch = { _, _ -> },
                        onCreate = { _, _, _, _ -> },
                        onDelete = {},
                        onDismiss = {},
                    )
                }
            }
        }

        rule.onNodeWithText("Profiller").assertIsDisplayed()
        rule.onNodeWithContentDescription("Çocuk profilini sil")
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Çocuk Profili (+18/korku gizlenir)")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)

        val swatchColors = listOf(
            "Profil rengi: Mavie Moru",
            "Profil rengi: Okyanus Turkuazı",
            "Profil rengi: Zümrüt Yeşili",
            "Profil rengi: Mor İndigo",
            "Profil rengi: Gökyüzü Mavisi",
        )
        swatchColors.forEach { desc ->
            rule.onNodeWithContentDescription(desc)
                .performScrollTo()
                .assertIsDisplayed()
                .assertWidthIsAtLeast(48.dp)
                .assertHeightIsAtLeast(48.dp)
        }

        rule.onNodeWithText("Profil Oluştur")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Kapat")
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun settingsScreenSignedOutAuthStepsHaveClearLabelsAndAccessibleControls() {
        fun renderStep(step: CloudAuthStep, pendingEmail: String = "") {
            rule.runOnUiThread {
                rule.activity.setContent {
                    MavieTheme {
                        MavieSettingsScreen(
                            accountName = "Demo Hesap",
                            catalogSummary = "Doğrudan cihaz içi oynatma",
                            refreshing = false,
                            error = null,
                            onBack = {},
                            onRefresh = {},
                            onExport = {},
                            onImport = {},
                            onSync = {},
                            onLogout = {},
                            cloudState = CloudAccountState(signedIn = false),
                            cloudAuthStep = step,
                            cloudPendingEmail = pendingEmail,
                        )
                    }
                }
            }
        }

        // 1. IDLE (login & register tabs + password length rule check)
        renderStep(CloudAuthStep.IDLE)
        rule.onNodeWithContentDescription("Geri dön")
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Normal vs Mavie Pro").performScrollTo().assertIsDisplayed()
        rule.onNodeWithContentDescription("Parolayı göster")
            .performScrollTo()
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Parolamı Unuttum")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)

        // Login tab allows shorter pre-existing passwords (clPass.isNotBlank())
        val textFields = rule.onAllNodes(hasSetTextAction())
        textFields[1].performTextInput("user@mavie.app")
        textFields[2].performTextInput("123456")
        rule.onAllNodesWithText("Giriş Yap").let { nodes ->
            // Last node with "Giriş Yap" is the submit button (first is FilterChip)
            val submitBtn = nodes[nodes.fetchSemanticsNodes().lastIndex]
            submitBtn.performScrollTo().assertIsEnabled().assertHeightIsAtLeast(48.dp)
        }

        // Register tab enforces >= 8 char password
        rule.onNodeWithText("Kayıt Ol (3 Gün Pro Deneme)").performScrollTo().performClick()
        rule.onNodeWithText("Kayıt Ol ve Doğrulama Kodu Al")
            .performScrollTo()
            .assertIsNotEnabled()
            .assertHeightIsAtLeast(48.dp)

        // 2. VERIFY_EMAIL
        renderStep(CloudAuthStep.VERIFY_EMAIL, pendingEmail = "test@mavie.app")
        rule.onNodeWithText("E-posta Doğrulama", substring = true).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Doğrula ve 3 Günlük Pro Denemeyi Başlat")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Kodu Tekrar Gönder")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)

        // 3. FORGOT_PASSWORD
        renderStep(CloudAuthStep.FORGOT_PASSWORD)
        rule.onNodeWithText("Parola Sıfırlama Kodu İste").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Sıfırlama Kodu Gönder")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Kodum Var")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)

        // 4. RESET_PASSWORD
        renderStep(CloudAuthStep.RESET_PASSWORD, pendingEmail = "test@mavie.app")
        rule.onNodeWithText("Yeni Parola Belirle", substring = true).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Kodu Kontrol Et")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Parolayı Güncelle")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun settingsScreenSignedInNormalAndTrialPlansRenderProperly() {
        val sampleDevice = CloudDevice("dev1", "Pixel 9 QA", "android")
        val normalState = CloudAccountState(
            cloudUrl = "https://cineva-app.netlify.app",
            email = "normal@mavie.app",
            displayName = "Normal Kullanıcı",
            emailVerified = true,
            plan = "normal",
            effectivePlan = "normal",
            isPro = false,
            trialActive = false,
            maxDevices = 1,
            devices = listOf(sampleDevice),
            features = CloudFeatures(maxDevices = 1),
            signedIn = true,
        )

        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    MavieSettingsScreen(
                        accountName = "Demo",
                        catalogSummary = "Doğrudan cihaz içi oynatma",
                        refreshing = false,
                        error = null,
                        onBack = {},
                        onRefresh = {},
                        onExport = {},
                        onImport = {},
                        onSync = {},
                        onLogout = {},
                        cloudState = normalState,
                    )
                }
            }
        }

        rule.onNodeWithText("NORMAL PLAN").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Normal vs Mavie Pro").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Bulut Eşitleme (Mavie Pro)")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithContentDescription("Pixel 9 QA cihazını kaldır")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Planı Yenile").performScrollTo().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Hesaptan Çık").performScrollTo().assertHeightIsAtLeast(48.dp)

        // Switch to 3-Day Pro Trial
        val trialState = normalState.copy(
            email = "trial@mavie.app",
            displayName = "Deneme Kullanıcısı",
            plan = "pro",
            effectivePlan = "pro",
            isPro = true,
            trialActive = true,
            trialEndsAt = Instant.now().plusSeconds(86_400L * 2 + 3600L).toString(),
            maxDevices = 5,
            features = CloudFeatures(
                cloudSync = true,
                multiView = true,
                unlimitedProfiles = true,
                epgMatch = true,
                advancedTracks = true,
                maxDevices = 5,
            ),
        )

        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    MavieSettingsScreen(
                        accountName = "Demo",
                        catalogSummary = "Doğrudan cihaz içi oynatma",
                        refreshing = false,
                        error = null,
                        onBack = {},
                        onRefresh = {},
                        onExport = {},
                        onImport = {},
                        onSync = {},
                        onLogout = {},
                        cloudState = trialState,
                    )
                }
            }
        }

        rule.onNodeWithText("3 GÜNLÜK PRO DENEME").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("3 Günlük Pro Denemeniz Aktif").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Hesap Verilerini Şimdi Eşitle (Bulut)")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
    }

    @Test
    fun playerScreenPortraitOverflowAndLandscapeControlsHaveMinimumTouchTargets() {
        val episodes = listOf("ep1" to "S1·B1 — İlk Bölüm", "ep2" to "S1·B2 — İkinci Bölüm")

        // Portrait compact width (< 600.dp) shows "Seçenekler" overflow menu
        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    Box(Modifier.width(412.dp).fillMaxHeight()) {
                        PlayerScreen(
                            title = "Portre Test Videosu",
                            sourceUrl = "http://127.0.0.1:9/unused.mp4",
                            isLive = false,
                            nextEpisode = UpNextEpisode("İkinci Bölüm", 1, 2, ""),
                            onProgress = { _, _ -> },
                            episodes = episodes,
                            currentEpisodeId = "ep1",
                            initialLandscape = false,
                            onBack = {},
                        )
                    }
                }
            }
        }

        rule.waitUntil(10_000) {
            rule.onAllNodesWithContentDescription("Oynatıcıdan çık").fetchSemanticsNodes().isNotEmpty()
        }

        listOf("Oynatıcıdan çık", "Ekranı kilitle", "Sesi kapat", "Seçenekler").forEach { desc ->
            rule.onNodeWithContentDescription(desc)
                .assertIsDisplayed()
                .assertWidthIsAtLeast(48.dp)
                .assertHeightIsAtLeast(48.dp)
        }
        rule.onNodeWithText("Ses").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Altyazı").assertIsDisplayed().assertHeightIsAtLeast(48.dp)

        // Open portrait overflow menu and verify labeled items
        rule.onNodeWithContentDescription("Seçenekler").performClick()
        rule.onNodeWithText("Oynatma Hızı (1.0x)").assertIsDisplayed()
        rule.onNodeWithText("Ekran Oranı (Sığdır)").assertIsDisplayed()
        rule.onNodeWithText("Uyku Zamanlayıcısı (Kapalı)").assertIsDisplayed()
        rule.onNodeWithText("Bölümler").assertIsDisplayed()

        // Landscape wide width (>= 600.dp) shows inline secondary controls without overflow button
        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    Box(Modifier.width(760.dp).fillMaxHeight()) {
                        PlayerScreen(
                            title = "Yatay Test Videosu",
                            sourceUrl = "http://127.0.0.1:9/unused.mp4",
                            isLive = false,
                            nextEpisode = UpNextEpisode("İkinci Bölüm", 1, 2, ""),
                            onProgress = { _, _ -> },
                            episodes = episodes,
                            currentEpisodeId = "ep1",
                            initialLandscape = true,
                            onBack = {},
                        )
                    }
                }
            }
        }

        rule.waitUntil(10_000) {
            rule.onAllNodesWithText("1.0x").fetchSemanticsNodes().isNotEmpty()
        }
        rule.onNodeWithText("1.0x").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Sığdır").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Uyku").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Bölümler").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        rule.onAllNodesWithContentDescription("Seçenekler").let { nodes ->
            assert(nodes.fetchSemanticsNodes().isEmpty()) {
                "Landscape player should show inline controls instead of overflow menu."
            }
        }
    }
}
