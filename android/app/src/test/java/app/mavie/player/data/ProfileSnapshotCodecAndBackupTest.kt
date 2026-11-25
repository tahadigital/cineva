package app.mavie.player.data

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ProfileSnapshotCodecAndBackupTest {
    @Test
    fun profileSnapshotCodecRoundTripsAllTablesIncludingNativeTrackPreferences() {
        val original = ProfileSnapshotData(
            favorites = listOf(FavoriteSnapshotRow("vod:1", "2026-11-22T10:00:00Z")),
            progress = listOf(ProgressSnapshotRow("vod:1", 125.5, 3600.0, false, "2026-11-22T10:05:00Z")),
            playlists = listOf(PlaylistSnapshotRow("pl1", "Favorilerim", "2026-11-22T09:00:00Z")),
            playlistItems = listOf(PlaylistItemSnapshotRow("pl1", "vod:1", 0)),
            nativeTrackPreferences = listOf(
                NativeTrackSnapshotRow(
                    itemId = "vod:1",
                    data = """{"audioId":2,"subtitleId":5,"subtitleOff":false}""",
                    updatedAt = "2026-11-22T10:06:00Z",
                ),
            ),
        )
        val encoded = ProfileSnapshotCodec.encode(original)
        val decoded = ProfileSnapshotCodec.decode(JSONObject(encoded.toString()))
        assertEquals(original, decoded)
    }

    @Test
    fun profileSnapshotCodecHandlesLegacySnapshotWithoutNativeTrackPreferences() {
        val legacy = JSONObject()
            .put("favorites", JSONArray().put(JSONObject().put("id", "vod:2").put("t", "2026-11-22T10:00:00Z")))
        val decoded = ProfileSnapshotCodec.decode(legacy)
        assertEquals(1, decoded.favorites.size)
        assertTrue(decoded.nativeTrackPreferences.isEmpty())
    }

    @Test
    fun stateBackupValidateAndParseAcceptsValidV1AndRejectsUnsafeSchemesSizeAndVersion() {
        val validJson = JSONObject()
            .put("version", 1)
            .put(
                "items",
                JSONArray().put(
                    JSONObject()
                        .put("id", "vod:42")
                        .put("providerId", "42")
                        .put("name", "Örnek Film")
                        .put("kind", "vod")
                        .put("poster", "https://img.example.test/p.jpg")
                        .put("backdrop", "http://img.example.test/b.jpg")
                        .put("sourceUrl", "https://cdn.example.test/42.mp4"),
                ),
            )
            .put(
                "nativeTrackPreferences",
                JSONArray().put(
                    JSONObject()
                        .put("item_id", "vod:42")
                        .put("updated_at", "2026-11-22T10:00:00Z")
                        .put("data", JSONObject().put("audioId", 1).put("subtitleId", -1).put("subtitleOff", true)),
                ),
            )
            .toString()

        val parsed = StateBackup.validateAndParse(validJson)
        assertEquals(1, parsed.items.size)
        assertEquals("vod:42", parsed.items.single().id)
        assertEquals(1, parsed.nativePreferences.size)

        // Unsafe URL schemes in sourceUrl / poster / backdrop -> UNSAFE_URL
        for (field in listOf("sourceUrl", "poster", "backdrop")) {
            val badScheme = JSONObject(validJson)
            badScheme.getJSONArray("items").getJSONObject(0).put(field, "file:///etc/passwd")
            try {
                StateBackup.validateAndParse(badScheme.toString())
                fail("Expected UNSAFE_URL for $field=file:///etc/passwd")
            } catch (ex: IptvException) {
                assertEquals(MavieErrorCode.UNSAFE_URL, ex.code)
            }
        }

        // Unsupported version -> INVALID_INPUT
        val wrongVersion = JSONObject(validJson).put("version", 2).toString()
        try {
            StateBackup.validateAndParse(wrongVersion)
            fail("Expected INVALID_INPUT for version=2")
        } catch (ex: IptvException) {
            assertEquals(MavieErrorCode.INVALID_INPUT, ex.code)
        }

        // Payload > 25 MB -> PAYLOAD_TOO_LARGE
        val huge = " ".repeat(25 * 1024 * 1024 + 1)
        try {
            StateBackup.validateAndParse(huge)
            fail("Expected PAYLOAD_TOO_LARGE")
        } catch (ex: IptvException) {
            assertEquals(MavieErrorCode.PAYLOAD_TOO_LARGE, ex.code)
        }
    }
}
