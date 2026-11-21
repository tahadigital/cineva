package app.mavie.player.data

import android.database.sqlite.SQLiteDatabase
import org.json.JSONArray
import org.json.JSONObject

/** Version 1 is deliberately compatible with Mavie Desktop /api/export. */
internal object StateBackup {
    private val idPattern=Regex("^(live|vod|series|episode):[A-Za-z0-9_-]{1,100}$")
    private val tableNames=linkedMapOf("favorites" to "favorites","progress" to "progress","playlists" to "playlists","playlistItems" to "playlist_items","trackPreferences" to "track_preferences","nativeTrackPreferences" to "native_track_preferences")
    fun export(database: LocalDatabase, account: String): String {
        val output=JSONObject().put("version",1).put("app","Mavie").put("exportedAt",nowIso())
        for((key,table) in tableNames) {
            val rows=JSONArray()
            database.readableDatabase.rawQuery("SELECT * FROM $table WHERE account=?",arrayOf(account)).use { cursor ->
                while(cursor.moveToNext()) {
                    val row=JSONObject()
                    for(index in 0 until cursor.columnCount) {
                        val name=cursor.getColumnName(index);if(name=="account")continue
                        when(cursor.getType(index)) {
                            android.database.Cursor.FIELD_TYPE_NULL -> row.put(name,JSONObject.NULL)
                            android.database.Cursor.FIELD_TYPE_INTEGER -> row.put(name,cursor.getLong(index))
                            android.database.Cursor.FIELD_TYPE_FLOAT -> row.put(name,cursor.getDouble(index))
                            else -> row.put(name,cursor.getString(index))
                        }
                    }
                    rows.put(row)
                }
            }
            output.put(key,rows)
        }
        val items=JSONArray()
        database.readableDatabase.rawQuery("SELECT i.body FROM items i WHERE i.account=? AND (EXISTS(SELECT 1 FROM progress p WHERE p.account=i.account AND p.item_id=i.id) OR EXISTS(SELECT 1 FROM favorites f WHERE f.account=i.account AND f.item_id=i.id) OR EXISTS(SELECT 1 FROM playlist_items pi WHERE pi.account=i.account AND pi.item_id=i.id)) ORDER BY i.id",arrayOf(account)).use { cursor ->
            while(cursor.moveToNext())items.put(JSONObject(cursor.getString(0)))
        }
        output.put("items",items)
        return output.toString(2)
    }

    fun import(database: LocalDatabase, account: String, json: String) {
        if(json.length>25*1024*1024)throw IptvException("Yedek dosyası 25 MB’tan küçük olmalı.")
        try {
            val input=JSONObject(json)
            require(input.optInt("version",0)==1)
            val arrays=tableNames.keys.associateWith { key ->
                if(!input.has(key))JSONArray() else input.getJSONArray(key).also { require(it.length()<=100000) }
            }
            val metadata=if(input.has("items")) input.getJSONArray("items") else JSONArray()
            require(metadata.length()<=100000)
            val items=objects(metadata).map { row -> storedItem(row).also {
                require(idPattern.matches(it.id)&&it.id=="${it.kind.key}:${it.providerId}")
                require(it.name.isNotBlank()&&it.name.length<=2000)
                require(it.poster.length<=5000&&it.backdrop.length<=5000&&it.plot.length<=20000)
            } }
            // Validate the entire document before beginning any mutation.
            val favorites=objects(arrays.getValue("favorites")).onEach { itemId(it);date(it,"created_at") }
            val progress=objects(arrays.getValue("progress")).onEach {
                itemId(it);require(it.has("position")&&it.has("duration"))
                require(it.getDouble("position").isFinite()&&it.getDouble("position")>=0)
                require(it.getDouble("duration").isFinite()&&it.getDouble("duration")>=0)
                date(it,"updated_at")
            }
            val playlists=objects(arrays.getValue("playlists")).onEach {
                shortId(it,"id");require(it.getString("name").isNotBlank()&&it.getString("name").length<=100);date(it,"created_at")
            }
            val playlistItems=objects(arrays.getValue("playlistItems")).onEach { shortId(it,"playlist_id");itemId(it);require(it.optInt("position",0)>=0) }
            val trackPreferences=objects(arrays.getValue("trackPreferences")).map { row ->
                itemId(row);date(row,"updated_at")
                val value=row.get("data");val data=if(value is JSONObject)value else JSONObject(value.toString())
                val allowed=mapOf("audio" to Regex("auto|stream:[0-9]{1,5}"),"subtitle" to Regex("off|stream:[0-9]{1,5}"),"clientAudio" to Regex("auto|(?:hls|native):[0-9]{1,5}"),"clientSubtitle" to Regex("off|(?:hls|native):[0-9]{1,5}"))
                for((key,pattern) in allowed)if(data.has(key)&&!data.isNull(key))require(pattern.matches(data.getString(key)))
                val clean=JSONObject()
                for(key in allowed.keys)if(data.has(key))clean.put(key,data.get(key))
                row to clean
            }
            val nativePreferences=objects(arrays.getValue("nativeTrackPreferences")).map { row ->
                itemId(row);date(row,"updated_at")
                val value=row.get("data");val data=if(value is JSONObject)value else JSONObject(value.toString())
                for(key in listOf("audioId","subtitleId"))if(data.has(key)&&!data.isNull(key)) {
                    val number=data.get(key);require(number is Number&&number.toDouble().isFinite()&&number.toDouble()==number.toInt().toDouble())
                }
                if(data.has("subtitleOff"))require(data.get("subtitleOff") is Boolean)
                val clean=JSONObject().put("audioId",if(data.isNull("audioId"))JSONObject.NULL else data.getInt("audioId"))
                    .put("subtitleId",if(data.isNull("subtitleId"))JSONObject.NULL else data.getInt("subtitleId")).put("subtitleOff",data.optBoolean("subtitleOff",true))
                row to clean
            }
            database.transaction { db ->
                val missing=items.filter { item -> db.rawQuery("SELECT 1 FROM items WHERE account=? AND id=?",arrayOf(account,item.id)).use { !it.moveToFirst() } }
                database.putItems(account,missing,db)
                for(row in favorites)db.insertWithOnConflict("favorites",null,values("account" to account,"item_id" to itemId(row),"created_at" to date(row,"created_at")),SQLiteDatabase.CONFLICT_IGNORE)
                for(row in progress) {
                    val item=itemId(row);val updated=date(row,"updated_at")
                    if(isNewer(db,"progress",account,item,updated)) {
                        val duration=row.getDouble("duration").coerceAtMost(7*86400.0)
                        val position=row.getDouble("position").coerceAtMost(if(duration>0)duration else 7*86400.0)
                        val complete=when(val value=row.opt("completed")) { is Boolean->value;is Number->value.toInt()!=0;else->false }
                        db.insertWithOnConflict("progress",null,values("account" to account,"item_id" to item,"position" to position,"duration" to duration,"completed" to complete,"updated_at" to updated),SQLiteDatabase.CONFLICT_REPLACE)
                    }
                }
                for(row in playlists)db.insertWithOnConflict("playlists",null,values("account" to account,"id" to shortId(row,"id"),"name" to row.getString("name"),"created_at" to date(row,"created_at")),SQLiteDatabase.CONFLICT_IGNORE)
                for(row in playlistItems) {
                    val list=shortId(row,"playlist_id")
                    val exists=db.rawQuery("SELECT 1 FROM playlists WHERE account=? AND id=?",arrayOf(account,list)).use { it.moveToFirst() }
                    if(exists)db.insertWithOnConflict("playlist_items",null,values("account" to account,"playlist_id" to list,"item_id" to itemId(row),"position" to row.optInt("position",0)),SQLiteDatabase.CONFLICT_IGNORE)
                }
                for((row,data) in trackPreferences) {
                    val item=itemId(row);val updated=date(row,"updated_at")
                    if(isNewer(db,"track_preferences",account,item,updated))db.insertWithOnConflict("track_preferences",null,values("account" to account,"item_id" to item,"data" to data.toString(),"updated_at" to updated),SQLiteDatabase.CONFLICT_REPLACE)
                }
                for((row,data) in nativePreferences) {
                    val item=itemId(row);val updated=date(row,"updated_at")
                    if(isNewer(db,"native_track_preferences",account,item,updated))db.insertWithOnConflict("native_track_preferences",null,values("account" to account,"item_id" to item,"data" to data.toString(),"updated_at" to updated),SQLiteDatabase.CONFLICT_REPLACE)
                }
            }
        } catch(error: IptvException) { throw error }
        catch(_: Exception) { throw IptvException("Yedek verileri geçersiz. Hiçbir değişiklik kaydedilmedi.") }
    }
    private fun objects(array: JSONArray): List<JSONObject> = List(array.length()) { array.getJSONObject(it) }
    private fun itemId(row: JSONObject): String = row.getString("item_id").also { require(idPattern.matches(it)) }
    private fun shortId(row: JSONObject, key: String): String = row.getString(key).also { require(it.isNotBlank()&&it.length<=200) }
    private fun date(row: JSONObject, key: String): String {
        if(!row.has(key)||row.isNull(key))return nowIso()
        return row.getString(key).also { require(it.length<=60&&timestamp(it)>0) }
    }
    private fun isNewer(db: SQLiteDatabase, table: String, account: String, item: String, updated: String): Boolean = db.rawQuery("SELECT updated_at FROM $table WHERE account=? AND item_id=?",arrayOf(account,item)).use {
        !it.moveToFirst()||timestamp(updated)>=timestamp(it.getString(0))
    }
}
