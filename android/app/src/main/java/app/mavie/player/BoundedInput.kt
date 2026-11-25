package app.mavie.player

import app.mavie.player.data.IptvException
import app.mavie.player.data.MavieErrorCode
import java.io.ByteArrayOutputStream
import java.io.InputStream

/** Uses APIs present on Android8+, with a hard bound before JSON parsing. */
internal fun InputStream.readBounded(maximum: Int=25*1024*1024): ByteArray {
    val output=ByteArrayOutputStream()
    val buffer=ByteArray(32*1024)
    while(true) {
        val count=read(buffer)
        if(count<0)break
        if(output.size()+count>maximum)throw IptvException("Dosya çok büyük.", MavieErrorCode.PAYLOAD_TOO_LARGE)
        output.write(buffer,0,count)
    }
    return output.toByteArray()
}

internal fun InputStream.limitBytes(
    maximum: Long,
    errorMessage: String = "Dosya çok büyük.",
    errorCode: MavieErrorCode = MavieErrorCode.PAYLOAD_TOO_LARGE,
): InputStream = object : InputStream() {
    private var consumed = 0L

    private fun track(count: Int): Int {
        if (count > 0) {
            consumed += count
            if (consumed > maximum) throw IptvException(errorMessage, errorCode)
        }
        return count
    }

    override fun read(): Int = this@limitBytes.read().also { if (it >= 0) track(1) }

    override fun read(b: ByteArray, off: Int, len: Int): Int = track(this@limitBytes.read(b, off, len))

    override fun close() = this@limitBytes.close()
}
