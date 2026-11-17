"""Track discovery, language switching and WebVTT tested with local media only."""
import array
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from http.client import HTTPConnection
from unittest.mock import patch
import test_codec_playback as codec_fixture
from playback import PlaybackManager, find_ffmpeg, parse_tracks

class TrackAPITests(unittest.TestCase):
    setUpClass = classmethod(codec_fixture.CodecPlaybackTests.setUpClass.__func__)
    tearDownClass = classmethod(codec_fixture.CodecPlaybackTests.tearDownClass.__func__)
    setUp = codec_fixture.CodecPlaybackTests.setUp
    tearDown = codec_fixture.CodecPlaybackTests.tearDown
    @staticmethod
    def started_playback(_source, **kwargs):
        return {'sessionId':'a'*32,'url':'/media/fixture/index.m3u8','type':'hls','startOffset':kwargs.get('start',0),'duration':kwargs.get('duration')}
    episode = codec_fixture.CodecPlaybackTests.episode
    request_play = codec_fixture.CodecPlaybackTests.request_play

    def tracks(self):
        data={'scanned':True,'audio':[{'id':'stream:1','index':1,'language':'tur','default':True,'codec':'aac'},{'id':'stream:2','index':2,'language':'eng','codec':'aac'}],
              'subtitles':[{'id':'stream:3','index':3,'language':'tur','codec':'subrip','bitmap':False},{'id':'stream:4','index':4,'language':'eng','codec':'ass','bitmap':False}]}
        self.app.playback.probe.return_value=data
        return data

    def request(self, path, method='GET', data=None):
        c=HTTPConnection('127.0.0.1',self.http.server_port,timeout=10)
        try:
            c.request(method,path,json.dumps(data) if data is not None else None,{'Content-Type':'application/json','Cookie':'akis_device=codec-device'})
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()

    def test_track_selection_is_validated_cached_and_shared_per_content(self):
        self.tracks();iid=self.episode('h264','yuv420p')
        code,data=self.request('/api/play','POST',{'id':iid,'mode':'remux','audioTrack':'stream:2','subtitleTrack':'stream:4','start':125})
        self.assertEqual(code,200);self.assertEqual(data['selection']['audio'],'stream:2')
        kwargs=self.app.playback.start.call_args.kwargs
        self.assertEqual(kwargs['audio_index'],2);self.assertEqual(kwargs['subtitle_index'],4);self.assertEqual(kwargs['start'],125)
        self.assertEqual(kwargs['subtitle_codec'],'ass')
        code,cached=self.request('/api/tracks/'+iid)
        self.assertEqual(code,200);self.assertEqual(cached['selection']['subtitle'],'stream:4');self.assertEqual(len(cached['tracks']['audio']),2)
        self.request_play(iid);self.assertEqual(self.app.playback.probe.call_count,1)
        self.assertEqual(self.app.playback.start.call_args.kwargs['audio_index'],2)
        code,backup=self.request('/api/export');self.assertEqual(len(backup['trackPreferences']),1)
        with self.app.connect() as c:c.execute('DELETE FROM track_preferences')
        self.assertEqual(self.request('/api/import','POST',{'data':backup})[0],200)
        self.assertEqual(self.app.track_preferences(iid)['subtitle'],'stream:4')

    def test_direct_selection_upgrades_and_subtitles_can_be_turned_off(self):
        self.tracks();iid=self.episode('h264','yuv420p')
        code,data=self.request('/api/play','POST',{'id':iid,'mode':'direct','subtitleTrack':'stream:3'})
        self.assertEqual((code,data['mode']),(200,'remux'))
        code,data=self.request('/api/play','POST',{'id':iid,'mode':'remux','subtitleTrack':'off'})
        self.assertEqual(code,200);self.assertNotIn('subtitle_index',self.app.playback.start.call_args.kwargs)

    def test_bitmap_caption_requires_transcode_and_invalid_track_is_rejected(self):
        data=self.tracks();data['subtitles'][0].update(codec='hdmv_pgs_subtitle',bitmap=True)
        iid=self.episode('h264','yuv420p')
        code,result=self.request('/api/play','POST',{'id':iid,'mode':'remux','subtitleTrack':'stream:3'})
        self.assertEqual((code,result['mode']),(200,'transcode'))
        code,_=self.request('/api/play','POST',{'id':iid,'mode':'remux','audioTrack':'stream:99'})
        self.assertEqual(code,400)
        self.assertEqual(self.request('/api/play','POST',{'id':iid,'mode':'remux','audioTrack':'../secret'})[0],400)

    def test_browser_track_preferences_and_backup_validation(self):
        iid=self.episode('h264','yuv420p')
        code,pref=self.request('/api/track-preferences','POST',{'id':iid,'clientAudio':'hls:1','clientSubtitle':'off'})
        self.assertEqual(code,200);self.assertEqual(pref['selection']['clientAudio'],'hls:1')
        self.assertEqual(self.request('/api/track-preferences','POST',{'id':iid,'clientAudio':'<script>'})[0],400)
        backup={'version':1,'trackPreferences':[{'item_id':iid,'data':'{"audio":"stream:2;rm"}'}]}
        self.assertEqual(self.request('/api/import','POST',{'data':backup})[0],400)
        self.assertEqual(self.app.track_preferences(iid)['clientAudio'],'hls:1')

class TrackMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg=find_ffmpeg()
        if not cls.ffmpeg:raise unittest.SkipTest('FFmpeg missing')
        cls.temp=tempfile.TemporaryDirectory(prefix='akis-multitrack-');cls.root=Path(cls.temp.name)
        for name,text in [('tr','Türkçe altyazı denemesi'),('en','English subtitle fixture')]:
            (cls.root/(name+'.srt')).write_text('\n'.join(f'{i+1}\n00:00:{sec:02d},000 --> 00:00:{sec+2:02d},000\n{text} {i+1}\n' for i,sec in enumerate(range(0,33,3))),encoding='utf-8')
        cls.file=cls.root/'fixture.mkv'
        command=[cls.ffmpeg,'-v','error','-f','lavfi','-i','color=navy:s=320x180:r=24:d=35','-f','lavfi','-i','sine=frequency=440:duration=35','-f','lavfi','-i','sine=frequency=880:duration=35',
                 '-i',str(cls.root/'tr.srt'),'-i',str(cls.root/'en.srt'),'-map','0:v','-map','1:a','-map','2:a','-map','3:s','-map','4:s','-c:v','libx264','-g','48','-c:a','aac','-c:s','srt',
                 '-metadata:s:a:0','language=tur','-metadata:s:a:0','title=Türkçe Dublaj','-metadata:s:a:1','language=eng','-metadata:s:s:0','language=tur','-metadata:s:s:1','language=eng','-t','35',str(cls.file)]
        subprocess.run(command,capture_output=True,check=True,timeout=30)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_probe_exposes_both_audio_languages_and_both_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=PlaybackManager(Path(tmp))
            try:
                tracks=manager.probe(str(self.file))
                self.assertEqual([x['language'] for x in tracks['audio']],['tur','eng'])
                self.assertEqual([x['id'] for x in tracks['subtitles']],['stream:3','stream:4'])
                self.assertEqual(tracks['audio'][0]['title'],'Türkçe Dublaj')
            finally:manager.close()

    def test_selected_audio_is_encoded_and_selected_subtitles_are_valid_webvtt(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=PlaybackManager(Path(tmp))
            try:
                result=manager.start(str(self.file),audio_index=2,subtitle_index=4,subtitle_codec='subrip',subtitle_name='English',subtitle_language='eng')
                sid=result['sessionId'];master=manager.get_file(sid,'master.m3u8').read_text()
                self.assertIn('TYPE=SUBTITLES',master);self.assertIn('index_vtt.m3u8',master)
                self.assertIn('English subtitle fixture',manager.get_file(sid,'index0.vtt').read_text())
                self.assertNotIn('Türkçe',manager.get_file(sid,'index0.vtt').read_text())
                segment=manager.get_file(sid,'seg_000000000.ts')
                pcm=subprocess.run([self.ffmpeg,'-v','error','-i',str(segment),'-map','0:a:0','-t','1','-ac','1','-ar','8000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=15).stdout
                samples=array.array('f',pcm);crossings=sum(a<=0<b for a,b in zip(samples,samples[1:]));frequency=crossings/(len(samples)/8000)
                self.assertAlmostEqual(frequency,880,delta=20)
                manager.stop(sid)
                result=manager.start(str(self.file),start=4,audio_index=1,subtitle_index=3,subtitle_codec='subrip')
                self.assertEqual(result['startOffset'],4)
                self.assertTrue(any('Türkçe altyazı' in v.read_text() for v in manager.get_file(result['sessionId'],'index_vtt.m3u8').parent.glob('*.vtt')))
                with self.assertRaises(FileNotFoundError):manager.get_file(result['sessionId'],'../config.json')
            finally:manager.close()

    def test_probe_parser_handles_transport_pids_flags_and_styled_subtitles(self):
        data=parse_tracks('Stream #0:2[0x111](tur): Audio: ac3, 48000 Hz, 5.1(side), fltp (default)\n Metadata:\n title : Dublaj\n Stream #0:8[0x112](eng): Subtitle: ass (forced)\n')
        self.assertEqual(data['audio'][0]['index'],2);self.assertTrue(data['subtitles'][0]['forced'])
        self.assertEqual(data['subtitles'][0]['codec'],'ass')

    def test_webvtt_and_video_share_a_clock_after_seek_and_transcode(self):
        # Inspect actual MPEG-TS PTS, not the decoder's rebased time. The
        # previous mux command added 1.4 seconds only to audio/video.
        with tempfile.TemporaryDirectory() as tmp:
            manager = PlaybackManager(Path(tmp))
            try:
                for mode in ('remux', 'transcode'):
                    for offset in (0, 4, 18):
                        with self.subTest(mode=mode, offset=offset):
                            result = manager.start(str(self.file), mode=mode, start=offset,
                                subtitle_index=4, subtitle_codec='subrip')
                            segment = manager.get_file(result['sessionId'], 'seg_000000000.ts')
                            decoded = subprocess.run([self.ffmpeg, '-hide_banner', '-copyts',
                                '-i', str(segment), '-vf', 'showinfo', '-frames:v', '1',
                                '-f', 'null', '-'], capture_output=True, text=True,
                                check=True, timeout=15)
                            match = re.search(r'pts_time:([0-9.]+)', decoded.stderr)
                            self.assertIsNotNone(match)
                            # At 4 s the still-active 3--5 s subtitle is
                            # retained as preroll; transcoded video starts
                            # one second after that shared timeline origin.
                            expected = 1.0 if mode == 'transcode' and offset == 4 else 0.0
                            self.assertAlmostEqual(float(match[1]), expected, delta=.2,
                                msg='Video must not have the TS-only 1.4 s delay absent from WebVTT')
            finally:
                manager.close()

    def test_english_cues_survive_silent_gaps_and_rolling_cache_after_seek(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def stamp(t):
                return f'{t // 3600:02d}:{t // 60 % 60:02d}:{t % 60:02d},000'
            subtitle = root / 'english.srt'
            subtitle.write_text('\n'.join(
                f'{i}\n{stamp(t)} --> {stamp(t + 3)}\nEnglish cue {t}\n'
                for i, t in enumerate([0, 20, 160, 220, 300], 1)))
            source = root / 'long.mkv'
            subprocess.run([self.ffmpeg, '-v', 'error', '-f', 'lavfi', '-i',
                'color=navy:s=160x90:r=10:d=320', '-f', 'lavfi', '-i',
                'sine=duration=320', '-i', str(subtitle), '-map', '0:v',
                '-map', '1:a', '-map', '2:s', '-c:v', 'libx264', '-preset',
                'ultrafast', '-g', '20', '-c:a', 'aac', '-c:s', 'srt', str(source)],
                capture_output=True, check=True, timeout=40)
            manager = PlaybackManager(root / 'sessions')
            try:
                # Generate past the 128-second rolling window without a
                # wall-clock wait. This tests packaging, not browser rendering.
                for offset in (0, 170):
                    output = root / f'out-{offset}'
                    output.mkdir()
                    subprocess.run(manager._command(str(source), output, 'remux',
                        offset, False, None, 2, 'subrip'), capture_output=True,
                        check=True, timeout=40)
                    video = (output / 'index.m3u8').read_text()
                    captions = (output / 'index_vtt.m3u8').read_text()
                    sequence = re.search(r'MEDIA-SEQUENCE:(\d+)', video)[1]
                    self.assertGreater(int(sequence), 0)
                    self.assertEqual(sequence, re.search(r'MEDIA-SEQUENCE:(\d+)', captions)[1])
                    files = [output / line for line in captions.splitlines()
                             if line and not line.startswith('#')]
                    self.assertTrue(all(path.is_file() for path in files))
                    self.assertTrue(any('English cue 300' in path.read_text() for path in files))
            finally:
                manager.close()
