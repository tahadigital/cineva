package app.mavie.player.data

import android.util.JsonReader
import android.util.JsonToken
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.io.InputStreamReader
import java.io.PushbackReader

/** Parse large provider catalogs without retaining a second raw byte/string copy. */
internal fun readProviderJson(input: InputStream, byteLimit: Long=100*1024*1024L): Any {
    val bounded=object : InputStream() {
        var consumed=0L
        private fun counted(count: Int): Int {
            if(count>0){consumed+=count;if(consumed>byteLimit)throw IptvException("Sağlayıcının listesi bu cihaz için çok büyük.", MavieErrorCode.PAYLOAD_TOO_LARGE)}
            return count
        }
        override fun read(): Int = input.read().also { if(it>=0)counted(1) }
        override fun read(buffer: ByteArray, offset: Int, length: Int): Int = counted(input.read(buffer,offset,length))
        override fun close() { input.close() }
    }
    val characters=PushbackReader(InputStreamReader(bounded,Charsets.UTF_8),1)
    val first=characters.read()
    if(first>=0&&first!=0xFEFF)characters.unread(first)
    return JsonReader(characters).use { reader ->
        var values=0
        fun value(depth: Int): Any {
            if(depth>64||++values>10_000_000)throw IptvException("Sağlayıcının yanıtı işlenemedi.", MavieErrorCode.INVALID_RESPONSE)
            return when(reader.peek()) {
                JsonToken.BEGIN_OBJECT -> {
                    val objectValue=JSONObject();reader.beginObject()
                    while(reader.hasNext())objectValue.put(reader.nextName(),value(depth+1))
                    reader.endObject();objectValue
                }
                JsonToken.BEGIN_ARRAY -> {
                    val array=JSONArray();reader.beginArray()
                    while(reader.hasNext())array.put(value(depth+1))
                    reader.endArray();array
                }
                JsonToken.STRING -> reader.nextString()
                JsonToken.NUMBER -> {
                    val number=reader.nextString()
                    number.toLongOrNull()?:number.toDoubleOrNull()?.takeIf { it.isFinite() }?:throw IptvException("Sağlayıcının yanıtı geçersiz sayılar içeriyor.", MavieErrorCode.INVALID_RESPONSE)
                }
                JsonToken.BOOLEAN -> reader.nextBoolean()
                JsonToken.NULL -> {reader.nextNull();JSONObject.NULL}
                else -> throw IptvException("Sağlayıcı geçerli bir kütüphane göndermedi.", MavieErrorCode.INVALID_RESPONSE)
            }
        }
        value(0).also {
            if(it !is JSONObject&&it !is JSONArray)throw IptvException("Sağlayıcı geçerli bir kütüphane göndermedi.", MavieErrorCode.INVALID_RESPONSE)
            if(reader.peek()!=JsonToken.END_DOCUMENT)throw IptvException("Sağlayıcı geçerli bir yanıt göndermedi.", MavieErrorCode.INVALID_RESPONSE)
        }
    }
}
