/* Mavie TV — ES2018 / ES5-Safe Multi-Platform Player Engine
 * Selects Samsung AVPlay API (webapis.avplay) on Tizen TVs and hls.js / HTML5 <video>
 * on LG webOS, Smart TV browsers, and desktop preview.
 */
(function (root) {
  'use strict';

  function formatTime(sec) {
    var s = Math.max(0, Math.floor(Number(sec) || 0));
    var h = Math.floor(s / 3600);
    var m = Math.floor((s % 3600) / 60);
    var rem = s % 60;
    var mm = m < 10 && h > 0 ? '0' + m : String(m);
    var ss = rem < 10 ? '0' + rem : String(rem);
    return h > 0 ? h + ':' + mm + ':' + ss : mm + ':' + ss;
  }

  function hasSamsungAvPlay() {
    try {
      return !!(root.webapis && root.webapis.avplay && typeof root.webapis.avplay.open === 'function');
    } catch (err) {
      return false;
    }
  }

  function notifyScreenSaver(disable) {
    if (root.MaviePlatform && typeof root.MaviePlatform.setScreenSaver === 'function') {
      root.MaviePlatform.setScreenSaver(!disable);
    }
  }

  // Adapter 1: Samsung Tizen Hardware AVPlay API
  function createSamsungAvPlayAdapter(callbacks) {
    var avplay = root.webapis.avplay;
    var audioTracks = [];
    var textTracks = [];
    var audioIdx = -1;
    var textIdx = -1;
    var durationSec = 0;
    var currentSec = 0;

    function safeStopClose() {
      try {
        var st = avplay.getState();
        if (st && st !== 'NONE' && st !== 'IDLE') {
          avplay.stop();
        }
      } catch (err) {
        // Ignore state transition errors
      }
      try {
        avplay.close();
      } catch (err2) {
        // Ignore close errors
      }
    }

    function readTracks() {
      audioTracks = [];
      textTracks = [];
      try {
        var list = avplay.getTotalTrackInfo() || [];
        var i, info, extra, lang;
        for (i = 0; i < list.length; i++) {
          info = list[i];
          extra = {};
          try {
            extra = info.extra_info ? JSON.parse(info.extra_info) : {};
          } catch (e) {
            extra = {};
          }
          lang = extra.language || extra.track_lang || ('Parça ' + info.index);
          if (info.type === 'AUDIO') {
            audioTracks.push({ index: info.index, label: lang });
          } else if (info.type === 'TEXT') {
            textTracks.push({ index: info.index, label: lang });
          }
        }
      } catch (err) {
        // Track metadata unavailable
      }
      if (callbacks.onTracks) callbacks.onTracks(audioTracks, textTracks, audioIdx, textIdx);
    }

    return {
      name: 'Samsung AVPlay (Donanımsal)',
      open: function (url, opts) {
        safeStopClose();
        durationSec = Number(opts && opts.duration) || 0;
        currentSec = 0;
        audioIdx = -1;
        textIdx = -1;

        try {
          avplay.open(url);
          avplay.setDisplayRect(0, 0, 1920, 1080);
          try {
            avplay.setDisplayMethod('PLAYER_DISPLAY_MODE_FULL_SCREEN');
          } catch (e1) {
            // Optional on some Tizen models
          }
          if (opts && opts.externalSubtitle) {
            try {
              avplay.setExternalSubtitlePath(opts.externalSubtitle);
            } catch (e2) {
              // Optional external subtitle
            }
          }
          avplay.setListener({
            onbufferingstart: function () {
              if (callbacks.onLoading) callbacks.onLoading(true, 'Önbellekleniyor…');
            },
            onbufferingprogress: function (percent) {
              if (callbacks.onLoading) callbacks.onLoading(true, 'Önbellekleniyor %' + percent);
            },
            onbufferingcomplete: function () {
              if (callbacks.onLoading) callbacks.onLoading(false);
            },
            oncurrentplaytime: function (ms) {
              currentSec = Math.floor((Number(ms) || 0) / 1000);
              var d = 0;
              try {
                d = Math.floor((Number(avplay.getDuration()) || 0) / 1000);
              } catch (e3) {
                d = durationSec;
              }
              if (d > 0) durationSec = d;
              if (callbacks.onTime) callbacks.onTime(currentSec, durationSec);
            },
            onsubtitlechange: function (dur, text) {
              if (callbacks.onSubtitleText) callbacks.onSubtitleText(text || '');
            },
            onstreamcompleted: function () {
              safeStopClose();
              if (callbacks.onEnded) callbacks.onEnded();
            },
            onerror: function (errorType) {
              if (callbacks.onError) callbacks.onError('AVPlay hatası: ' + String(errorType || 'Bilinmeyen akış hatası'));
            }
          });
          avplay.prepareAsync(
            function () {
              if (callbacks.onLoading) callbacks.onLoading(false);
              readTracks();
              if (opts && opts.start > 5 && !opts.isLive) {
                try {
                  avplay.seekTo(Math.floor(opts.start * 1000));
                } catch (eSeek) {
                  // Ignore unsupported seek before play
                }
              }
              avplay.play();
              notifyScreenSaver(true);
              if (callbacks.onState) callbacks.onState(true);
            },
            function (err) {
              if (callbacks.onError) callbacks.onError('Yayın hazırlanamadı (' + (err && err.message ? err.message : 'AVPlay') + ')');
            }
          );
        } catch (err) {
          if (callbacks.onError) callbacks.onError('AVPlay başlatılamadı: ' + (err && err.message ? err.message : String(err)));
        }
      },
      togglePlay: function () {
        try {
          var st = avplay.getState();
          if (st === 'PLAYING') {
            avplay.pause();
            notifyScreenSaver(false);
            if (callbacks.onState) callbacks.onState(false);
          } else {
            avplay.play();
            notifyScreenSaver(true);
            if (callbacks.onState) callbacks.onState(true);
          }
        } catch (err) {
          // Ignore state error
        }
      },
      seekDelta: function (sec) {
        try {
          if (sec >= 0) {
            avplay.jumpForward(Math.floor(sec * 1000));
          } else {
            avplay.jumpBackward(Math.floor(Math.abs(sec) * 1000));
          }
        } catch (err) {
          // Live streams may not support seek
        }
      },
      cycleAudio: function () {
        if (audioTracks.length === 0) return 'Ses: Varsayılan';
        audioIdx = (audioIdx + 1) % audioTracks.length;
        try {
          avplay.setSelectTrack('AUDIO', audioTracks[audioIdx].index);
        } catch (err) {
          // Ignore
        }
        return 'Ses: ' + audioTracks[audioIdx].label;
      },
      cycleSubtitle: function () {
        if (textTracks.length === 0) return 'Altyazı: Yok';
        textIdx += 1;
        if (textIdx >= textTracks.length) {
          textIdx = -1;
          try { avplay.setSilentSubtitle(true); } catch (err) {}
          if (callbacks.onSubtitleText) callbacks.onSubtitleText('');
          return 'Altyazı: Kapalı';
        }
        try {
          avplay.setSilentSubtitle(false);
          avplay.setSelectTrack('TEXT', textTracks[textIdx].index);
        } catch (err2) {}
        return 'Altyazı: ' + textTracks[textIdx].label;
      },
      getPosition: function () {
        return { current: currentSec, duration: durationSec };
      },
      destroy: function () {
        notifyScreenSaver(false);
        safeStopClose();
      }
    };
  }

  // Adapter 2: hls.js + Native HTML5 <video> (LG webOS, Smart TV Browsers, Desktop /tv)
  function createHlsVideoAdapter(videoEl, callbacks) {
    var hls = null;
    var audioIdx = -1;
    var subIdx = -1;

    function cleanupHls() {
      if (hls) {
        try { hls.destroy(); } catch (err) {}
        hls = null;
      }
      if (videoEl) {
        try {
          videoEl.pause();
          videoEl.removeAttribute('src');
          videoEl.load();
        } catch (err2) {}
      }
    }

    function bindEvents() {
      videoEl.onwaiting = function () {
        if (callbacks.onLoading) callbacks.onLoading(true, 'Yükleniyor…');
      };
      videoEl.onplaying = function () {
        if (callbacks.onLoading) callbacks.onLoading(false);
        notifyScreenSaver(true);
        if (callbacks.onState) callbacks.onState(true);
      };
      videoEl.onpause = function () {
        notifyScreenSaver(false);
        if (callbacks.onState) callbacks.onState(false);
      };
      videoEl.ontimeupdate = function () {
        if (callbacks.onTime) {
          callbacks.onTime(videoEl.currentTime || 0, isFinite(videoEl.duration) ? videoEl.duration : 0);
        }
      };
      videoEl.onended = function () {
        notifyScreenSaver(false);
        if (callbacks.onEnded) callbacks.onEnded();
      };
      videoEl.onerror = function () {
        if (callbacks.onError) {
          callbacks.onError('Video çözümlenemedi veya ağ akışı koptu. Tekrar deneyin veya Ev Sunucusu dönüştürme modunu kullanın.');
        }
      };
    }

    return {
      name: 'HLS.js / HTML5 Video',
      open: function (url, opts) {
        cleanupHls();
        bindEvents();
        audioIdx = -1;
        subIdx = -1;
        if (callbacks.onLoading) callbacks.onLoading(true, 'Yayın bağlanıyor…');

        var isHlsUrl = /\.m3u8(?:[?#]|$)/i.test(url) || (opts && opts.type === 'hls');
        var useHlsJs = isHlsUrl && typeof root.Hls !== 'undefined' && root.Hls.isSupported() && !videoEl.canPlayType('application/vnd.apple.mpegurl');

        if (useHlsJs) {
          hls = new root.Hls({
            enableWorker: true,
            lowLatencyMode: !!(opts && opts.isLive),
            maxBufferLength: 30
          });
          hls.loadSource(url);
          hls.attachMedia(videoEl);
          hls.on(root.Hls.Events.MANIFEST_PARSED, function () {
            if (opts && opts.start > 5 && !opts.isLive) {
              try { videoEl.currentTime = opts.start; } catch (e) {}
            }
            var playPromise = videoEl.play();
            if (playPromise && typeof playPromise.catch === 'function') {
              playPromise.catch(function () {
                if (callbacks.onLoading) callbacks.onLoading(false);
              });
            }
          });
          hls.on(root.Hls.Events.ERROR, function (ev, data) {
            if (data && data.fatal) {
              if (data.type === root.Hls.ErrorTypes.NETWORK_ERROR) {
                hls.startLoad();
              } else if (data.type === root.Hls.ErrorTypes.MEDIA_ERROR) {
                hls.recoverMediaError();
              } else if (callbacks.onError) {
                callbacks.onError('HLS yayın hatası: ' + String(data.details || 'Bağlantı kesildi'));
              }
            }
          });
        } else {
          videoEl.src = url;
          videoEl.onloadedmetadata = function () {
            if (opts && opts.start > 5 && !opts.isLive) {
              try { videoEl.currentTime = opts.start; } catch (e) {}
            }
          };
          var p = videoEl.play();
          if (p && typeof p.catch === 'function') {
            p.catch(function () {
              if (callbacks.onLoading) callbacks.onLoading(false);
            });
          }
        }
      },
      togglePlay: function () {
        if (!videoEl) return;
        if (videoEl.paused) {
          var p = videoEl.play();
          if (p && typeof p.catch === 'function') p.catch(function () {});
        } else {
          videoEl.pause();
        }
      },
      seekDelta: function (sec) {
        if (!videoEl || !isFinite(videoEl.duration)) return;
        var next = Math.max(0, Math.min(videoEl.duration, (videoEl.currentTime || 0) + sec));
        videoEl.currentTime = next;
      },
      cycleAudio: function () {
        if (hls && hls.audioTracks && hls.audioTracks.length > 0) {
          audioIdx = (audioIdx + 1) % hls.audioTracks.length;
          hls.audioTrack = audioIdx;
          var t = hls.audioTracks[audioIdx];
          return 'Ses: ' + (t.name || t.lang || ('#' + (audioIdx + 1)));
        }
        return 'Ses: Varsayılan';
      },
      cycleSubtitle: function () {
        if (hls && hls.subtitleTracks && hls.subtitleTracks.length > 0) {
          subIdx += 1;
          if (subIdx >= hls.subtitleTracks.length) {
            subIdx = -1;
            hls.subtitleTrack = -1;
            return 'Altyazı: Kapalı';
          }
          hls.subtitleTrack = subIdx;
          var s = hls.subtitleTracks[subIdx];
          return 'Altyazı: ' + (s.name || s.lang || ('#' + (subIdx + 1)));
        }
        if (videoEl && videoEl.textTracks && videoEl.textTracks.length > 0) {
          var i;
          subIdx += 1;
          if (subIdx >= videoEl.textTracks.length) subIdx = -1;
          for (i = 0; i < videoEl.textTracks.length; i++) {
            videoEl.textTracks[i].mode = (i === subIdx) ? 'showing' : 'disabled';
          }
          if (subIdx === -1) return 'Altyazı: Kapalı';
          var tt = videoEl.textTracks[subIdx];
          return 'Altyazı: ' + (tt.label || tt.language || ('#' + (subIdx + 1)));
        }
        return 'Altyazı: Yok';
      },
      getPosition: function () {
        return {
          current: videoEl ? (videoEl.currentTime || 0) : 0,
          duration: videoEl && isFinite(videoEl.duration) ? videoEl.duration : 0
        };
      },
      destroy: function () {
        notifyScreenSaver(false);
        cleanupHls();
      }
    };
  }

  // Controller wrapping OSD + Adapter + Retry + Channel Zap
  var activeAdapter = null;
  var activeItem = null;
  var activeOpts = null;
  var osdTimer = null;
  var progressTimer = null;
  var onCloseCb = null;
  var onZapCb = null;
  var onProgressCb = null;

  function byId(id) {
    return typeof document !== 'undefined' ? document.getElementById(id) : null;
  }

  function showOsd(keepOpen) {
    var osd = byId('tvPlayerOsd');
    if (!osd) return;
    osd.classList.remove('osd-hidden');
    if (osdTimer) clearTimeout(osdTimer);
    if (!keepOpen) {
      osdTimer = setTimeout(function () {
        osd.classList.add('osd-hidden');
      }, 5500);
    }
  }

  function open(item, streamInfo, options) {
    close(true);
    activeItem = item;
    activeOpts = options || {};
    onCloseCb = activeOpts.onClose || null;
    onZapCb = activeOpts.onZap || null;
    onProgressCb = activeOpts.onProgress || null;

    var layer = byId('tvPlayerLayer');
    var avObj = byId('tvAvplayObject');
    var videoEl = byId('tvVideo');
    var errBox = byId('tvPlayerErrorBox');
    var loadingEl = byId('tvPlayerLoading');
    var titleEl = byId('tvOsdTitle');
    var subEl = byId('tvOsdSub');
    var badgeEl = byId('tvOsdModeBadge');
    var engineEl = byId('tvOsdEngine');
    var prevCh = byId('tvBtnPrevCh');
    var nextCh = byId('tvBtnNextCh');
    var progWrap = byId('tvProgressWrap');

    if (!layer) return;
    layer.hidden = false;
    if (errBox) errBox.hidden = true;
    if (loadingEl) loadingEl.hidden = false;

    var isLive = item.kind === 'live';
    if (titleEl) titleEl.textContent = item.name || 'Yayın';
    if (subEl) subEl.textContent = item.categoryName || (isLive ? 'Canlı TV' : 'Mavie Sinema');
    if (badgeEl) badgeEl.textContent = isLive ? 'CANLI YAYIN' : 'MAVIE OYNATICI';
    if (prevCh) prevCh.hidden = !isLive;
    if (nextCh) nextCh.hidden = !isLive;
    if (progWrap) progWrap.hidden = isLive;

    var callbacks = {
      onLoading: function (isLoading, msg) {
        if (loadingEl) loadingEl.hidden = !isLoading;
        var lt = byId('tvPlayerLoadingText');
        if (lt && msg) lt.textContent = msg;
      },
      onState: function (isPlaying) {
        var btn = byId('tvBtnPlayPause');
        if (btn) btn.textContent = isPlaying ? 'Duraklat' : 'Oynat';
      },
      onTime: function (cur, dur) {
        var curEl = byId('tvTimeCurrent');
        var totEl = byId('tvTimeTotal');
        var fillEl = byId('tvProgressFill');
        if (curEl) curEl.textContent = formatTime(cur);
        if (totEl) totEl.textContent = dur > 0 ? formatTime(dur) : '--:--';
        if (fillEl && dur > 0) {
          var pct = Math.max(0, Math.min(100, (cur / dur) * 100));
          fillEl.style.width = pct.toFixed(1) + '%';
        }
      },
      onSubtitleText: function (txt) {
        var subOverlay = byId('tvPlayerSubtitle');
        if (!subOverlay) return;
        subOverlay.textContent = txt || '';
        subOverlay.hidden = !txt;
      },
      onEnded: function () {
        showOsd(true);
      },
      onError: function (msg) {
        if (loadingEl) loadingEl.hidden = true;
        if (errBox) errBox.hidden = false;
        var em = byId('tvPlayerErrorMsg');
        if (em) em.textContent = msg || 'Yayın başlatılamadı.';
        showOsd(true);
        if (root.MavieSpatial) root.MavieSpatial.focusElement(byId('tvPlayerRetryBtn'));
      }
    };

    var useAvPlay = hasSamsungAvPlay();
    if (avObj) avObj.hidden = !useAvPlay;
    if (videoEl) videoEl.hidden = useAvPlay;

    activeAdapter = useAvPlay
      ? createSamsungAvPlayAdapter(callbacks)
      : createHlsVideoAdapter(videoEl, callbacks);

    if (engineEl) engineEl.textContent = activeAdapter.name;

    activeAdapter.open(streamInfo.url, {
      isLive: isLive,
      type: streamInfo.type || (isLive ? 'hls' : 'file'),
      start: Number(streamInfo.start) || 0,
      duration: Number(streamInfo.duration || item.duration) || 0,
      externalSubtitle: streamInfo.externalSubtitle || ''
    });

    if (progressTimer) clearInterval(progressTimer);
    if (!isLive && typeof onProgressCb === 'function') {
      progressTimer = setInterval(function () {
        if (!activeAdapter || !activeItem) return;
        var pos = activeAdapter.getPosition();
        if (pos.current > 3) {
          onProgressCb(activeItem, pos.current, pos.duration);
        }
      }, 10000);
    }

    showOsd(false);
    if (root.MavieSpatial) {
      root.MavieSpatial.focusElement(byId('tvBtnPlayPause'));
    }
  }

  function close(silent) {
    if (osdTimer) { clearTimeout(osdTimer); osdTimer = null; }
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }

    if (activeAdapter && activeItem && activeItem.kind !== 'live' && typeof onProgressCb === 'function') {
      var pos = activeAdapter.getPosition();
      if (pos.current > 3) onProgressCb(activeItem, pos.current, pos.duration);
    }
    if (activeAdapter) {
      activeAdapter.destroy();
      activeAdapter = null;
    }

    var layer = byId('tvPlayerLayer');
    if (layer) layer.hidden = true;
    var subOverlay = byId('tvPlayerSubtitle');
    if (subOverlay) { subOverlay.textContent = ''; subOverlay.hidden = true; }

    var closedItem = activeItem;
    activeItem = null;
    if (!silent && typeof onCloseCb === 'function') {
      var cb = onCloseCb;
      onCloseCb = null;
      cb(closedItem);
    }
  }

  function bindUiControls() {
    if (typeof document === 'undefined') return;
    var map = [
      ['tvBtnBack', function () { close(false); }],
      ['tvPlayerErrorCloseBtn', function () { close(false); }],
      ['tvBtnPlayPause', function () { if (activeAdapter) activeAdapter.togglePlay(); showOsd(false); }],
      ['tvBtnRew', function () { if (activeAdapter) activeAdapter.seekDelta(-10); showOsd(false); }],
      ['tvBtnFwd', function () { if (activeAdapter) activeAdapter.seekDelta(10); showOsd(false); }],
      ['tvBtnAudio', function () {
        if (activeAdapter) {
          var label = activeAdapter.cycleAudio();
          var btn = byId('tvBtnAudio');
          if (btn) btn.textContent = label;
          showOsd(false);
        }
      }],
      ['tvBtnSub', function () {
        if (activeAdapter) {
          var label = activeAdapter.cycleSubtitle();
          var btn = byId('tvBtnSub');
          if (btn) btn.textContent = label;
          showOsd(false);
        }
      }],
      ['tvBtnPrevCh', function () { if (typeof onZapCb === 'function') onZapCb(-1); }],
      ['tvBtnNextCh', function () { if (typeof onZapCb === 'function') onZapCb(1); }],
      ['tvPlayerRetryBtn', function () {
        if (activeOpts && typeof activeOpts.onRetry === 'function' && activeItem) {
          activeOpts.onRetry(activeItem);
        }
      }]
    ];
    var i;
    for (i = 0; i < map.length; i++) {
      (function (id, handler) {
        var el = byId(id);
        if (el) el.addEventListener('click', handler);
      })(map[i][0], map[i][1]);
    }
  }

  function handleMediaKey(keyCode) {
    if (!activeAdapter) return false;
    var K = root.MavieSpatial ? root.MavieSpatial.KEYS : {};
    showOsd(false);
    if (keyCode === K.MEDIA_PLAY_PAUSE || keyCode === K.MEDIA_PLAY || keyCode === K.MEDIA_PAUSE) {
      activeAdapter.togglePlay();
      return true;
    }
    if (keyCode === K.MEDIA_STOP) {
      close(false);
      return true;
    }
    if (keyCode === K.MEDIA_REWIND) {
      activeAdapter.seekDelta(-10);
      return true;
    }
    if (keyCode === K.MEDIA_FF) {
      activeAdapter.seekDelta(10);
      return true;
    }
    if (keyCode === K.CHANNEL_UP && typeof onZapCb === 'function') {
      onZapCb(1);
      return true;
    }
    if (keyCode === K.CHANNEL_DOWN && typeof onZapCb === 'function') {
      onZapCb(-1);
      return true;
    }
    return false;
  }

  var api = {
    formatTime: formatTime,
    hasSamsungAvPlay: hasSamsungAvPlay,
    bindUiControls: bindUiControls,
    open: open,
    close: close,
    showOsd: showOsd,
    handleMediaKey: handleMediaKey,
    isOpen: function () { return !!activeAdapter; }
  };

  root.MaviePlayer = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : this);
