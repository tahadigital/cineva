package app.mavie.player.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.database.sqlite.SQLiteStatement
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

internal fun nowIso(): String = Instant.now().toString()
internal fun timestamp(value: String): Long = runCatching { Instant.parse(value).toEpochMilli() }.getOrDefault(0)

internal fun MediaItem.toStoredJson(): JSONObject = JSONObject()
    .put("id", id).put("providerId", providerId).put("name", name).put("kind", kind.key)
    .put("categoryId", categoryId).put("categoryName", categoryName).put("poster", poster).put("backdrop", backdrop)
    .put("year", year).put("rating", rating).put("extension", extension).put("durationSeconds", durationSeconds)
    .put("plot", plot).put("season", season).put("episode", episode).put("parentId", parentId ?: JSONObject.NULL)
    .put("genres", genres).put("addedAt", addedAt).put("videoCodec", videoCodec).put("audioCodec", audioCodec)
    .put("sourceUrl", sourceUrl)

internal fun storedItem(data: JSONObject): MediaItem = MediaItem(
    id = data.getString("id"), providerId = data.getString("providerId"), name = data.getString("name"),
    kind = MediaKind.fromKey(data.getString("kind")), categoryId = data.optString("categoryId"),
    categoryName = data.optString("categoryName"), poster = data.optString("poster"), backdrop = data.optString("backdrop"),
    year = data.optString("year"), rating = data.optDouble("rating", 0.0).finiteOrZero(), extension = data.optString("extension", "mp4"),
    durationSeconds = data.optDouble("durationSeconds", 0.0).finiteOrZero(), plot = data.optString("plot"),
    season = data.optInt("season"), episode = data.optInt("episode"), parentId = data.optString("parentId").takeUnless { it.isBlank() || it == "null" },
    genres = data.optString("genres"), addedAt = data.optLong("addedAt"), videoCodec = data.optString("videoCodec"), audioCodec = data.optString("audioCodec"),
    sourceUrl = data.optString("sourceUrl"),
)
internal fun Double.finiteOrZero(): Double = if (isFinite()) this else 0.0
internal fun values(vararg pairs: Pair<String, Any?>): ContentValues = ContentValues().apply {
    for ((key, value) in pairs) when(value) {
        null -> putNull(key)
        is String -> put(key, value)
        is Int -> put(key, value)
        is Long -> put(key, value)
        is Double -> put(key, value)
        is Boolean -> put(key, if(value) 1 else 0)
        else -> error("Unsupported local value")
    }
}

internal interface CatalogStore {
    fun replaceCatalog(account: String, kind: MediaKind, categories: List<Category>, items: List<MediaItem>)
    fun replaceAllCatalogsStream(account: String, stream: (onBatch: (List<MediaItem>) -> Unit) -> M3uStreamSummary): M3uStreamSummary
    fun putItems(account: String, items: List<MediaItem>)
    fun items(account: String, where: String = "1", args: List<String> = emptyList(), order: String = "i.added DESC,i.name COLLATE NOCASE,i.id", limit: Int = 60, offset: Int = 0, checkCancelled: () -> Unit = {}): List<MediaItem>
    fun item(account: String, id: String): MediaItem?
    fun count(account: String, where: String, args: List<String>): Int
    fun categories(account: String, kind: MediaKind): List<Category>
    fun putCache(account: String, key: String, data: String)
    fun cache(account: String, key: String): Pair<String, Long>?
    fun liveChannelNames(account: String): List<Pair<String, String>>
    fun favorite(account: String, item: MediaItem): Boolean
    fun progress(account: String, itemId: String): WatchProgress?
    fun saveProgress(account: String, item: MediaItem, position: Double, duration: Double)
    fun clearProgress(account: String, itemId: String)
    fun trackPreference(account: String, itemId: String): TrackPreference
    fun saveTrackPreference(account: String, itemId: String, preference: TrackPreference)
    fun playlists(account: String): List<Playlist>
    fun playlistItems(account: String, id: String): List<MediaItem>
    fun createPlaylist(account: String, name: String): Playlist
    fun addToPlaylist(account: String, playlistId: String, item: MediaItem)
    fun removeFromPlaylist(account: String, playlistId: String, itemId: String)
    fun deletePlaylist(account: String, playlistId: String)
    fun profiles(): List<UserProfile>
    fun activeProfile(): UserProfile
    fun createProfile(name: String, avatarColor: String, isKids: Boolean, pin: String): UserProfile
    fun deleteProfile(account: String?, profileId: String)
    fun switchProfile(account: String?, targetId: String, pin: String = ""): UserProfile
    fun saveSeriesDetail(account: String, updated: MediaItem, episodes: List<MediaItem>, infoJson: String)
    fun exportState(account: String): String
    fun importState(account: String, json: String)
}

internal class LocalDatabase(context: Context, name: String = "mavie_library.db") : SQLiteOpenHelper(context, name, null, 4), CatalogStore {
    init { setWriteAheadLoggingEnabled(true) }
    override fun onConfigure(db: SQLiteDatabase) { db.setForeignKeyConstraintsEnabled(true) }
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE items(account TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,provider_id TEXT NOT NULL,name TEXT NOT NULL,search TEXT NOT NULL,category_id TEXT NOT NULL,added INTEGER NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,parent_id TEXT,body TEXT NOT NULL,PRIMARY KEY(account,id))")
        db.execSQL("CREATE INDEX items_catalog ON items(account,kind,category_id,added DESC)")
        db.execSQL("CREATE INDEX items_parent ON items(account,parent_id,season,episode)")
        db.execSQL("CREATE INDEX items_recent ON items(account,kind,added DESC,name COLLATE NOCASE,id)")
        db.execSQL("CREATE TABLE categories(account TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,PRIMARY KEY(account,id,kind))")
        db.execSQL("CREATE TABLE favorites(account TEXT NOT NULL,item_id TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        db.execSQL("CREATE TABLE progress(account TEXT NOT NULL,item_id TEXT NOT NULL,position REAL NOT NULL,duration REAL NOT NULL,completed INTEGER NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        db.execSQL("CREATE TABLE playlists(account TEXT NOT NULL,id TEXT NOT NULL,name TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(account,id))")
        db.execSQL("CREATE TABLE playlist_items(account TEXT NOT NULL,playlist_id TEXT NOT NULL,item_id TEXT NOT NULL,position INTEGER NOT NULL,PRIMARY KEY(account,playlist_id,item_id),FOREIGN KEY(account,playlist_id) REFERENCES playlists(account,id) ON DELETE CASCADE)")
        db.execSQL("CREATE TABLE track_preferences(account TEXT NOT NULL,item_id TEXT NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        db.execSQL("CREATE TABLE native_track_preferences(account TEXT NOT NULL,item_id TEXT NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        db.execSQL("CREATE TABLE cache_meta(account TEXT NOT NULL,key TEXT NOT NULL,data TEXT NOT NULL,updated INTEGER NOT NULL,PRIMARY KEY(account,key))")
        ensureProfileSchema(db)
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if(oldVersion<2)db.execSQL("CREATE TABLE IF NOT EXISTS native_track_preferences(account TEXT NOT NULL,item_id TEXT NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        if(oldVersion<3)db.execSQL("CREATE INDEX IF NOT EXISTS items_recent ON items(account,kind,added DESC,name COLLATE NOCASE,id)")
        if(oldVersion<4)ensureProfileSchema(db)
    }

    private fun ensureProfileSchema(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT NOT NULL,avatar_color TEXT NOT NULL,is_kids INTEGER DEFAULT 0,pin_hash TEXT DEFAULT '',active INTEGER DEFAULT 0,created_at TEXT NOT NULL)")
        db.execSQL("CREATE TABLE IF NOT EXISTS profile_snapshots(account TEXT NOT NULL,profile_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(account,profile_id))")
        val hasProfiles = db.rawQuery("SELECT COUNT(*) FROM profiles", null).use { it.moveToFirst(); it.getInt(0) > 0 }
        if (!hasProfiles) {
            db.insertWithOnConflict("profiles", null, values("id" to "default", "name" to "Ana Profil", "avatar_color" to "#7C3AED", "is_kids" to 0, "pin_hash" to "", "active" to 1, "created_at" to nowIso()), SQLiteDatabase.CONFLICT_IGNORE)
        }
    }

    fun transaction(block: (SQLiteDatabase) -> Unit) {
        val db = writableDatabase
        db.beginTransaction()
        try { block(db); db.setTransactionSuccessful() } finally { db.endTransaction() }
    }

    private fun bindItemStatement(statement: SQLiteStatement, account: String, item: MediaItem) {
        statement.clearBindings()
        statement.bindString(1, account)
        statement.bindString(2, item.id)
        statement.bindString(3, item.kind.key)
        statement.bindString(4, item.providerId)
        statement.bindString(5, item.name)
        statement.bindString(6, fold(item.name))
        statement.bindString(7, item.categoryId)
        statement.bindLong(8, item.addedAt)
        statement.bindLong(9, item.season.toLong())
        statement.bindLong(10, item.episode.toLong())
        if (item.parentId == null) statement.bindNull(11) else statement.bindString(11, item.parentId)
        statement.bindString(12, item.toStoredJson().toString())
    }

    override fun putItems(account: String, items: List<MediaItem>) = putItems(account, items, writableDatabase)

    fun putItems(account: String, items: List<MediaItem>, db: SQLiteDatabase = writableDatabase) {
        if (items.isEmpty()) return
        val sql = "INSERT OR REPLACE INTO items(account,id,kind,provider_id,name,search,category_id,added,season,episode,parent_id,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        db.compileStatement(sql).use { statement ->
            for (item in items) {
                bindItemStatement(statement, account, item)
                statement.executeInsert()
            }
        }
    }

    override fun replaceCatalog(account: String, kind: MediaKind, categories: List<Category>, items: List<MediaItem>) = transaction { db ->
        db.delete("items", "account=? AND kind=?", arrayOf(account, kind.key))
        db.delete("categories", "account=? AND kind=?", arrayOf(account, kind.key))
        for (category in categories) db.insertOrThrow("categories", null, values("account" to account, "id" to category.id, "kind" to kind.key, "name" to category.name))
        putItems(account, items, db)
        putCache(account, "catalog:${kind.key}", "{}", db)
    }

    override fun replaceAllCatalogsStream(
        account: String,
        stream: (onBatch: (List<MediaItem>) -> Unit) -> M3uStreamSummary,
    ): M3uStreamSummary {
        var db: SQLiteDatabase? = null
        var itemStatement: SQLiteStatement? = null
        var started = false
        try {
            val summary = stream { batch ->
                if (batch.isEmpty()) return@stream
                if (!started) {
                    val writable = writableDatabase
                    writable.beginTransaction()
                    db = writable
                    started = true
                    writable.delete("items", "account=? AND kind IN ('live','vod','series')", arrayOf(account))
                    writable.delete("categories", "account=? AND kind IN ('live','vod','series')", arrayOf(account))
                    itemStatement = writable.compileStatement(
                        "INSERT OR REPLACE INTO items(account,id,kind,provider_id,name,search,category_id,added,season,episode,parent_id,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
                    )
                }
                val stmt = itemStatement!!
                for (item in batch) {
                    bindItemStatement(stmt, account, item)
                    stmt.executeInsert()
                }
            }
            if (!started || summary.itemCount == 0) {
                throw IptvException("M3U listesinde geçerli yayın bulunamadı.")
            }
            itemStatement?.close()
            itemStatement = null
            val writable = db!!
            for (kind in listOf(MediaKind.LIVE, MediaKind.VOD, MediaKind.SERIES)) {
                for (category in summary.categories[kind].orEmpty()) {
                    writable.insertOrThrow(
                        "categories",
                        null,
                        values("account" to account, "id" to category.id, "kind" to kind.key, "name" to category.name),
                    )
                }
                putCache(account, "catalog:${kind.key}", "{}", writable)
            }
            writable.setTransactionSuccessful()
            return summary
        } finally {
            runCatching { itemStatement?.close() }
            if (started) {
                runCatching { db?.endTransaction() }
            }
        }
    }

    private val itemSelect = "SELECT i.body,f.item_id AS favorite_id,p.position AS p_position,p.duration AS p_duration,p.completed AS p_completed,p.updated_at AS p_updated FROM items i LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id LEFT JOIN progress p ON p.account=i.account AND p.item_id=i.id"
    override fun items(account: String, where: String, args: List<String>, order: String, limit: Int, offset: Int, checkCancelled: () -> Unit): List<MediaItem> {
        checkCancelled()
        return readableDatabase.rawQuery("$itemSelect WHERE i.account=? AND ($where) ORDER BY $order LIMIT ? OFFSET ?", (listOf(account)+args+listOf(limit.coerceIn(1,20000).toString(),offset.coerceAtLeast(0).toString())).toTypedArray()).use { cursor ->
            buildList {
                while (true) {
                    checkCancelled()
                    if (!cursor.moveToNext()) break
                    checkCancelled()
                    add(readItem(cursor,account))
                }
            }
        }
    }
    private fun readItem(cursor: Cursor, account: String): MediaItem {
        val item = storedItem(JSONObject(cursor.getString(0)))
        val progress = if(cursor.isNull(2)) null else WatchProgress(item.id,cursor.getDouble(2),cursor.getDouble(3),cursor.getInt(4)!=0,timestamp(cursor.getString(5)))
        return item.copy(isFavorite = !cursor.isNull(1),progress = progress,accountId = account)
    }
    override fun item(account: String, id: String): MediaItem? = items(account,"i.id=?",listOf(id),limit=1).firstOrNull()
    override fun count(account: String, where: String, args: List<String>): Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM items i LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id WHERE i.account=? AND ($where)",(listOf(account)+args).toTypedArray()).use { it.moveToFirst();it.getInt(0) }
    override fun categories(account: String, kind: MediaKind): List<Category> = readableDatabase.rawQuery("SELECT id,name FROM categories WHERE account=? AND kind=? ORDER BY name COLLATE NOCASE",arrayOf(account,kind.key)).use { c -> buildList { while(c.moveToNext()) add(Category(c.getString(0),c.getString(1),kind)) } }
    override fun putCache(account: String, key: String, data: String) = putCache(account, key, data, writableDatabase)
    fun putCache(account: String, key: String, data: String, db: SQLiteDatabase = writableDatabase) { db.insertWithOnConflict("cache_meta",null,values("account" to account,"key" to key,"data" to data,"updated" to System.currentTimeMillis()),SQLiteDatabase.CONFLICT_REPLACE) }
    override fun cache(account: String, key: String): Pair<String,Long>? = readableDatabase.rawQuery("SELECT data,updated FROM cache_meta WHERE account=? AND key=?",arrayOf(account,key)).use { if(it.moveToFirst()) it.getString(0) to it.getLong(1) else null }
    override fun liveChannelNames(account: String): List<Pair<String, String>> = readableDatabase.rawQuery(
        "SELECT id,name FROM items WHERE account=? AND kind=? ORDER BY name COLLATE NOCASE,id",
        arrayOf(account, MediaKind.LIVE.key),
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(cursor.getString(0) to cursor.getString(1))
        }
    }
    override fun favorite(account: String, item: MediaItem): Boolean {
        var selected=false
        transaction { db ->
            putItems(account,listOf(item),db)
            val removed=db.delete("favorites","account=? AND item_id=?",arrayOf(account,item.id))
            selected=removed==0
            if(selected)db.insertOrThrow("favorites",null,values("account" to account,"item_id" to item.id,"created_at" to nowIso()))
        }
        return selected
    }
    override fun progress(account: String, itemId: String): WatchProgress? = readableDatabase.rawQuery(
        "SELECT position,duration,completed,updated_at FROM progress WHERE account=? AND item_id=?",
        arrayOf(account, itemId),
    ).use { c ->
        if (c.moveToFirst()) WatchProgress(itemId, c.getDouble(0), c.getDouble(1), c.getInt(2) != 0, timestamp(c.getString(3))) else null
    }
    override fun saveProgress(account: String, item: MediaItem, position: Double, duration: Double) = transaction { db ->
        val exists=db.rawQuery("SELECT 1 FROM items WHERE account=? AND id=?",arrayOf(account,item.id)).use { it.moveToFirst() }
        if(!exists)putItems(account,listOf(item),db)
        val total=duration.finiteOrZero().coerceAtLeast(0.0)
        val at=position.finiteOrZero().coerceAtLeast(0.0).let { if(total>0)it.coerceAtMost(total) else it }
        db.insertWithOnConflict("progress",null,values("account" to account,"item_id" to item.id,"position" to at,"duration" to total,"completed" to (total>0&&at/total>=.95),"updated_at" to nowIso()),SQLiteDatabase.CONFLICT_REPLACE)
    }
    override fun clearProgress(account: String, itemId: String) {
        writableDatabase.delete("progress", "account=? AND item_id=?", arrayOf(account, itemId))
    }
    override fun trackPreference(account: String, itemId: String): TrackPreference = readableDatabase.rawQuery("SELECT data FROM native_track_preferences WHERE account=? AND item_id=?",arrayOf(account,itemId)).use {
        if(!it.moveToFirst())return@use TrackPreference()
        val json=JSONObject(it.getString(0))
        TrackPreference(if(json.isNull("audioId"))null else json.optInt("audioId"),if(json.isNull("subtitleId"))null else json.optInt("subtitleId"),json.optBoolean("subtitleOff",true))
    }
    override fun saveTrackPreference(account: String, itemId: String, preference: TrackPreference) {
        val data=JSONObject().put("audioId",preference.audioId?:JSONObject.NULL).put("subtitleId",preference.subtitleId?:JSONObject.NULL).put("subtitleOff",preference.subtitleOff)
        writableDatabase.insertWithOnConflict("native_track_preferences",null,values("account" to account,"item_id" to itemId,"data" to data.toString(),"updated_at" to nowIso()),SQLiteDatabase.CONFLICT_REPLACE)
    }
    override fun playlists(account: String): List<Playlist> = readableDatabase.rawQuery("SELECT p.id,p.name,COUNT(pi.item_id) FROM playlists p LEFT JOIN playlist_items pi ON pi.account=p.account AND pi.playlist_id=p.id WHERE p.account=? GROUP BY p.id ORDER BY p.created_at",arrayOf(account)).use { c -> buildList { while(c.moveToNext()) { val id=c.getString(0);add(Playlist(id,c.getString(1),c.getInt(2))) } } }
    override fun playlistItems(account: String, id: String): List<MediaItem> = items(account,"i.id IN (SELECT item_id FROM playlist_items WHERE account=? AND playlist_id=?)",listOf(account,id),order="(SELECT position FROM playlist_items WHERE account=i.account AND playlist_id='${id.replace("'","''")}' AND item_id=i.id)",limit=20000)
    override fun createPlaylist(account: String, name: String): Playlist {
        val clean=name.trim().take(100);if(clean.isEmpty())throw IptvException("Liste adı boş olamaz.")
        val id=UUID.randomUUID().toString()
        writableDatabase.insertOrThrow("playlists",null,values("account" to account,"id" to id,"name" to clean,"created_at" to nowIso()))
        return Playlist(id,clean,0)
    }
    override fun addToPlaylist(account: String, playlistId: String, item: MediaItem) = transaction { db ->
        putItems(account,listOf(item),db)
        val position=db.rawQuery("SELECT COALESCE(MAX(position),-1)+1 FROM playlist_items WHERE account=? AND playlist_id=?",arrayOf(account,playlistId)).use { it.moveToFirst();it.getInt(0) }
        try { db.insertWithOnConflict("playlist_items",null,values("account" to account,"playlist_id" to playlistId,"item_id" to item.id,"position" to position),SQLiteDatabase.CONFLICT_IGNORE) }
        catch (_: android.database.sqlite.SQLiteConstraintException) { throw IptvException("Liste bulunamadı.") }
    }
    override fun removeFromPlaylist(account: String, playlistId: String, itemId: String) { writableDatabase.delete("playlist_items","account=? AND playlist_id=? AND item_id=?",arrayOf(account,playlistId,itemId)) }
    override fun deletePlaylist(account: String, playlistId: String) { writableDatabase.delete("playlists","account=? AND id=?",arrayOf(account,playlistId)) }

    override fun profiles(): List<UserProfile> = readableDatabase.rawQuery(
        "SELECT id,name,avatar_color,is_kids,pin_hash,active FROM profiles ORDER BY CASE WHEN id='default' THEN 0 ELSE 1 END, created_at",
        null,
    ).use { c ->
        buildList {
            while (c.moveToNext()) {
                add(UserProfile(c.getString(0), c.getString(1), c.getString(2), c.getInt(3) != 0, c.getString(4).isNotEmpty(), c.getInt(5) != 0))
            }
        }
    }

    override fun activeProfile(): UserProfile = profiles().firstOrNull { it.active } ?: profiles().firstOrNull()
        ?: UserProfile("default", "Ana Profil", "#7C3AED", active = true)

    override fun createProfile(name: String, avatarColor: String, isKids: Boolean, pin: String): UserProfile {
        val clean = name.trim().take(60)
        if (clean.isEmpty()) throw IptvException("Profil adı boş olamaz.")
        val color = if (avatarColor.matches(Regex("^#[0-9A-Fa-f]{6}$"))) avatarColor else "#7C3AED"
        val pinHash = ProfilePinHasher.hash(pin)
        val id = "p_" + UUID.randomUUID().toString().replace("-", "").take(12)
        writableDatabase.insertOrThrow("profiles", null, values("id" to id, "name" to clean, "avatar_color" to color, "is_kids" to if (isKids) 1 else 0, "pin_hash" to pinHash, "active" to 0, "created_at" to nowIso()))
        return UserProfile(id, clean, color, isKids, pinHash.isNotEmpty(), false)
    }

    override fun deleteProfile(account: String?, profileId: String) {
        if (profileId == "default") throw IptvException("Ana profil silinemez.")
        val current = activeProfile()
        if (current.id == profileId) switchProfile(account, "default", "")
        writableDatabase.delete("profiles", "id=?", arrayOf(profileId))
        writableDatabase.delete("profile_snapshots", "profile_id=?", arrayOf(profileId))
    }

    override fun switchProfile(account: String?, targetId: String, pin: String): UserProfile {
        val targetRow = readableDatabase.rawQuery("SELECT id,name,avatar_color,is_kids,pin_hash,active FROM profiles WHERE id=?", arrayOf(targetId)).use { c ->
            if (!c.moveToFirst()) throw IptvException("Profil bulunamadı.")
            Tuple6(c.getString(0), c.getString(1), c.getString(2), c.getInt(3) != 0, c.getString(4), c.getInt(5) != 0)
        }
        if (targetRow.fifth.isNotEmpty() && !ProfilePinHasher.verify(pin, targetRow.fifth)) {
            throw IptvException("Profil PIN kodu hatalı.")
        }
        if (targetRow.sixth) return activeProfile()
        transaction { db ->
            val prevId = db.rawQuery("SELECT id FROM profiles WHERE active=1 LIMIT 1", null).use { if (it.moveToFirst()) it.getString(0) else "default" }
            if (account != null) {
                db.insertWithOnConflict("profile_snapshots", null, values("account" to account, "profile_id" to prevId, "data" to dumpSnapshot(db, account).toString()), SQLiteDatabase.CONFLICT_REPLACE)
                for (table in listOf("playlist_items", "playlists", "favorites", "progress", "native_track_preferences")) {
                    db.delete(table, "account=?", arrayOf(account))
                }
                val snapJson = db.rawQuery("SELECT data FROM profile_snapshots WHERE account=? AND profile_id=?", arrayOf(account, targetId)).use { if (it.moveToFirst()) it.getString(0) else null }
                if (snapJson != null) restoreSnapshot(db, account, JSONObject(snapJson))
            }
            db.execSQL("UPDATE profiles SET active = CASE WHEN id = ? THEN 1 ELSE 0 END", arrayOf(targetId))
        }
        return activeProfile()
    }

    private fun dumpSnapshot(db: SQLiteDatabase, account: String): JSONObject {
        val favs = org.json.JSONArray()
        db.rawQuery("SELECT item_id,created_at FROM favorites WHERE account=?", arrayOf(account)).use { c ->
            while (c.moveToNext()) favs.put(JSONObject().put("id", c.getString(0)).put("t", c.getString(1)))
        }
        val prog = org.json.JSONArray()
        db.rawQuery("SELECT item_id,position,duration,completed,updated_at FROM progress WHERE account=?", arrayOf(account)).use { c ->
            while (c.moveToNext()) prog.put(JSONObject().put("id", c.getString(0)).put("p", c.getDouble(1)).put("d", c.getDouble(2)).put("c", c.getInt(3)).put("u", c.getString(4)))
        }
        val lists = org.json.JSONArray()
        db.rawQuery("SELECT id,name,created_at FROM playlists WHERE account=?", arrayOf(account)).use { c ->
            while (c.moveToNext()) lists.put(JSONObject().put("id", c.getString(0)).put("n", c.getString(1)).put("t", c.getString(2)))
        }
        val listItems = org.json.JSONArray()
        db.rawQuery("SELECT playlist_id,item_id,position FROM playlist_items WHERE account=?", arrayOf(account)).use { c ->
            while (c.moveToNext()) listItems.put(JSONObject().put("lid", c.getString(0)).put("iid", c.getString(1)).put("pos", c.getInt(2)))
        }
        return JSONObject().put("favorites", favs).put("progress", prog).put("playlists", lists).put("playlistItems", listItems)
    }

    private fun restoreSnapshot(db: SQLiteDatabase, account: String, snap: JSONObject) {
        snap.optJSONArray("favorites")?.let { arr ->
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                db.insertWithOnConflict("favorites", null, values("account" to account, "item_id" to it.getString("id"), "created_at" to it.getString("t")), SQLiteDatabase.CONFLICT_IGNORE)
            }
        }
        snap.optJSONArray("progress")?.let { arr ->
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                db.insertWithOnConflict("progress", null, values("account" to account, "item_id" to it.getString("id"), "position" to it.getDouble("p"), "duration" to it.getDouble("d"), "completed" to (it.getInt("c") != 0), "updated_at" to it.getString("u")), SQLiteDatabase.CONFLICT_REPLACE)
            }
        }
        snap.optJSONArray("playlists")?.let { arr ->
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                db.insertWithOnConflict("playlists", null, values("account" to account, "id" to it.getString("id"), "name" to it.getString("n"), "created_at" to it.getString("t")), SQLiteDatabase.CONFLICT_IGNORE)
            }
        }
        snap.optJSONArray("playlistItems")?.let { arr ->
            for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                db.insertWithOnConflict("playlist_items", null, values("account" to account, "playlist_id" to it.getString("lid"), "item_id" to it.getString("iid"), "position" to it.getInt("pos")), SQLiteDatabase.CONFLICT_IGNORE)
            }
        }
    }

    override fun saveSeriesDetail(account: String, updated: MediaItem, episodes: List<MediaItem>, infoJson: String) {
        transaction { db ->
            db.delete("items", "account=? AND parent_id=?", arrayOf(account, updated.id))
            putItems(account, listOf(updated) + episodes, db)
            putCache(account, "detail:${updated.id}", infoJson, db)
        }
    }

    override fun exportState(account: String): String = StateBackup.export(this, account)

    override fun importState(account: String, json: String) = StateBackup.import(this, account, json)

    private data class Tuple6(val first: String, val second: String, val third: String, val fourth: Boolean, val fifth: String, val sixth: Boolean)
}
