package app.mavie.player.player

import android.app.KeyguardManager
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.PixelCopy
import android.view.SurfaceView
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.mavie.player.MainActivity
import okhttp3.mockwebserver.*
import okio.Buffer
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.runner.RunWith
import org.videolan.libvlc.util.VLCVideoLayout
import java.io.File
import java.net.InetAddress
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** PixelCopy reads only VLC's own subtitle surface, never the device screen. */
@RunWith(AndroidJUnit4::class)
class SubtitleContinuityTest {
 @get:Rule val rule=createAndroidComposeRule<MainActivity>()
 private val diagnostics=JSONObject()
 @Test(timeout=240_000) fun englishAssStaysVisibleAcrossSeekingPauseAndReconnect() {
  val context=InstrumentationRegistry.getInstrumentation().targetContext
  assumeTrue(!(context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isDeviceLocked)
  val fixture=InstrumentationRegistry.getInstrumentation().context.assets.open("subtitle-ass-qa.mkv").use{it.readBytes()}
  val proof=JSONObject().put("success",false)
  var player:NativePlaybackController?=null
  lateinit var layout:VLCVideoLayout
  val began=SystemClock.elapsedRealtime()
  MockWebServer().use{server->
   server.dispatcher=object:Dispatcher(){override fun dispatch(request:RecordedRequest):MockResponse {
    val range=request.getHeader("Range")?.let{Regex("bytes=(\\d+)-(\\d*)").matchEntire(it)}
    val start=range?.groupValues?.get(1)?.toIntOrNull()?:0
    val end=range?.groupValues?.get(2)?.toIntOrNull()?.coerceAtMost(fixture.lastIndex)?:fixture.lastIndex
    if(start !in 0..end)return MockResponse().setResponseCode(416)
    val response=MockResponse().setHeader("Content-Type","video/x-matroska").setHeader("Accept-Ranges","bytes").setHeader("Content-Length",end-start+1)
    if(request.method!="HEAD")response.setBody(Buffer().write(fixture,start,end-start+1))
    return if(range==null)response else response.setResponseCode(206).setHeader("Content-Range","bytes $start-$end/${fixture.size}")
   }}
   server.start(InetAddress.getByName("127.0.0.1"),0)
   val source="http://127.0.0.1:${server.port}/fixture.mkv"
   try {
    rule.runOnUiThread {
     rule.activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
     layout=VLCVideoLayout(rule.activity)
     rule.activity.setContentView(layout)
     player=NativePlaybackController(rule.activity,source,false,0,null,2,{_,_->},{_,_->})
     player!!.attach(layout)
    }
    val p=requireNotNull(player)
    await("English ASS track missing"){p.state.value.subtitleTracks.isNotEmpty()&&p.state.value.playing}
    val selected=p.state.value.subtitleTracks.first().id
    proof.put("nativeSubtitleId",selected)
    rule.runOnUiThread{p.selectSubtitle(selected)}
    proof.put("initialWhitePixels",awaitWhite(layout,p,0,9_500))
    rule.runOnUiThread{p.seekTo(12_000)}
    await("Silent point not reached"){p.state.value.positionMs in 12_000..13_500}
    val blank=whitePixels(layout);proof.put("silentWhitePixels",blank)
    assertTrue("Silent interval must not contain old subtitle pixels",blank<=30)
    rule.runOnUiThread{p.seekTo(162_000)}
    proof.put("afterGapWhitePixels",awaitWhite(layout,p,162_000,177_000))
    rule.runOnUiThread{p.togglePlaying()}
    await("Pause failed"){!p.state.value.playing}
    val paused=p.state.value.positionMs
    SystemClock.sleep(500)
    assertTrue(kotlin.math.abs(p.state.value.positionMs-paused)<800)
    rule.runOnUiThread{p.togglePlaying()}
    proof.put("afterPauseWhitePixels",awaitWhite(layout,p,162_000,179_000))
    rule.runOnUiThread{p.suspendPlayback()}
    SystemClock.sleep(400)
    rule.runOnUiThread{p.resumePlayback()}
    proof.put("afterReconnectWhitePixels",awaitWhite(layout,p,162_000,179_000))
    rule.runOnUiThread{p.seekTo(242_000)}
    proof.put("lateWhitePixels",awaitWhite(layout,p,242_000,258_000))
    rule.runOnUiThread{p.seekTo(15_000)}
    proof.put("afterRewindWhitePixels",awaitWhite(layout,p,15_000,18_900))
    assertEquals(selected,p.state.value.subtitleTrackId)
    proof.put("selectedTrackPreserved",true).put("success",true)
   }catch(e:Throwable){proof.put("failureType",e.javaClass.simpleName).put("diagnostics",diagnostics)
    player?.state?.value?.let{proof.put("lastPositionMs",it.positionMs).put("lastSubtitleId",it.subtitleTrackId).put("lastPlaying",it.playing)}
    throw e}
   finally {
    rule.runOnUiThread{player?.close()}
    rule.activityRule.scenario.close()
    val directory=File(context.getExternalFilesDir(null),"proofs").apply{mkdirs()}
    proof.put("elapsedSeconds",(SystemClock.elapsedRealtime()-began)/1000.0)
    File(directory,"subtitle-continuity-proof.json").writeText(proof.toString(2))
   }
  }
 }
 private fun await(reason:String,predicate:()->Boolean){
  val deadline=SystemClock.elapsedRealtime()+25_000
  while(SystemClock.elapsedRealtime()<deadline){if(predicate())return;SystemClock.sleep(100)}
  fail(reason)
 }
 private fun awaitWhite(layout:VLCVideoLayout,p:NativePlaybackController,min:Long,max:Long):Int {
  var pixels=0
  await("Selected English ASS did not render in $min..$max; current=${p.state.value.positionMs}"){
   if(p.state.value.playing&&p.state.value.positionMs in min..max){pixels=whitePixels(layout);pixels>30}else false
  };return pixels
 }
 private fun whitePixels(layout:VLCVideoLayout):Int {
  val surfaces=mutableListOf<SurfaceView>()
  fun visit(v:View){
   if(v is SurfaceView)surfaces.add(v)
   if(v is ViewGroup)for(i in 0 until v.childCount)visit(v.getChildAt(i))
  }
  rule.runOnUiThread{visit(layout)}
  var maximum=0
  for(view in surfaces){
  val name=runCatching{view.resources.getResourceEntryName(view.id)}.getOrDefault("unknown")
  diagnostics.put("surface-$name","${view.width}x${view.height} valid=${view.holder.surface.isValid}")
  if(view.width<2||view.height<2||!view.holder.surface.isValid)continue
  val bitmap=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
  val latch=CountDownLatch(1);var result=-1
  PixelCopy.request(view,bitmap,{result=it;latch.countDown()},Handler(Looper.getMainLooper()))
  try {
   if(!latch.await(3,TimeUnit.SECONDS)||result!=PixelCopy.SUCCESS){diagnostics.put("copy-$name",result);continue}
   var white=0
   for(y in 0 until bitmap.height step 2)for(x in 0 until bitmap.width step 2){val c=bitmap.getPixel(x,y);if(Color.alpha(c)>100&&Color.red(c)>180&&Color.green(c)>180&&Color.blue(c)>180)white++}
   diagnostics.put("white-$name",white)
   maximum=maxOf(maximum,white)
  }finally{bitmap.recycle()}
  }
  return maximum
 }
}
