package app.mavie.player

import org.junit.Assert.*
import org.junit.Test

class BoundedLruMapTest {
    @Test
    fun evictsLeastRecentlyUsedEntryWhenExceedingMaxSize() {
        val map = BoundedLruMap<String, Int>(maxSize = 3)
        map["a"] = 1
        map["b"] = 2
        map["c"] = 3
        // Touch "a" so "b" becomes the least recently used entry
        assertEquals(1, map["a"])

        map["d"] = 4
        assertEquals(3, map.size)
        assertTrue(map.containsKey("a"))
        assertFalse(map.containsKey("b"))
        assertTrue(map.containsKey("c"))
        assertTrue(map.containsKey("d"))
    }

    @Test
    fun supportsPutAllClearAndRejectsNonPositiveMaxSize() {
        val map = BoundedLruMap<String, String>(maxSize = 2)
        map.putAll(mapOf("k1" to "v1", "k2" to "v2", "k3" to "v3"))
        assertEquals(2, map.size)
        assertFalse(map.containsKey("k1"))
        assertEquals("v2", map["k2"])
        assertEquals("v3", map["k3"])

        map.clear()
        assertEquals(0, map.size)

        try {
            BoundedLruMap<String, String>(maxSize = 0)
            fail("maxSize = 0 must throw IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
        }
    }
}
