package app.mavie.player.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.database.sqlite.SQLiteStatement
import org.json.JSONArray
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

internal fun MediaItem.toSlimStoredJson(): JSONObject? =
    if (plot.isEmpty()) null else toStoredJson().apply { remove("plot") }

internal fun storedItem(data: JSONObject, includeDetails: Boolean = true): MediaItem = MediaItem(
    id = data.getString("id"), providerId = data.getString("providerId"), name = data.getString("name"),
    kind = MediaKind.fromKey(data.getString("kind")), categoryId = data.optString("categoryId"),
    categoryName = data.optString("categoryName"), poster = data.optString("poster"), backdrop = data.optString("backdrop"),
    year = data.optString("year"), rating = data.optDouble("rating", 0.0).finiteOrZero(), extension = data.optString("extension", "mp4"),
    durationSeconds = data.optDouble("durationSeconds", 0.0).finiteOrZero(),
    plot = if (includeDetails) data.optString("plot") else "",
    season = data.optInt("season"), episode = data.optInt("episode"), parentId = data.optString("parentId").takeUnless { it.isBlank() || it == "null" },
    genres = data.optString("genres"), addedAt = data.optLong("addedAt"),
    videoCodec = if (includeDetails) data.optString("videoCodec") else "",
    audioCodec = if (includeDetails) data.optString("audioCodec") else "",
    sourceUrl = if (includeDetails) data.optString("sourceUrl") else "",
)

internal data class FavoriteSnapshotRow(val itemId: String, val createdAt: String)
internal data class ProgressSnapshotRow(val itemId: String, val position: Double, val duration: Double, val completed: Boolean, val updatedAt: String)
internal data class PlaylistSnapshotRow(val id: String, val name: String, val createdAt: String)
internal data class PlaylistItemSnapshotRow(val playlistId: String, val itemId: String, val position: Int)
internal data class NativeTrackSnapshotRow(val itemId: String, val data: String, val updatedAt: String)

internal data class ProfileSnapshotData(
    val favorites: List<FavoriteSnapshotRow> = emptyList(),
    val progress: List<ProgressSnapshotRow> = emptyList(),
    val playlists: List<PlaylistSnapshotRow> = emptyList(),
    val playlistItems: List<PlaylistItemSnapshotRow> = emptyList(),
    val nativeTrackPreferences: List<NativeTrackSnapshotRow> = emptyList(),
)

internal object ProfileSnapshotCodec {
    fun encode(data: ProfileSnapshotData): JSONObject {
        val favs = JSONArray()
        for (row in data.favorites) favs.put(JSONObject().put("id", row.itemId).put("t", row.createdAt))
        val prog = JSONArray()
        for (row in data.progress) {
            prog.put(
                JSONObject()
                    .put("id", row.itemId)
                    .put("p", row.position)
                    .put("d", row.duration)
                    .put("c", if (row.completed) 1 else 0)
                    .put("u", row.updatedAt)
            )
        }
        val lists = JSONArray()
        for (row in data.playlists) lists.put(JSONObject().put("id", row.id).put("n", row.name).put("t", row.createdAt))
        val listItems = JSONArray()
        for (row in data.playlistItems) listItems.put(JSONObject().put("lid", row.playlistId).put("iid", row.itemId).put("pos", row.position))
        val nativeTracks = JSONArray()
        for (row in data.nativeTrackPreferences) {
            nativeTracks.put(JSONObject().put("id", row.itemId).put("data", row.data).put("u", row.updatedAt))
        }
        return JSONObject()
            .put("favorites", favs)
            .put("progress", prog)
            .put("playlists", lists)
            .put("playlistItems", listItems)
            .put("nativeTrackPreferences", nativeTracks)
    }

    fun decode(snap: JSONObject): ProfileSnapshotData {
        val favs = buildList {
            snap.optJSONArray("favorites")?.let { arr ->
                for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                    add(FavoriteSnapshotRow(it.getString("id"), it.getString("t")))
                }
            }
        }
        val prog = buildList {
            snap.optJSONArray("progress")?.let { arr ->
                for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                    add(ProgressSnapshotRow(it.getString("id"), it.getDouble("p"), it.getDouble("d"), it.getInt("c") != 0, it.getString("u")))
                }
            }
        }
        val lists = buildList {
            snap.optJSONArray("playlists")?.let { arr ->
                for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                    add(PlaylistSnapshotRow(it.getString("id"), it.getString("n"), it.getString("t")))
                }
            }
        }
        val listItems = buildList {
            snap.optJSONArray("playlistItems")?.let { arr ->
                for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                    add(PlaylistItemSnapshotRow(it.getString("lid"), it.getString("iid"), it.getInt("pos")))
                }
            }
        }
        val nativeTracks = buildList {
            snap.optJSONArray("nativeTrackPreferences")?.let { arr ->
                for (i in 0 until arr.length()) arr.optJSONObject(i)?.let {
                    add(NativeTrackSnapshotRow(it.getString("id"), it.getString("data"), it.getString("u")))
                }
            }
        }
        return ProfileSnapshotData(favs, prog, lists, listItems, nativeTracks)
    }
}
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
    fun slimItems(account: String, where: String = "1", args: List<String> = emptyList(), order: String = "i.added DESC,i.name COLLATE NOCASE,i.id", limit: Int = 60, offset: Int = 0, checkCancelled: () -> Unit = {}): List<MediaItem> =
        items(account, where, args, order, limit, offset, checkCancelled)
    fun kidsCatalogPage(account: String, kind: MediaKind, where: String, args: List<String>, page: Int, pageSize: Int): CatalogPage {
        val filtered = items(account, where, args, limit = 20000).filter {
            it.kind == kind && !AdultContentFilter.isAdult(it.name, it.categoryName)
        }
        val from = (page * pageSize).coerceAtMost(filtered.size)
        val to = ((page + 1) * pageSize).coerceAtMost(filtered.size)
        return CatalogPage(filtered.subList(from, to), page, filtered.size, to < filtered.size)
    }
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
    fun close() {}
}

internal class LocalDatabase(context: Context, name: String = "mavie_library.db") : SQLiteOpenHelper(context, name, null, 5), CatalogStore {
    init { setWriteAheadLoggingEnabled(true) }
    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
        db.rawQuery("PRAGMA busy_timeout = 5000", null).use { it.moveToFirst() }
    }
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE items(account TEXT NOT NULL,id TEXT NOT NULL,kind TEXT NOT NULL,provider_id TEXT NOT NULL,name TEXT NOT NULL,search TEXT NOT NULL,category_id TEXT NOT NULL,added INTEGER NOT NULL,season INTEGER NOT NULL,episode INTEGER NOT NULL,parent_id TEXT,body TEXT NOT NULL,slim_body TEXT,PRIMARY KEY(account,id))")
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
        if(oldVersion<5)db.execSQL("ALTER TABLE items ADD COLUMN slim_body TEXT")
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
        val slim = item.toSlimStoredJson()?.toString()
        if (slim == null) statement.bindNull(13) else statement.bindString(13, slim)
    }

    override fun putItems(account: String, items: List<MediaItem>) = putItems(account, items, writableDatabase)

    fun putItems(account: String, items: List<MediaItem>, db: SQLiteDatabase = writableDatabase) {
        if (items.isEmpty()) return
        val sql = "INSERT OR REPLACE INTO items(account,id,kind,provider_id,name,search,category_id,added,season,episode,parent_id,body,slim_body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
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
                        "INSERT OR REPLACE INTO items(account,id,kind,provider_id,name,search,category_id,added,season,episode,parent_id,body,slim_body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    )
                }
                val stmt = itemStatement!!
                for (item in batch) {
                    bindItemStatement(stmt, account, item)
                    stmt.executeInsert()
                }
            }
            if (!started || summary.itemCount == 0) {
                throw IptvException("M3U listesinde geçerli yayın bulunamadı.", MavieErrorCode.EMPTY_CATALOG)
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
    private val slimItemSelect = "SELECT COALESCE(i.slim_body,i.body),f.item_id AS favorite_id,p.position AS p_position,p.duration AS p_duration,p.completed AS p_completed,p.updated_at AS p_updated FROM items i LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id LEFT JOIN progress p ON p.account=i.account AND p.item_id=i.id"

    override fun items(account: String, where: String, args: List<String>, order: String, limit: Int, offset: Int, checkCancelled: () -> Unit): List<MediaItem> {
        checkCancelled()
        return readableDatabase.rawQuery("$itemSelect WHERE i.account=? AND ($where) ORDER BY $order LIMIT ? OFFSET ?", (listOf(account)+args+listOf(limit.coerceIn(1,20000).toString(),offset.coerceAtLeast(0).toString())).toTypedArray()).use { cursor ->
            buildList {
                while (true) {
                    checkCancelled()
                    if (!cursor.moveToNext()) break
                    checkCancelled()
                    add(readItem(cursor, account, includeDetails = true))
                }
            }
        }
    }

    override fun slimItems(account: String, where: String, args: List<String>, order: String, limit: Int, offset: Int, checkCancelled: () -> Unit): List<MediaItem> {
        checkCancelled()
        return readableDatabase.rawQuery("$slimItemSelect WHERE i.account=? AND ($where) ORDER BY $order LIMIT ? OFFSET ?", (listOf(account)+args+listOf(limit.coerceIn(1,20000).toString(),offset.coerceAtLeast(0).toString())).toTypedArray()).use { cursor ->
            buildList {
                while (true) {
                    checkCancelled()
                    if (!cursor.moveToNext()) break
                    checkCancelled()
                    add(readItem(cursor, account, includeDetails = false))
                }
            }
        }
    }

    override fun kidsCatalogPage(account: String, kind: MediaKind, where: String, args: List<String>, page: Int, pageSize: Int): CatalogPage {
        val startIdx = page * pageSize
        val endIdx = startIdx + pageSize
        var kidsTotal = 0
        val pageIds = ArrayList<String>(pageSize)
        readableDatabase.rawQuery(
            "SELECT i.id, i.name, COALESCE(c.name, '') FROM items i LEFT JOIN categories c ON c.account=i.account AND c.id=i.category_id AND c.kind=i.kind LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id WHERE i.account=? AND ($where) ORDER BY i.added DESC,i.name COLLATE NOCASE,i.id",
            (listOf(account) + args).toTypedArray(),
        ).use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getString(0)
                val name = cursor.getString(1)
                val categoryName = cursor.getString(2)
                if (!AdultContentFilter.isAdult(name, categoryName)) {
                    if (kidsTotal in startIdx until endIdx) {
                        pageIds.add(id)
                    }
                    kidsTotal++
                }
            }
        }
        val fetched = if (pageIds.isEmpty()) {
            emptyList()
        } else {
            val placeholders = pageIds.joinToString(",") { "?" }
            val byId = items(account, "i.id IN ($placeholders)", pageIds, limit = pageIds.size).associateBy { it.id }
            pageIds.mapNotNull { byId[it] }
        }
        return CatalogPage(fetched, page, kidsTotal, endIdx < kidsTotal)
    }

    private fun readItem(cursor: Cursor, account: String, includeDetails: Boolean = true): MediaItem {
        val item = storedItem(JSONObject(cursor.getString(0)), includeDetails = includeDetails)
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
    override fun playlistItems(account: String, id: String): List<MediaItem> = readableDatabase.rawQuery(
        "SELECT i.body, f.item_id AS favorite_id, p.position AS p_position, p.duration AS p_duration, p.completed AS p_completed, p.updated_at AS p_updated " +
            "FROM playlist_items pi " +
            "INNER JOIN items i ON i.account = pi.account AND i.id = pi.item_id " +
            "LEFT JOIN favorites f ON f.account = i.account AND f.item_id = i.id " +
            "LEFT JOIN progress p ON p.account = i.account AND p.item_id = i.id " +
            "WHERE pi.account = ? AND pi.playlist_id = ? " +
            "ORDER BY pi.position ASC, i.name COLLATE NOCASE, i.id " +
            "LIMIT 20000",
        arrayOf(account, id),
    ).use { cursor ->
        buildList {
            while (cursor.moveToNext()) add(readItem(cursor, account, includeDetails = true))
        }
    }
    override fun createPlaylist(account: String, name: String): Playlist {
        val clean=name.trim().take(100);if(clean.isEmpty())throw IptvException("Liste adı boş olamaz.", MavieErrorCode.INVALID_INPUT)
        val id=UUID.randomUUID().toString()
        writableDatabase.insertOrThrow("playlists",null,values("account" to account,"id" to id,"name" to clean,"created_at" to nowIso()))
        return Playlist(id,clean,0)
    }
    override fun addToPlaylist(account: String, playlistId: String, item: MediaItem) = transaction { db ->
        putItems(account,listOf(item),db)
        val position=db.rawQuery("SELECT COALESCE(MAX(position),-1)+1 FROM playlist_items WHERE account=? AND playlist_id=?",arrayOf(account,playlistId)).use { it.moveToFirst();it.getInt(0) }
        try { db.insertWithOnConflict("playlist_items",null,values("account" to account,"playlist_id" to playlistId,"item_id" to item.id,"position" to position),SQLiteDatabase.CONFLICT_IGNORE) }
        catch (_: android.database.sqlite.SQLiteConstraintException) { throw IptvException("Liste bulunamadı.", MavieErrorCode.NOT_FOUND) }
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
        if (clean.isEmpty()) throw IptvException("Profil adı boş olamaz.", MavieErrorCode.INVALID_INPUT)
        val color = if (avatarColor.matches(Regex("^#[0-9A-Fa-f]{6}$"))) avatarColor else "#7C3AED"
        val pinHash = ProfilePinHasher.hash(pin)
        val id = "p_" + UUID.randomUUID().toString().replace("-", "").take(12)
        writableDatabase.insertOrThrow("profiles", null, values("id" to id, "name" to clean, "avatar_color" to color, "is_kids" to if (isKids) 1 else 0, "pin_hash" to pinHash, "active" to 0, "created_at" to nowIso()))
        return UserProfile(id, clean, color, isKids, pinHash.isNotEmpty(), false)
    }

    override fun deleteProfile(account: String?, profileId: String) {
        if (profileId == "default") throw IptvException("Ana profil silinemez.", MavieErrorCode.INVALID_INPUT)
        transaction { db ->
            val currentActive = db.rawQuery("SELECT id FROM profiles WHERE active=1 LIMIT 1", null).use {
                if (it.moveToFirst()) it.getString(0) else "default"
            }
            if (currentActive == profileId) {
                performProfileSwitchInTransaction(db, account, "default")
            }
            db.delete("profiles", "id=?", arrayOf(profileId))
            db.delete("profile_snapshots", "profile_id=?", arrayOf(profileId))
        }
    }

    override fun switchProfile(account: String?, targetId: String, pin: String): UserProfile {
        val targetRow = readableDatabase.rawQuery("SELECT id,name,avatar_color,is_kids,pin_hash,active FROM profiles WHERE id=?", arrayOf(targetId)).use { c ->
            if (!c.moveToFirst()) throw IptvException("Profil bulunamadı.", MavieErrorCode.PROFILE_NOT_FOUND)
            Tuple6(c.getString(0), c.getString(1), c.getString(2), c.getInt(3) != 0, c.getString(4), c.getInt(5) != 0)
        }
        if (targetRow.fifth.isNotEmpty() && !ProfilePinHasher.verify(pin, targetRow.fifth)) {
            throw IptvException("Profil PIN kodu hatalı.", MavieErrorCode.PROFILE_PIN_INVALID)
        }
        if (targetRow.sixth) return activeProfile()
        transaction { db ->
            performProfileSwitchInTransaction(db, account, targetId)
        }
        return activeProfile()
    }

    private fun performProfileSwitchInTransaction(db: SQLiteDatabase, account: String?, targetId: String) {
        val exists = db.rawQuery("SELECT 1 FROM profiles WHERE id=?", arrayOf(targetId)).use { it.moveToFirst() }
        if (!exists) throw IptvException("Profil bulunamadı.", MavieErrorCode.PROFILE_NOT_FOUND)
        val prevId = db.rawQuery("SELECT id FROM profiles WHERE active=1 LIMIT 1", null).use {
            if (it.moveToFirst()) it.getString(0) else "default"
        }
        if (prevId != targetId) {
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
    }

    private fun dumpSnapshot(db: SQLiteDatabase, account: String): JSONObject {
        val favs = buildList {
            db.rawQuery("SELECT item_id,created_at FROM favorites WHERE account=?", arrayOf(account)).use { c ->
                while (c.moveToNext()) add(FavoriteSnapshotRow(c.getString(0), c.getString(1)))
            }
        }
        val prog = buildList {
            db.rawQuery("SELECT item_id,position,duration,completed,updated_at FROM progress WHERE account=?", arrayOf(account)).use { c ->
                while (c.moveToNext()) add(ProgressSnapshotRow(c.getString(0), c.getDouble(1), c.getDouble(2), c.getInt(3) != 0, c.getString(4)))
            }
        }
        val lists = buildList {
            db.rawQuery("SELECT id,name,created_at FROM playlists WHERE account=?", arrayOf(account)).use { c ->
                while (c.moveToNext()) add(PlaylistSnapshotRow(c.getString(0), c.getString(1), c.getString(2)))
            }
        }
        val listItems = buildList {
            db.rawQuery("SELECT playlist_id,item_id,position FROM playlist_items WHERE account=?", arrayOf(account)).use { c ->
                while (c.moveToNext()) add(PlaylistItemSnapshotRow(c.getString(0), c.getString(1), c.getInt(2)))
            }
        }
        val nativeTracks = buildList {
            db.rawQuery("SELECT item_id,data,updated_at FROM native_track_preferences WHERE account=?", arrayOf(account)).use { c ->
                while (c.moveToNext()) add(NativeTrackSnapshotRow(c.getString(0), c.getString(1), c.getString(2)))
            }
        }
        return ProfileSnapshotCodec.encode(
            ProfileSnapshotData(favs, prog, lists, listItems, nativeTracks)
        )
    }

    private fun restoreSnapshot(db: SQLiteDatabase, account: String, snap: JSONObject) {
        val data = ProfileSnapshotCodec.decode(snap)
        for (row in data.favorites) {
            db.insertWithOnConflict("favorites", null, values("account" to account, "item_id" to row.itemId, "created_at" to row.createdAt), SQLiteDatabase.CONFLICT_IGNORE)
        }
        for (row in data.progress) {
            db.insertWithOnConflict("progress", null, values("account" to account, "item_id" to row.itemId, "position" to row.position, "duration" to row.duration, "completed" to row.completed, "updated_at" to row.updatedAt), SQLiteDatabase.CONFLICT_REPLACE)
        }
        for (row in data.playlists) {
            db.insertWithOnConflict("playlists", null, values("account" to account, "id" to row.id, "name" to row.name, "created_at" to row.createdAt), SQLiteDatabase.CONFLICT_IGNORE)
        }
        for (row in data.playlistItems) {
            db.insertWithOnConflict("playlist_items", null, values("account" to account, "playlist_id" to row.playlistId, "item_id" to row.itemId, "position" to row.position), SQLiteDatabase.CONFLICT_IGNORE)
        }
        for (row in data.nativeTrackPreferences) {
            db.insertWithOnConflict("native_track_preferences", null, values("account" to account, "item_id" to row.itemId, "data" to row.data, "updated_at" to row.updatedAt), SQLiteDatabase.CONFLICT_REPLACE)
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

    override fun close() {
        super<SQLiteOpenHelper>.close()
    }

    private data class Tuple6(val first: String, val second: String, val third: String, val fourth: Boolean, val fifth: String, val sixth: Boolean)
}
