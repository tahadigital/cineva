"""Bounded, private FFmpeg playback sessions for the local IPTV server.

Only opaque local source URLs should be passed to this module. FFmpeg receives
those URLs on its command line, but provider credentials never enter manifests,
segment names, or diagnostic output.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass


_SESSION_ID = re.compile(r"[a-f0-9]{32}\Z")
_MEDIA_FILE = re.compile(r"(?:(?:master|index|index_vtt)\.m3u8|index[0-9]+\.vtt|seg_[0-9]{9,}\.ts)\Z")


BITMAP_SUBTITLES = frozenset({'hdmv_pgs_subtitle', 'pgssub', 'dvd_subtitle', 'dvdsub', 'dvb_subtitle', 'dvbsub', 'xsub'})


def parse_tracks(diagnostic: str) -> dict:
    """Read input stream metadata from the bundled FFmpeg (no ffprobe needed)."""
    result = {'audio': [], 'subtitles': [], 'scanned': False}
    duration = re.search(r'^\s*Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?),', diagnostic, re.M)
    if duration:
        hours, minutes, seconds = map(float, duration.groups())
        result['duration'] = hours * 3600 + minutes * 60 + seconds
    current = None
    for line in diagnostic.splitlines():
        if re.match(r'\s*Stream #', line):
            current = None
            video_match = re.match(r'\s*Stream #0:\d+(?:\[[^\]]+\])?(?:\(([^)]+)\))?: Video: ([\w]+)(.*)', line)
            if video_match:
                result['scanned'] = True
                result.setdefault('videoCodec', video_match[2].lower())
                pix = re.search(r'\b(yuv[a-z0-9]+|nv12|nv21|rgb[a-z0-9]*|bgr[a-z0-9]*|gbrp[a-z0-9]*|gray[a-z0-9]*)\b', video_match[3])
                if pix:
                    result.setdefault('pixelFormat', pix[1].lower())
                continue
            match = re.match(r'\s*Stream #0:(\d+)(?:\[[^\]]+\])?(?:\(([^)]+)\))?: (Audio|Subtitle): ([\w]+)(.*)', line)
            if not match:
                continue
            idx, lang, kind, codec, extra = match.groups()
            current = {'id': f'stream:{idx}', 'index': int(idx), 'language': (lang or 'und').lower(),
                       'codec': codec.lower(), 'title': '', 'default': '(default)' in extra,
                       'forced': '(forced)' in extra, 'hearingImpaired': '(hearing impaired)' in extra}
            if kind == 'Audio':
                channels = re.search(r'\b(mono|stereo|[257]\.1(?:\([^)]+\))?)\b', extra)
                current['channels'] = channels.group(0) if channels else ''
            else:
                current['bitmap'] = codec.lower() in BITMAP_SUBTITLES
            result['audio' if kind == 'Audio' else 'subtitles'].append(current)
            result['scanned'] = True
        elif current:
            title = re.match(r'\s*title\s*:\s*(.*)', line, re.I)
            if title:
                current['title'] = title[1].strip()[:180]
    # A valid video-only source still has a complete (empty) track list.
    if re.search(r'Stream #0:\d+.*: Video:', diagnostic):
        result['scanned'] = True
    return result


@dataclass
class _Session:
    session_id: str
    directory: Path
    process: subprocess.Popen
    last_used: float
    paused: bool = False
    live: bool = False
    flow_paused: bool = False
    process_paused: bool = False
    position: float = 0.0
    cache_start: float = 0.0
    cache_end: float = 0.0
    last_sequence: int = -1


def _executable(candidate: str | Path | None) -> str | None:
    if not candidate:
        return None
    value = os.fspath(candidate)
    found = shutil.which(value)
    if found and Path(found).is_file():
        return str(Path(found).resolve())
    return None


def find_ffmpeg(explicit: str | None = None) -> str | None:
    """Find an installed FFmpeg, including an optional imageio wheel binary."""
    candidates: list[str | Path | None] = [
        explicit,
        os.environ.get("FFMPEG_PATH"),
        os.environ.get("IMAGEIO_FFMPEG_EXE"),
        "ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]
    try:
        spec = importlib.util.find_spec("imageio_ffmpeg")
        if spec and spec.submodule_search_locations:
            for location in spec.submodule_search_locations:
                candidates.extend(sorted((Path(location) / "binaries").glob("ffmpeg-*")))
    except (ImportError, ValueError, OSError):
        pass
    project = Path(__file__).resolve().parent
    candidates.extend(sorted(project.glob(".venv/lib/python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*")))
    for candidate in candidates:
        resolved = _executable(candidate)
        if resolved:
            return resolved
    return None


class PlaybackManager:
    """Manage one upstream playback connection with a small rolling HLS cache.

    Starting a new title ends the previous session, including across devices.
    Seek by starting another session with the desired absolute start offset.
    ``duration`` describes the complete title; it does not limit playback.
    """

    IDLE_TIMEOUT = 65.0
    START_TIMEOUT = 25.0
    REAPER_INTERVAL = 5.0
    PREFETCH_SECONDS = 60.0
    PREFETCH_RESUME_SECONDS = 35.0
    BUFFER_INTERVAL = 0.1

    def __init__(self, data_dir: Path, ffmpeg_path: str | None = None):
        self._ffmpeg_hint = ffmpeg_path
        self._ffmpeg = find_ffmpeg(ffmpeg_path)
        self._directory = Path(data_dir) / "playback"
        self._directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._directory.chmod(0o700)
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._closed = False
        self._shutdown = threading.Event()
        self._active = threading.Event()
        # Only remove our generated runtime directories, never arbitrary files.
        for child in self._directory.iterdir():
            if _SESSION_ID.fullmatch(child.name):
                self._remove_directory(child)
        self._reaper = threading.Thread(target=self._reap, name="iptv-playback-reaper", daemon=True)
        self._reaper.start()
        self._buffer = threading.Thread(target=self._buffer_loop, name="iptv-playback-buffer", daemon=True)
        self._buffer.start()

    @property
    def available(self) -> bool:
        # A first-run installer may finish after the server has been created.
        if not self._ffmpeg:
            self._ffmpeg = find_ffmpeg(self._ffmpeg_hint)
        return self._ffmpeg is not None

    def start(
        self,
        source_url: str,
        mode: str = "remux",
        start: float = 0,
        duration: float | None = None,
        live: bool = False,
        audio_index: int | None = None,
        subtitle_index: int | None = None,
        subtitle_codec: str = "",
        subtitle_name: str = "Altyazı",
        subtitle_language: str = "und",
    ) -> dict:
        if mode not in {"remux", "transcode"}:
            raise ValueError("Geçersiz oynatma modu.")
        try:
            offset = float(start)
            total = float(duration) if duration is not None else None
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Geçersiz oynatma zamanı.") from None
        if not math.isfinite(offset) or offset < 0:
            raise ValueError("Geçersiz oynatma zamanı.")
        if total is not None and (not math.isfinite(total) or total <= 0):
            total = None
        if live:
            offset = 0.0
        if not isinstance(source_url, str) or not source_url:
            raise ValueError("Oynatma kaynağı bulunamadı.")
        if not self.available:
            raise RuntimeError("Oynatma bileşeni bulunamadı. Kurulum dosyasını yeniden çalıştırın.")

        with self._start_lock:
            with self._lock:
                if self._closed:
                    raise RuntimeError("Oynatıcı kapatıldı.")
                old_ids = list(self._sessions)
            # The provider permits one connection. Release it before opening another.
            for session_id in old_ids:
                self.stop(session_id)

            session_id = uuid.uuid4().hex
            directory = self._directory / session_id
            directory.mkdir(mode=0o700)
            for value in (audio_index, subtitle_index):
                if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10000):
                    self._remove_directory(directory)
                    raise ValueError("Geçersiz ses veya altyazı parçası.")
            bitmap = subtitle_index is not None and subtitle_codec in BITMAP_SUBTITLES
            if bitmap:
                mode = 'transcode'
            command = self._command(source_url, directory, mode, offset, live, audio_index, subtitle_index, subtitle_codec)
            text_subtitle = subtitle_index is not None and not bitmap
            if text_subtitle:
                name = str(subtitle_name).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')[:180]
                language = subtitle_language if re.fullmatch(r'[a-zA-Z]{2,3}', subtitle_language) else 'und'
                (directory / 'master.m3u8').write_text('#EXTM3U\n#EXT-X-VERSION:3\n'
                    + f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{name}",LANGUAGE="{language}",DEFAULT=YES,AUTOSELECT=YES,FORCED=NO,URI="index_vtt.m3u8"\n'
                    + '#EXT-X-STREAM-INF:BANDWIDTH=12000000,SUBTITLES="subs"\nindex.m3u8\n', encoding='utf-8')
            try:
                # Only opaque localhost URLs enter FFmpeg. Keep a private
                # per-session diagnostic so premature input endings can be
                # distinguished from a completed title.
                with (directory / 'ffmpeg.log').open('ab') as diagnostic:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=diagnostic,
                        cwd=directory,
                        start_new_session=True,
                    )
            except (OSError, ValueError):
                self._remove_directory(directory)
                raise RuntimeError("Oynatma bileşeni başlatılamadı. Kurulumu kontrol edin.") from None

            session = _Session(session_id, directory, process, time.monotonic(), live=live)
            with self._lock:
                if self._closed:
                    self._terminate(process)
                    self._remove_directory(directory)
                    raise RuntimeError("Oynatıcı kapatıldı.")
                self._sessions[session_id] = session
                self._active.set()

            deadline = time.monotonic() + self.START_TIMEOUT
            try:
                while time.monotonic() < deadline:
                    with self._lock:
                        if self._sessions.get(session_id) is not session:
                            raise RuntimeError("Oynatma durduruldu.")
                    playlist = directory / "index.m3u8"
                    if self._ready(playlist, directory, minimum_duration=None if live else 4.0) and (not text_subtitle or (directory / 'index_vtt.m3u8').is_file()):
                        session.last_used = time.monotonic()
                        with self._lock:
                            self._update_buffer(session)
                            buffer_state = self._buffer_state(session)
                        return {
                            "sessionId": session_id,
                            "url": f"/media/{session_id}/{'master.m3u8' if text_subtitle else 'index.m3u8'}",
                            "type": "hls",
                            "startOffset": offset,
                            "duration": total,
                            "mode": mode,
                            **buffer_state,
                        }
                    if process.poll() is not None:
                        raise RuntimeError("Yayın başlatılamadı. Başka bir içerik veya uyumluluk modunu deneyin.")
                    self._shutdown.wait(0.15)
                raise RuntimeError("Yayın zamanında yanıt vermedi. Yeniden deneyin veya başka bir içerik açın.")
            except Exception:
                self.stop(session_id)
                raise

    def probe(self, source_url: str) -> dict:
        if not self.available:
            return {'audio': [], 'subtitles': [], 'scanned': False}
        command = [self._ffmpeg, '-hide_banner', '-nostdin', '-rw_timeout', '10000000',
                   '-analyzeduration', '4000000', '-probesize', '8000000', '-i', source_url]
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, timeout=16)
            return parse_tracks(result.stderr.decode('utf-8', errors='replace')[:512000])
        except (OSError, subprocess.TimeoutExpired):
            return {'audio': [], 'subtitles': [], 'scanned': False}

    def _command(self, source: str, directory: Path, mode: str, offset: float, live: bool,
                 audio_index: int | None = None, subtitle_index: int | None = None,
                 subtitle_codec: str = '') -> list[str]:
        command = [
            self._ffmpeg,
            "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-rw_timeout", "30000000",
            "-fflags", "+genpts+discardcorrupt",
            "-analyzeduration", "3000000", "-probesize", "3000000",
        ]
        # The provider can close a VOD HTTP response before Content-Length.
        # Resume seekable files with a byte Range instead of treating the
        # truncated response as the end of the movie. Never reconnect at EOF.
        if source.startswith(('http://', 'https://')):
            command += ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "2"]
            if live:
                command += ["-reconnect_streamed", "1"]
        if offset:
            command += ["-ss", f"{offset:.3f}"]
        # Films can refill their buffer faster than playback after a network
        # stall. The controller below stops production at a bounded lead.
        if live:
            command += ["-re"]
        command += ["-i", source]
        bitmap = subtitle_index is not None and subtitle_codec in BITMAP_SUBTITLES
        scale = "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"
        if bitmap:
            command += ['-filter_complex', f'[0:v:0][0:{subtitle_index}]overlay=eof_action=pass:shortest=0,{scale}[captioned]', '-map', '[captioned]']
        else:
            command += ['-map', '0:v:0?']
        command += ['-map', f'0:{audio_index}' if audio_index is not None else '0:a:0?', '-dn', '-map_metadata', '-1', '-map_chapters', '-1']
        if subtitle_index is not None and not bitmap:
            command += ['-map', f'0:{subtitle_index}', '-c:s', 'webvtt']
        else:
            command += ['-sn']
        if mode == "transcode":
            command += [
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-crf", "23", "-threads", "2", "-pix_fmt", "yuv420p",
                "-force_key_frames", "expr:gte(t,n_forced*2)",
            ]
            if not bitmap:
                command += ["-vf", scale]
        else:
            command += ["-c:v", "copy"]
        if subtitle_index is not None and not bitmap:
            # The HLS WebVTT muxer writes session-relative cue times without
            # X-TIMESTAMP-MAP. MPEG-TS's default 1.4 s mux delay would shift
            # only A/V, making those cues early in native HLS and hls.js.
            command += ["-muxdelay", "0"]
        command += [
            "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "48000",
            "-max_muxing_queue_size", "1024", "-avoid_negative_ts", "make_zero",
            "-f", "hls", "-hls_time", "2", "-hls_list_size", "8" if live else "64",
            "-hls_delete_threshold", "2", "-hls_flags", "delete_segments+temp_file",
            "-hls_segment_filename", str(directory / "seg_%09d.ts"),
            str(directory / "index.m3u8"),
        ]
        return command

    @staticmethod
    def _ready(playlist: Path, directory: Path, minimum_segments: int = 1,
               minimum_duration: float | None = None) -> bool:
        try:
            if not playlist.is_file():
                return False
            lines = playlist.read_text(encoding="utf-8").splitlines()
            segments = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
            complete = "#EXT-X-ENDLIST" in lines
            if minimum_duration is None:
                enough = len(segments) >= minimum_segments or (complete and bool(segments))
            else:
                ready_duration = sum(float(line.split(":", 1)[1].split(",", 1)[0])
                                     for line in lines if line.startswith("#EXTINF:"))
                enough = ready_duration >= minimum_duration or (complete and bool(segments))
            return enough and all(
                _MEDIA_FILE.fullmatch(name) and name.endswith(".ts")
                and (directory / name).is_file() and (directory / name).stat().st_size > 0
                for name in segments
            )
        except (OSError, UnicodeError, ValueError):
            return False

    def ping(self, session_id: str, position: float | None = None) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise FileNotFoundError("Oynatma oturumu sona erdi.")
            if position is not None:
                if isinstance(position, bool):
                    raise ValueError("Geçersiz oynatma zamanı.")
                try:
                    value = float(position)
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("Geçersiz oynatma zamanı.") from None
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Geçersiz oynatma zamanı.")
                session.position = value
            session.last_used = time.monotonic()
            self._update_buffer(session)
            return self._buffer_state(session)

    def pause(self, session_id: str, paused: bool) -> None:
        """Keep a user's pause independent from the prefetch controller's stop."""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise FileNotFoundError("Oynatma oturumu sona erdi.")
            desired = bool(paused)
            session.paused = desired
            self._sync_process_pause(session, strict=True)
            session.last_used = time.monotonic()

    @staticmethod
    def _buffer_state(session: _Session) -> dict:
        return {"cacheStart": round(session.cache_start, 3),
                "cacheEnd": round(session.cache_end, 3),
                "bufferAhead": round(max(0.0, session.cache_end - session.position), 3)}

    def _sync_process_pause(self, session: _Session, strict: bool = False) -> None:
        desired = session.paused or session.flow_paused
        if desired == session.process_paused or session.process.poll() is not None:
            return
        pause_signal = getattr(signal, "SIGSTOP" if desired else "SIGCONT", None)
        if pause_signal is None:
            if strict:
                raise RuntimeError("Bu bilgisayarda yayın duraklatma desteklenmiyor.")
            return
        try:
            session.process.send_signal(pause_signal)
            session.process_paused = desired
        except OSError:
            if strict and session.process.poll() is None:
                raise RuntimeError("Yayın duraklatılamadı. Yeniden oynatmayı deneyin.") from None

    def _update_buffer(self, session: _Session) -> None:
        """Track cumulative media time even after older HLS entries roll away.

        Call with _lock held. FFmpeg writes manifests atomically, so a reader
        always sees a complete duration/sequence snapshot.
        """
        if session.live:
            return
        try:
            lines = (session.directory / "index.m3u8").read_text(encoding="utf-8").splitlines()
            sequence = next((int(line.split(":", 1)[1]) for line in lines
                             if line.startswith("#EXT-X-MEDIA-SEQUENCE:")), 0)
            durations = [float(line.split(":", 1)[1].split(",", 1)[0])
                         for line in lines if line.startswith("#EXTINF:")]
            if not durations:
                return
            # Normally every segment is observed. Account for a skipped early
            # snapshot too, e.g. a tiny fixture processed within one poll.
            if sequence > session.last_sequence + 1:
                session.cache_end += (sequence - session.last_sequence - 1) * (sum(durations) / len(durations))
                session.last_sequence = sequence - 1
            for index, duration in enumerate(durations, sequence):
                if index > session.last_sequence:
                    session.cache_end += duration
                    session.last_sequence = index
            session.cache_start = max(0.0, session.cache_end - sum(durations))
            ahead = session.cache_end - session.position
            if session.flow_paused:
                if ahead <= self.PREFETCH_RESUME_SECONDS:
                    session.flow_paused = False
            elif ahead >= self.PREFETCH_SECONDS:
                session.flow_paused = True
            self._sync_process_pause(session)
        except (OSError, UnicodeError, ValueError):
            return

    def _buffer_loop(self) -> None:
        while not self._shutdown.is_set():
            if not self._active.wait(1.0):
                continue
            if self._shutdown.wait(self.BUFFER_INTERVAL):
                break
            with self._lock:
                if not self._sessions:
                    self._active.clear()
                    continue
                for session in self._sessions.values():
                    self._update_buffer(session)

    def get_file(self, session_id: str, filename: str) -> Path:
        if not _SESSION_ID.fullmatch(session_id) or not _MEDIA_FILE.fullmatch(filename):
            raise FileNotFoundError("Oynatma dosyası bulunamadı.")
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise FileNotFoundError("Oynatma oturumu sona erdi.")
            path = session.directory / filename
            if path.is_symlink() or not path.is_file():
                raise FileNotFoundError("Oynatma dosyası bulunamadı.")
            session.last_used = time.monotonic()
            return path

    def stop(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if not self._sessions:
                self._active.clear()
        if session:
            self._terminate(session.process)
            self._remove_directory(session.directory)

    @staticmethod
    def _terminate(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            # A stopped process cannot handle SIGTERM until it is continued.
            if resume_signal := getattr(signal, "SIGCONT", None):
                process.send_signal(resume_signal)
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except (OSError, ProcessLookupError):
            pass

    @staticmethod
    def _remove_directory(directory: Path) -> None:
        try:
            if directory.is_symlink():
                directory.unlink()
            else:
                shutil.rmtree(directory, ignore_errors=True)
        except OSError:
            pass

    def _reap(self) -> None:
        while not self._shutdown.wait(self.REAPER_INTERVAL):
            cutoff = time.monotonic() - self.IDLE_TIMEOUT
            with self._lock:
                idle = [session for session in self._sessions.values() if session.last_used < cutoff]
                for session in idle:
                    self._sessions.pop(session.session_id, None)
                if not self._sessions:
                    self._active.clear()
            for session in idle:
                self._terminate(session.process)
                self._remove_directory(session.directory)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            session_ids = list(self._sessions)
        self._shutdown.set()
        self._active.set()
        for session_id in session_ids:
            self.stop(session_id)
        if threading.current_thread() is not self._reaper:
            self._reaper.join(timeout=3)
        if threading.current_thread() is not self._buffer:
            self._buffer.join(timeout=3)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
