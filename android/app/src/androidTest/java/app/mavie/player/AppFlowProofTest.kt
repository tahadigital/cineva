package app.mavie.player

import android.app.KeyguardManager
import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import android.view.WindowManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.mavie.player.data.MavieRepository
import app.mavie.player.data.LocalDatabase
import app.mavie.player.data.values
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/** End-to-end user flow on a provisioned phone, without any Mac service. */
@RunWith(AndroidJUnit4::class)
class AppFlowProofTest {
    @get:Rule val rule=createAndroidComposeRule<MainActivity>()
    @Test fun librarySearchDetailAndNativePlayback() {
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        assumeTrue(!(context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isDeviceLocked)
        val repository=MavieRepository(context)
        val account=repository.account.value
        assumeTrue(account!=null)
        val movie=runBlocking { repository.item("vod:1774083") }
        assumeTrue(movie!=null)
        val item=requireNotNull(movie)
        val accountId=requireNotNull(account).id
        val database=LocalDatabase(context)
        val snapshots=listOf("progress","native_track_preferences").associateWith { table ->
            database.readableDatabase.rawQuery("SELECT * FROM $table WHERE account=? AND item_id=?",arrayOf(accountId,item.id)).use { c ->
                if(!c.moveToFirst())null else JSONObject().apply { for(i in 0 until c.columnCount)put(c.getColumnName(i),c.getString(i)) }
            }
        }
        val directory=File(context.getExternalFilesDir(null),"proofs").apply { mkdirs() }
        val proof=JSONObject().put("success",false)
        fun capture(name: String) {
            val image=instrumentation.uiAutomation.takeScreenshot()?:error("App screenshot unavailable")
            File(directory,name).outputStream().use { image.compress(Bitmap.CompressFormat.PNG,95,it) };image.recycle()
        }
        try {
            rule.runOnUiThread { rule.activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
            rule.waitUntil(120_000) { rule.onAllNodesWithText("Ana Sayfa").fetchSemanticsNodes().isNotEmpty() }
            SystemClock.sleep(1200)
            capture("Android-home.png")
            rule.onNodeWithText("Ara").performClick()
            rule.onAllNodes(hasSetTextAction()).onFirst().performTextInput("Interstellar")
            rule.waitUntil(30_000) { rule.onAllNodesWithContentDescription(item.name).fetchSemanticsNodes().isNotEmpty() }
            capture("Android-search.png")
            rule.onAllNodesWithContentDescription(item.name).onFirst().performClick()
            rule.waitUntil(30_000) { rule.onAllNodes(hasText("Devam et",substring=true) or hasText("İzlemeye başla")).fetchSemanticsNodes().isNotEmpty() }
            capture("Android-detail.png")
            rule.onAllNodes(hasText("Devam et",substring=true) or hasText("İzlemeye başla")).onFirst().performClick()
            rule.waitUntil(90_000) { rule.onAllNodesWithContentDescription("Duraklat").fetchSemanticsNodes().isNotEmpty() }
            rule.onAllNodesWithContentDescription("İçerikte ileri geri sar").assertCountEquals(1)
            rule.onNodeWithContentDescription("10 saniye ileri sar").assertIsEnabled().performClick()
            SystemClock.sleep(1200)
            rule.onNodeWithContentDescription("10 saniye geri sar").assertIsEnabled().performClick()
            capture("Android-player.png")
            rule.onNodeWithText("Ses").performClick()
            rule.onNodeWithText("Seslendirme ve ses dili").assertExists()
            capture("Android-audio.png")
            rule.onNodeWithText("Kapat").performClick()
            rule.onNodeWithText("Altyazı").performClick()
            rule.onNodeWithText("Kapalı").assertExists()
            capture("Android-subtitles.png")
            rule.onNodeWithText("Kapat").performClick()
            rule.onNodeWithContentDescription("Oynatıcıdan çık").performClick()
            proof.put("success",true).put("libraryRendered",true).put("searchWorked",true).put("detailOpened",true)
                .put("nativePlayerOpened",true).put("seekControlsEnabled",true).put("trackDialogsOpened",true)
        } finally {
            rule.activityRule.scenario.close()
            database.transaction { db ->
                for((table,row) in snapshots) {
                    db.delete(table,"account=? AND item_id=?",arrayOf(accountId,item.id))
                    if(row!=null)db.insertOrThrow(table,null,values(*row.keys().asSequence().map { it to row.getString(it) }.toList().toTypedArray()))
                }
            }
            database.close()
            File(directory,"app-flow-proof.json").writeText(proof.toString(2))
        }
    }
}
