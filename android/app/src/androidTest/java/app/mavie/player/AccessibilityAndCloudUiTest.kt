package app.mavie.player

import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.width
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertWidthIsAtLeast
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
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
    fun settingsScreenFreeNoAccountHasAccessibleControlsAndZeroPaywall() {
        rule.runOnUiThread {
            rule.activity.setContent {
                MavieTheme {
                    MavieSettingsScreen(
                        accountName = "Açık Sinema · Demo",
                        catalogSummary = "Doğrudan cihaz içi oynatma · Hesap ve masaüstü gerektirmez",
                        refreshing = false,
                        error = null,
                        onBack = {},
                        onRefresh = {},
                        onExport = {},
                        onImport = {},
                        onSync = {},
                        onLogout = {},
                    )
                }
            }
        }

        rule.onNodeWithContentDescription("Geri dön")
            .assertIsDisplayed()
            .assertWidthIsAtLeast(48.dp)
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Kütüphaneyi yenile")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Yedek dışa aktar")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Yedek içe aktar")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Masaüstü ile eşitle")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Açık Kaynak Lisansları ve Bildirimler")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)
        rule.onNodeWithText("Kaynaktan çıkış yap")
            .performScrollTo()
            .assertIsDisplayed()
            .assertHeightIsAtLeast(48.dp)

        // Ensure zero cloud account / Pro paywall UI exists
        assert(rule.onAllNodesWithText("Mavie Pro", substring = true).fetchSemanticsNodes().isEmpty()) {
            "Free app must not render Mavie Pro upsell in Settings."
        }
        assert(rule.onAllNodesWithText("Portal Sunucu Adresi", substring = true).fetchSemanticsNodes().isEmpty()) {
            "Free app must not render cloud portal login in Settings."
        }
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
