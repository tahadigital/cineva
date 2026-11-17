package app.cineva.player.data

import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
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

internal class LocalDatabase(context: Context, name: String = "cineva_library.db") : SQLiteOpenHelper(context, name, null, 3) {
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
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if(oldVersion<2)db.execSQL("CREATE TABLE IF NOT EXISTS native_track_preferences(account TEXT NOT NULL,item_id TEXT NOT NULL,data TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account,item_id))")
        if(oldVersion<3)db.execSQL("CREATE INDEX IF NOT EXISTS items_recent ON items(account,kind,added DESC,name COLLATE NOCASE,id)")
    }

    fun transaction(block: (SQLiteDatabase) -> Unit) {
        val db = writableDatabase
        db.beginTransaction()
        try { block(db); db.setTransactionSuccessful() } finally { db.endTransaction() }
    }

    fun putItems(account: String, items: List<MediaItem>, db: SQLiteDatabase = writableDatabase) {
        val sql = "INSERT OR REPLACE INTO items(account,id,kind,provider_id,name,search,category_id,added,season,episode,parent_id,body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        db.compileStatement(sql).use { statement ->
            for (item in items) {
                statement.clearBindings()
                listOf(account,item.id,item.kind.key,item.providerId,item.name,fold(item.name),item.categoryId).forEachIndexed { index, value -> statement.bindString(index+1,value) }
                statement.bindLong(8,item.addedAt);statement.bindLong(9,item.season.toLong());statement.bindLong(10,item.episode.toLong())
                if(item.parentId == null)statement.bindNull(11) else statement.bindString(11,item.parentId)
                statement.bindString(12,item.toStoredJson().toString());statement.executeInsert()
            }
        }
    }

    fun replaceCatalog(account: String, kind: MediaKind, categories: List<Category>, items: List<MediaItem>) = transaction { db ->
        db.delete("items", "account=? AND kind=?", arrayOf(account,kind.key))
        db.delete("categories", "account=? AND kind=?", arrayOf(account,kind.key))
        for(category in categories) db.insertOrThrow("categories",null,values("account" to account,"id" to category.id,"kind" to kind.key,"name" to category.name))
        putItems(account,items,db)
        putCache(account,"catalog:${kind.key}","{}",db)
    }

    private val itemSelect = "SELECT i.body,f.item_id AS favorite_id,p.position AS p_position,p.duration AS p_duration,p.completed AS p_completed,p.updated_at AS p_updated FROM items i LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id LEFT JOIN progress p ON p.account=i.account AND p.item_id=i.id"
    fun items(account: String, where: String = "1", args: List<String> = emptyList(), order: String = "i.added DESC,i.name COLLATE NOCASE,i.id", limit: Int = 60, offset: Int = 0, checkCancelled: () -> Unit = {}): List<MediaItem> {
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
    fun item(account: String, id: String): MediaItem? = items(account,"i.id=?",listOf(id),limit=1).firstOrNull()
    fun count(account: String, where: String, args: List<String>): Int = readableDatabase.rawQuery("SELECT COUNT(*) FROM items i LEFT JOIN favorites f ON f.account=i.account AND f.item_id=i.id WHERE i.account=? AND ($where)",(listOf(account)+args).toTypedArray()).use { it.moveToFirst();it.getInt(0) }
    fun categories(account: String, kind: MediaKind): List<Category> = readableDatabase.rawQuery("SELECT id,name FROM categories WHERE account=? AND kind=? ORDER BY name COLLATE NOCASE",arrayOf(account,kind.key)).use { c -> buildList { while(c.moveToNext()) add(Category(c.getString(0),c.getString(1),kind)) } }
    fun putCache(account: String, key: String, data: String, db: SQLiteDatabase = writableDatabase) { db.insertWithOnConflict("cache_meta",null,values("account" to account,"key" to key,"data" to data,"updated" to System.currentTimeMillis()),SQLiteDatabase.CONFLICT_REPLACE) }
    fun cache(account: String, key: String): Pair<String,Long>? = readableDatabase.rawQuery("SELECT data,updated FROM cache_meta WHERE account=? AND key=?",arrayOf(account,key)).use { if(it.moveToFirst()) it.getString(0) to it.getLong(1) else null }
    fun favorite(account: String, item: MediaItem): Boolean {
        var selected=false
        transaction { db ->
            putItems(account,listOf(item),db)
            val removed=db.delete("favorites","account=? AND item_id=?",arrayOf(account,item.id))
            selected=removed==0
            if(selected)db.insertOrThrow("favorites",null,values("account" to account,"item_id" to item.id,"created_at" to nowIso()))
        }
        return selected
    }
    fun saveProgress(account: String, item: MediaItem, position: Double, duration: Double) = transaction { db ->
        val exists=db.rawQuery("SELECT 1 FROM items WHERE account=? AND id=?",arrayOf(account,item.id)).use { it.moveToFirst() }
        if(!exists)putItems(account,listOf(item),db)
        val total=duration.finiteOrZero().coerceAtLeast(0.0)
        val at=position.finiteOrZero().coerceAtLeast(0.0).let { if(total>0)it.coerceAtMost(total) else it }
        db.insertWithOnConflict("progress",null,values("account" to account,"item_id" to item.id,"position" to at,"duration" to total,"completed" to (total>0&&at/total>=.95),"updated_at" to nowIso()),SQLiteDatabase.CONFLICT_REPLACE)
    }
    fun trackPreference(account: String, itemId: String): TrackPreference = readableDatabase.rawQuery("SELECT data FROM native_track_preferences WHERE account=? AND item_id=?",arrayOf(account,itemId)).use {
        if(!it.moveToFirst())return@use TrackPreference()
        val json=JSONObject(it.getString(0))
        TrackPreference(if(json.isNull("audioId"))null else json.optInt("audioId"),if(json.isNull("subtitleId"))null else json.optInt("subtitleId"),json.optBoolean("subtitleOff",true))
    }
    fun saveTrackPreference(account: String, itemId: String, preference: TrackPreference) {
        val data=JSONObject().put("audioId",preference.audioId?:JSONObject.NULL).put("subtitleId",preference.subtitleId?:JSONObject.NULL).put("subtitleOff",preference.subtitleOff)
        writableDatabase.insertWithOnConflict("native_track_preferences",null,values("account" to account,"item_id" to itemId,"data" to data.toString(),"updated_at" to nowIso()),SQLiteDatabase.CONFLICT_REPLACE)
    }
    fun playlists(account: String): List<Playlist> = readableDatabase.rawQuery("SELECT p.id,p.name,COUNT(pi.item_id) FROM playlists p LEFT JOIN playlist_items pi ON pi.account=p.account AND pi.playlist_id=p.id WHERE p.account=? GROUP BY p.id ORDER BY p.created_at",arrayOf(account)).use { c -> buildList { while(c.moveToNext()) { val id=c.getString(0);add(Playlist(id,c.getString(1),c.getInt(2))) } } }
    fun playlistItems(account: String, id: String): List<MediaItem> = items(account,"i.id IN (SELECT item_id FROM playlist_items WHERE account=? AND playlist_id=?)",listOf(account,id),order="(SELECT position FROM playlist_items WHERE account=i.account AND playlist_id='${id.replace("'","''")}' AND item_id=i.id)",limit=20000)
    fun createPlaylist(account: String, name: String): Playlist {
        val clean=name.trim().take(100);if(clean.isEmpty())throw IptvException("Liste adı boş olamaz.")
        val id=UUID.randomUUID().toString()
        writableDatabase.insertOrThrow("playlists",null,values("account" to account,"id" to id,"name" to clean,"created_at" to nowIso()))
        return Playlist(id,clean,0)
    }
    fun addToPlaylist(account: String, playlistId: String, item: MediaItem) = transaction { db ->
        putItems(account,listOf(item),db)
        val position=db.rawQuery("SELECT COALESCE(MAX(position),-1)+1 FROM playlist_items WHERE account=? AND playlist_id=?",arrayOf(account,playlistId)).use { it.moveToFirst();it.getInt(0) }
        try { db.insertWithOnConflict("playlist_items",null,values("account" to account,"playlist_id" to playlistId,"item_id" to item.id,"position" to position),SQLiteDatabase.CONFLICT_IGNORE) }
        catch (_: android.database.sqlite.SQLiteConstraintException) { throw IptvException("Liste bulunamadı.") }
    }
    fun removeFromPlaylist(account: String, playlistId: String, itemId: String) { writableDatabase.delete("playlist_items","account=? AND playlist_id=? AND item_id=?",arrayOf(account,playlistId,itemId)) }
    fun deletePlaylist(account: String, playlistId: String) { writableDatabase.delete("playlists","account=? AND id=?",arrayOf(account,playlistId)) }
}
