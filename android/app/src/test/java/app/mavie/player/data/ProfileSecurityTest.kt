package app.mavie.player.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProfileSecurityTest {
    @Test
    fun pinHashingUsesUniqueSaltAndConstantTimeVerify() {
        val h1 = ProfilePinHasher.hash("1234")
        val h2 = ProfilePinHasher.hash("1234")
        assertNotEquals(h1, h2)
        assertFalse(h1.contains("1234"))
        assertTrue(h1.matches(Regex("^[0-9a-f]{32}:[0-9a-f]{64}$")))
        assertTrue(ProfilePinHasher.verify("1234", h1))
        assertFalse(ProfilePinHasher.verify("9999", h1))
        assertEquals("", ProfilePinHasher.hash(""))
        assertTrue(ProfilePinHasher.verify("", ""))
    }

    @Test(expected = IptvException::class)
    fun pinRejectsShortNonDigitPins() {
        ProfilePinHasher.hash("ab")
    }

    @Test
    fun adultContentFilterBlocksMatureAndHorrorCategoriesInKidsMode() {
        assertTrue(AdultContentFilter.isAdult("Gece Filmi", "Yetişkin +18"))
        assertTrue(AdultContentFilter.isAdult("Film 18+", "Sinema"))
        assertTrue(AdultContentFilter.isAdult("Karanlık", "Korku"))
        assertTrue(AdultContentFilter.isAdult("Test", "Adult Streams"))
        assertFalse(AdultContentFilter.isAdult("Big Buck Bunny", "Animasyon"))
        assertFalse(AdultContentFilter.isAdult("180 Dakika Spor", "Belgesel"))
    }
}
