# Stacktrace readability for release diagnostics
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# LibVLC native JNI classes, callbacks, and fields (libvlc-all AAR has no consumer proguard.txt)
-keep class org.videolan.** { *; }
-dontwarn org.videolan.**

# Entry points & ViewModel reflective instantiation (defense-in-depth alongside AndroidX consumer rules)
-keep class app.mavie.player.MainActivity
-keepclassmembers class app.mavie.player.MainViewModel {
    public <init>(android.app.Application);
}

# Okio JVM optional APIs (okio-jvm JAR ships no consumer proguard.txt)
-dontwarn java.nio.file.**
-dontwarn org.codehaus.mojo.animal_sniffer.*
-dontwarn okio.**

# Coil optional decoder/fetcher checks (coil AARs ship no consumer proguard.txt)
-dontwarn coil.**
