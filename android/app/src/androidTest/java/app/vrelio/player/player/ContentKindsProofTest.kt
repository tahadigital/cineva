package app.vrelio.player.player

import android.graphics.Bitmap
import android.os.SystemClock
import android.view.WindowManager
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.vrelio.player.MainActivity
import app.vrelio.player.data.*
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.videolan.libvlc.util.VLCVideoLayout
import java.io.File

@RunWith(AndroidJUnit4::class)
class ContentKindsProofTest {
    @Test(timeout=240_000) fun directLiveAndSeriesPlayback() {
        val instrumentation=InstrumentationRegistry.getInstrumentation()
        val context=instrumentation.targetContext
        val optIn=File(context.filesDir,"qa-content.optin")
        assumeTrue(optIn.exists());assertTrue(optIn.delete())
        val repository=VrelioRepository(context)
        assumeTrue(repository.account.value!=null)
        val proof=JSONObject().put("success",false)
        val directory=File(context.getExternalFilesDir(null),"proofs").apply { mkdirs() }
        var controller: NativePlaybackController?=null
        val scenario=ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.onActivity { it.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
            val series=runBlocking {
                repository.favorites(MediaKind.SERIES).firstOrNull { it.name.contains("Dexter",true) }
                    ?:repository.catalog(MediaKind.SERIES,query="Dexter").items.firstOrNull { it.name.equals("Dexter",true) }
                    ?:repository.catalog(MediaKind.SERIES,query="Dexter").items.first()
            }
            val detail=runBlocking { repository.detail(series) }
            assertTrue(detail.seasons.isNotEmpty())
            val season=detail.seasons.firstOrNull { it.number==1 }?:detail.seasons.first()
            val episode=season.episodes.getOrNull(1)?:season.episodes.first()
            proof.put("seriesSeasons",detail.seasons.size).put("firstSeasonEpisodes",season.episodes.size)
            fun open(item: MediaItem): NativePlaybackController {
                val source=repository.streamUrl(item)
                var created: NativePlaybackController?=null
                scenario.onActivity { activity ->
                    controller?.close()
                    val view=VLCVideoLayout(activity);activity.setContentView(view)
                    created=NativePlaybackController(activity,source,item.kind==MediaKind.LIVE,0,null,-1,{_,_->},{_,_->}).also { it.attach(view) }
                }
                controller=requireNotNull(created)
                return requireNotNull(created)
            }
            fun waitFor(player: NativePlaybackController,condition:(PlaybackSnapshot)->Boolean): PlaybackSnapshot {
                val deadline=SystemClock.elapsedRealtime()+70_000
                while(SystemClock.elapsedRealtime()<deadline) {
                    val state=player.state.value
                    assertNull("Native source must not fail.",state.error)
                    if(condition(state))return state
                    SystemClock.sleep(100)
                }
                fail("Native content did not start in time.");error("unreachable")
            }
            val episodePlayer=open(episode)
            val playing=waitFor(episodePlayer) { it.playing&&it.durationMs>60_000&&it.positionMs>2000&&it.seekable }
            proof.put("episodePlayed",true).put("episodeDurationMs",playing.durationMs).put("episodeAudioCount",playing.audioTracks.size)
            scenario.onActivity { episodePlayer.skipBy(10_000) }
            waitFor(episodePlayer) { it.playing&&it.positionMs>playing.positionMs+10_500 }
            proof.put("episodeSeekPassed",true)
            val live=runBlocking {
                repository.catalog(MediaKind.LIVE,query="TRT HABER",pageSize=30).items.sortedByDescending { it.name.contains("HD",true) }.first()
            }
            val livePlayer=open(live)
            waitFor(livePlayer) { it.playing&&!it.buffering }
            SystemClock.sleep(2200)
            assertTrue(livePlayer.state.value.playing)
            val image=instrumentation.uiAutomation.takeScreenshot()?:error("Live screenshot unavailable")
            try {
                File(directory,"Android-live.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG,95,it) }
                var count=0;var bright=0
                for(y in image.height*43/100 until image.height*57/100 step 8)for(x in image.width/4 until image.width*3/4 step 8) {
                    count++;val pixel=image.getPixel(x,y);if(android.graphics.Color.red(pixel)+android.graphics.Color.green(pixel)+android.graphics.Color.blue(pixel)>45)bright++
                }
                assertTrue("Live video must be visible.",bright>count/100)
                proof.put("liveVideoVisible",true)
            } finally { image.recycle() }
            proof.put("livePlayed",true).put("liveAudioCount",livePlayer.state.value.audioTracks.size).put("success",true)
        } finally {
            scenario.onActivity { controller?.close() };scenario.close()
            File(directory,"content-kinds-proof.json").writeText(proof.toString(2))
        }
    }
}
