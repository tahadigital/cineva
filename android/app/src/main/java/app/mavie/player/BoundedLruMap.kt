package app.mavie.player

internal class BoundedLruMap<K, V>(private val maxSize: Int = 2_000) {
    private val lock = Any()
    private val map = object : LinkedHashMap<K, V>(minOf(maxSize.coerceAtLeast(1), 256), 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, V>?): Boolean = size > maxSize
    }

    init {
        require(maxSize > 0) { "maxSize must be positive" }
    }

    operator fun get(key: K): V? = synchronized(lock) { map[key] }

    operator fun set(key: K, value: V) {
        synchronized(lock) {
            map[key] = value
        }
    }

    fun putAll(entries: Map<K, V>) {
        synchronized(lock) {
            map.putAll(entries)
        }
    }

    fun clear() {
        synchronized(lock) {
            map.clear()
        }
    }

    val size: Int
        get() = synchronized(lock) { map.size }

    fun containsKey(key: K): Boolean = synchronized(lock) { map.containsKey(key) }
}
