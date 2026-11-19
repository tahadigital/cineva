package app.vrelio.player.qa

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView

/** Test APK only: keeps the already-unlocked device awake between playback probes. */
class SubtitleTestHoldingActivity:Activity(){
 override fun onCreate(state:Bundle?){
  super.onCreate(state)
  window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
  setContentView(TextView(this).apply{text="Vrelio altyazı testi hazırlanıyor…";gravity=Gravity.CENTER;textSize=22f})
 }
}
