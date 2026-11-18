package app.cineva.player.data

import org.junit.Assert.assertEquals
import org.junit.Test

class CloudAccountTest {
    @Test
    fun normalizesValidHttpsAndHttpUrls() {
        assertEquals("https://cineva.app", CloudUrlValidator.normalize("cineva.app/"))
        assertEquals("http://127.0.0.1:8899", CloudUrlValidator.normalize("http://127.0.0.1:8899/"))
    }

    @Test(expected = IptvException::class)
    fun rejectsEmptyOrCredentialEmbeddedUrls() {
        CloudUrlValidator.normalize("https://user:pass@cineva.app")
    }
}
