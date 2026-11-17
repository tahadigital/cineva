"""Local-only real FFmpeg/HLS fixture. Never loads a personal account."""
import sys,json,tempfile,subprocess,threading,signal,os,time
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
sys.path.insert(0,str(Path.cwd()))
from playback import PlaybackManager,find_ffmpeg
temporary=tempfile.TemporaryDirectory(prefix='akis-caption-browser-');root=Path(temporary.name);ff=find_ffmpeg()
def stamp(t):return f'{t//3600:02d}:{t//60%60:02d}:{t%60:02d},000'
cues=[0,4,8,12,16]+list(range(160,320,4))
(root/'en.srt').write_text('\n'.join(f'{i}\n{stamp(t)} --> {stamp(t+3)}\nCUE_{t}\n' for i,t in enumerate(cues,1)))
source=root/'fixture.mkv'
subprocess.run([ff,'-v','error','-f','lavfi','-i','color=navy:s=160x90:r=10:d=320','-f','lavfi','-i','sine=duration=320','-i',str(root/'en.srt'),'-map','0:v','-map','1:a','-map','2:s','-c:v','libx264','-preset','ultrafast','-g','20','-c:a','aac','-c:s','srt',str(source)],check=True,capture_output=True,timeout=40)
m=PlaybackManager(root/'sessions')
class H(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def send(self,b,typ='application/json',code=200):
  self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Content-Length',len(b));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  try:
   p=self.path.split('?')[0]
   if os.environ.get('AKIS_SUBTITLE_HTTP_LOG'):
    with open(os.environ['AKIS_SUBTITLE_HTTP_LOG'],'a') as log:log.write(json.dumps({'time':time.time(),'path':p})+'\n')
   if p=='/':return self.send(b'<video id="video" muted></video><select id="audioTrackSelect"></select><select id="subtitleTrackSelect"></select><div id="trackStatus"></div><button id="refreshTracks"></button>','text/html')
   if p=='/hls.js':return self.send(Path('public/vendor/hls.min.js').read_bytes(),'application/javascript')
   if p=='/tracks.js':return self.send(Path('public/tracks.js').read_bytes(),'application/javascript')
   _,_,sid,name=p.split('/');f=m.get_file(sid,name)
   body=f.read_bytes()
   return self.send(body,'text/vtt' if name.endswith('.vtt') else 'application/vnd.apple.mpegurl' if name.endswith('.m3u8') else 'video/mp2t')
  except Exception:return self.send(b'{}',code=404)
 def do_POST(self):
  try:
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
   if self.path=='/start':
    r=m.start(str(source),start=data.get('offset',0),subtitle_index=2,subtitle_codec='subrip',subtitle_language='eng')
    return self.send(json.dumps(r).encode())
   if self.path=='/ping':return self.send(json.dumps(m.ping(data['sid'],data['position'])).encode())
   if self.path=='/pause':m.pause(data['sid'],data['paused'])
   self.send(b'{}')
  except Exception:return self.send(b'{}',code=500)
server=ThreadingHTTPServer(('127.0.0.1',0),H)
print(server.server_port,flush=True)
def stop(*a):m.close();server.server_close();sys.exit(0)
signal.signal(signal.SIGTERM,stop)
try:server.serve_forever()
finally:m.close();temporary.cleanup()
