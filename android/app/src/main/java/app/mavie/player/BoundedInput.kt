package app.mavie.player

import app.mavie.player.data.IptvException
import java.io.ByteArrayOutputStream
import java.io.InputStream

/** Uses APIs present on Android8+, with a hard bound before JSON parsing. */
internal fun InputStream.readBounded(maximum: Int=25*1024*1024): ByteArray {
    val output=ByteArrayOutputStream()
    val buffer=ByteArray(32*1024)
    while(true) {
        val count=read(buffer)
        if(count<0)break
        if(output.size()+count>maximum)throw IptvException("Dosya çok büyük.")
        output.write(buffer,0,count)
    }
    return output.toByteArray()
}
