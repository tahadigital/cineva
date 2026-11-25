/* Mavie TV — ES2018 / ES5-Safe Universal 10-Foot TV Application Core
 * Supports Dual Mode:
 *  1) Companion Mode (Ev Sunucusu http://<PC-IP>:8844 — auto-detected or paired)
 *  2) Standalone Mode (Direct M3U / Xtream + Built-in Demo Catalog + QR Setup)
 */
(function (root) {
  'use strict';

  var STORAGE_KEY = 'mavie_tv_state_v1';
  var ROUTE_TITLES = {
    home: 'Ana Sayfa',
    live: 'Canlı TV',
    vod: 'Filmler',
    series: 'Diziler',
    sports: 'Spor Ekranı',
    favorites: 'Favoriler',
    search: 'Arama',
    settings: 'Ayarlar / Bağlan'
  };

  var state = {
    route: 'home',
    mode: 'standalone', // 'companion' | 'standalone'
    serverUrl: '',
    tvInfo: null,
    serverStatus: null,
    pairingRequired: false,
    items: [],
    continueWatching: [],
    favoritesMap: {},
    progressMap: {},
    profileName: 'Ana Profil',
    activeCategory: '',
    searchQuery: '',
    sportsGuide: null,
    sportsLoading: false,
    activeSessionId: null,
    sourceLabel: 'Açık Sinema (Demo)',
    m3uUrl: '',
    xtreamHost: '',
    xtreamUser: ''
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function esc(val) {
    return String(val === undefined || val === null ? '' : val)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function loadPersisted() {
    try {
      var raw = root.localStorage ? root.localStorage.getItem(STORAGE_KEY) : null;
      if (!raw) return;
      var data = JSON.parse(raw);
      if (data && typeof data === 'object') {
        if (typeof data.serverUrl === 'string') state.serverUrl = data.serverUrl;
        if (data.favoritesMap && typeof data.favoritesMap === 'object') state.favoritesMap = data.favoritesMap;
        if (data.progressMap && typeof data.progressMap === 'object') state.progressMap = data.progressMap;
        if (typeof data.profileName === 'string' && data.profileName) state.profileName = data.profileName;
        if (typeof data.m3uUrl === 'string') state.m3uUrl = data.m3uUrl;
        if (typeof data.xtreamHost === 'string') state.xtreamHost = data.xtreamHost;
        if (typeof data.xtreamUser === 'string') state.xtreamUser = data.xtreamUser;
        if (Array.isArray(data.standaloneItems) && data.standaloneItems.length > 0) {
          state.items = data.standaloneItems;
          state.sourceLabel = data.sourceLabel || 'Kayıtlı Liste';
        }
      }
    } catch (err) {
      // Ignore storage read error
    }
  }

  function savePersisted() {
    try {
      if (!root.localStorage) return;
      var payload = {
        serverUrl: state.serverUrl,
        favoritesMap: state.favoritesMap,
        progressMap: state.progressMap,
        profileName: state.profileName,
        m3uUrl: state.m3uUrl,
        xtreamHost: state.xtreamHost,
        xtreamUser: state.xtreamUser,
        sourceLabel: state.sourceLabel,
        standaloneItems: state.mode === 'standalone' ? state.items.slice(0, 600) : []
      };
      root.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (err) {
      // Quota or private mode
    }
  }

  var toastTimer = null;
  function showToast(msg, isError) {
    var el = byId('tvToast');
    if (!el) return;
    el.textContent = msg;
    el.className = 'tv-toast' + (isError ? ' error' : '');
    el.hidden = false;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.hidden = true;
    }, 4500);
  }

  function httpJson(url, opts) {
    var o = opts || {};
    var headers = {};
    if (o.body) headers['Content-Type'] = 'application/json';
    return fetch(url, {
      method: o.method || 'GET',
      credentials: 'include',
      headers: headers,
      body: o.body ? JSON.stringify(o.body) : undefined
    }).then(function (resp) {
      return resp.text().then(function (txt) {
        var data = null;
        try { data = txt ? JSON.parse(txt) : {}; } catch (err) { data = { error: txt }; }
        if (!resp.ok) {
          var e = new Error((data && data.error) || ('HTTP ' + resp.status));
          e.status = resp.status;
          throw e;
        }
        return data;
      });
    });
  }

  function httpText(url) {
    return fetch(url, { method: 'GET' }).then(function (resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.text();
    });
  }

  function apiBase() {
    if (state.serverUrl) return state.serverUrl.replace(/\/+$/, '');
    if (root.location && /^https?:$/i.test(root.location.protocol)) {
      return root.location.protocol + '//' + root.location.host;
    }
    return '';
  }

  function resolveMediaUrl(rawUrl) {
    if (!rawUrl) return '';
    if (/^https?:\/\//i.test(rawUrl)) return rawUrl;
    var base = apiBase();
    if (rawUrl.charAt(0) === '/' && base) return base + rawUrl;
    return rawUrl;
  }

  function posterUrl(item) {
    if (!item || !item.poster) return '';
    if (state.mode === 'companion' && apiBase() && /^https?:\/\//i.test(item.poster)) {
      return apiBase() + '/api/image?url=' + encodeURIComponent(item.poster);
    }
    return item.poster;
  }

  function updateStatusBar() {
    var dot = byId('tvStatusDot');
    var txt = byId('tvStatusText');
    var sub = byId('tvStatusSub');
    var badge = byId('tvPlatformBadge');
    var meta = byId('tvPageMeta');

    var plat = root.MaviePlatform || { label: 'Universal Smart TV', name: 'web' };
    if (badge) {
      badge.textContent = plat.name === 'tizen' ? 'SAMSUNG TIZEN' : (plat.name === 'webos' ? 'LG WEBOS' : 'SMART TV');
    }
    if (dot) {
      dot.className = 'tv-status-dot' + (state.mode === 'companion' ? ' companion' : '');
    }
    if (txt) {
      txt.textContent = state.mode === 'companion' ? 'Ev Sunucusu Bağlı' : 'Bağımsız Mod';
    }
    if (sub) {
      sub.textContent = state.mode === 'companion'
        ? (apiBase() || 'Yerel Ağ')
        : state.sourceLabel;
    }
    if (meta) {
      meta.textContent = state.profileName + ' · ' + state.items.length + ' içerik';
    }
  }

  function updateClock() {
    var el = byId('tvClock');
    if (!el) return;
    var now = new Date();
    var hh = now.getHours();
    var mm = now.getMinutes();
    el.textContent = (hh < 10 ? '0' + hh : hh) + ':' + (mm < 10 ? '0' + mm : mm);
  }

  function loadDemoCatalog() {
    state.mode = 'standalone';
    state.items = root.MavieM3U.getDemoCatalog();
    state.sourceLabel = 'Açık Sinema (Demo)';
    state.continueWatching = buildStandaloneContinue();
    savePersisted();
    updateStatusBar();
  }

  function buildStandaloneContinue() {
    var out = [];
    var i, item, prog;
    for (i = 0; i < state.items.length; i++) {
      item = state.items[i];
      prog = state.progressMap[item.id];
      if (prog && prog.position > 10 && (!prog.duration || prog.position / prog.duration < 0.95)) {
        out.push(item);
      }
    }
    return out;
  }

  function connectCompanion(baseUrl, silent) {
    var clean = root.MavieM3U.normalizeBaseHost(baseUrl);
    if (!clean) return Promise.reject(new Error('Geçerli bir sunucu adresi girin.'));

    return httpJson(clean + '/api/health').then(function (health) {
      if (!health || health.app !== 'mavie' || !health.ok) {
        throw new Error('Bu adreste Mavie sunucusu bulunamadı.');
      }
      state.serverUrl = clean;
      return httpJson(clean + '/api/tv-info').catch(function () { return null; }).then(function (info) {
        state.tvInfo = info;
        return httpJson(clean + '/api/status');
      });
    }).then(function (st) {
      state.serverStatus = st;
      if (st && st.pairingRequired && !st.authorized) {
        state.pairingRequired = true;
        openPairModal();
        return false;
      }
      state.pairingRequired = false;
      state.mode = 'companion';
      if (st && st.profile && st.profile.name) {
        state.profileName = st.profile.name;
      }
      if (st && st.connection && st.connection.name) {
        state.sourceLabel = st.connection.name;
      }
      savePersisted();
      return refreshCompanionLibrary().then(function () {
        updateStatusBar();
        if (!silent) showToast('Ev sunucusuna bağlandı: ' + clean, false);
        return true;
      });
    });
  }

  function refreshCompanionLibrary() {
    var base = apiBase();
    if (!base) return Promise.resolve();
    return Promise.all([
      httpJson(base + '/api/home').catch(function () { return {}; }),
      httpJson(base + '/api/catalog?kind=live&limit=100').catch(function () { return { items: [] }; }),
      httpJson(base + '/api/catalog?kind=vod&limit=100').catch(function () { return { items: [] }; }),
      httpJson(base + '/api/catalog?kind=series&limit=100').catch(function () { return { items: [] }; })
    ]).then(function (results) {
      var homeData = results[0] || {};
      var liveItems = (results[1] && results[1].items) || [];
      var vodItems = (results[2] && results[2].items) || [];
      var seriesItems = (results[3] && results[3].items) || [];
      var merged = [];
      var seen = {};
      var lists = [liveItems, vodItems, seriesItems, homeData.recent || [], homeData.favorites || []];
      var i, j, it;
      for (i = 0; i < lists.length; i++) {
        for (j = 0; j < lists[i].length; j++) {
          it = lists[i][j];
          if (it && it.id && !seen[it.id]) {
            seen[it.id] = 1;
            merged.push(it);
            if (it.favorite) state.favoritesMap[it.id] = true;
          }
        }
      }
      state.items = merged.length > 0 ? merged : root.MavieM3U.getDemoCatalog();
      state.continueWatching = Array.isArray(homeData.continueWatching) ? homeData.continueWatching : [];
      updateStatusBar();
    });
  }

  function isFavorite(item) {
    if (!item) return false;
    return !!(state.favoritesMap[item.id] || item.favorite);
  }

  function toggleFavorite(item) {
    if (!item || !item.id) return;
    var next = !isFavorite(item);
    state.favoritesMap[item.id] = next;
    item.favorite = next;
    savePersisted();

    if (state.mode === 'companion' && apiBase()) {
      httpJson(apiBase() + '/api/favorites', {
        method: 'POST',
        body: { id: item.id, favorite: next }
      }).catch(function () {});
    }
    showToast(next ? 'Favorilere eklendi: ' + item.name : 'Favorilerden çıkarıldı', false);
  }

  function saveProgress(item, cur, dur) {
    if (!item || !item.id || item.kind === 'live') return;
    state.progressMap[item.id] = { position: Math.floor(cur), duration: Math.floor(dur || item.duration || 0) };
    savePersisted();
    if (state.mode === 'companion' && apiBase()) {
      httpJson(apiBase() + '/api/progress', {
        method: 'POST',
        body: { id: item.id, position: cur, duration: dur || 0, sessionId: state.activeSessionId || undefined }
      }).catch(function () {});
    }
  }

  function stopCompanionSession() {
    if (state.activeSessionId && state.mode === 'companion' && apiBase()) {
      var sid = state.activeSessionId;
      state.activeSessionId = null;
      fetch(apiBase() + '/api/play/' + encodeURIComponent(sid), {
        method: 'DELETE',
        credentials: 'include'
      }).catch(function () {});
    }
  }

  function findItemById(id) {
    var i;
    for (i = 0; i < state.items.length; i++) {
      if (state.items[i].id === id) return state.items[i];
    }
    return null;
  }

  function getItemsByKind(kind) {
    var out = [];
    var i;
    for (i = 0; i < state.items.length; i++) {
      if (state.items[i].kind === kind) out.push(state.items[i]);
    }
    return out;
  }

  function playItem(item, startPos) {
    if (!item) return;
    if (item.kind === 'series') {
      openDetailModal(item);
      return;
    }

    var resumeSec = typeof startPos === 'number'
      ? startPos
      : (state.progressMap[item.id] ? state.progressMap[item.id].position : (item.progress ? item.progress.position : 0));

    function launchWithStream(streamInfo) {
      closeDetailModal();
      var prevFocus = root.MavieSpatial ? root.MavieSpatial.getCurrent() : null;
      if (root.MavieSpatial) {
        root.MavieSpatial.pushBack(function () {
          root.MaviePlayer.close(false);
          return true;
        });
      }
      root.MaviePlayer.open(item, streamInfo, {
        onProgress: saveProgress,
        onRetry: function (it) { playItem(it, 0); },
        onZap: function (delta) {
          var liveList = getItemsByKind('live');
          if (liveList.length < 2) return;
          var idx = -1;
          var k;
          for (k = 0; k < liveList.length; k++) {
            if (liveList[k].id === item.id) { idx = k; break; }
          }
          var nextIdx = idx < 0 ? 0 : (idx + delta + liveList.length) % liveList.length;
          playItem(liveList[nextIdx], 0);
        },
        onClose: function () {
          stopCompanionSession();
          if (root.MavieSpatial && prevFocus) {
            root.MavieSpatial.focusElement(prevFocus);
          }
        }
      });
    }

    if (state.mode === 'companion' && apiBase() && !item.url) {
      showToast('Yayın hazırlanıyor…', false);
      httpJson(apiBase() + '/api/play', {
        method: 'POST',
        body: { id: item.id, mode: 'direct', start: resumeSec || 0 }
      }).then(function (res) {
        state.activeSessionId = res.sessionId || null;
        launchWithStream({
          url: resolveMediaUrl(res.url),
          type: res.type || (item.kind === 'live' ? 'hls' : 'file'),
          start: res.startOffset || resumeSec || 0,
          duration: res.duration || item.duration || 0
        });
      }).catch(function (err) {
        showToast('Oynatılamadı: ' + (err && err.message ? err.message : 'Sunucu hatası'), true);
      });
    } else if (item.url) {
      launchWithStream({
        url: item.url,
        type: /\.m3u8(?:[?#]|$)/i.test(item.url) || item.kind === 'live' ? 'hls' : 'file',
        start: resumeSec || 0,
        duration: item.duration || 0
      });
    } else {
      showToast('Bu içerik için oynatılabilir adres bulunamadı.', true);
    }
  }

  /* ---- Rendering Helpers ---- */
  function renderCardHtml(item, extraClass) {
    var img = posterUrl(item);
    var prog = state.progressMap[item.id] || item.progress;
    var pct = prog && prog.duration > 0 ? Math.min(100, Math.round((prog.position / prog.duration) * 100)) : 0;
    var badge = item.kind === 'live'
      ? '<span class="tv-card-badge live">CANLI</span>'
      : (item.rating > 0 ? '<span class="tv-card-badge">&#9733; ' + Number(item.rating).toFixed(1) + '</span>' : '');
    var meta = (item.year ? item.year + ' · ' : '') + (item.categoryName || 'Mavie');

    return '<button type="button" class="tv-card ' + (extraClass || '') + '" data-tv-focusable="true" data-action="open-item" data-id="' + esc(item.id) + '">'
      + '<div class="tv-card-poster">'
      + '<div class="tv-card-fallback">' + esc(item.name) + '</div>'
      + (img ? '<img src="' + esc(img) + '" alt="" data-tv-poster="1">' : '')
      + badge
      + (pct > 2 ? '<div class="tv-card-progress"><div class="tv-card-progress-fill" style="width:' + pct + '%"></div></div>' : '')
      + '</div>'
      + '<div class="tv-card-info">'
      + '<div class="tv-card-title">' + esc(item.name) + '</div>'
      + '<div class="tv-card-meta">' + esc(meta) + '</div>'
      + '</div>'
      + '</button>';
  }

  function renderRailHtml(title, list) {
    if (!list || list.length === 0) return '';
    var cards = [];
    var i;
    for (i = 0; i < Math.min(list.length, 24); i++) {
      cards.push(renderCardHtml(list[i]));
    }
    return '<section class="tv-section">'
      + '<div class="tv-section-head"><h2 class="tv-section-title">' + esc(title) + '</h2><span class="tv-section-count">' + list.length + ' içerik</span></div>'
      + '<div class="tv-rail-row">' + cards.join('') + '</div>'
      + '</section>';
  }

  function renderHome() {
    var hero = state.items[0] || root.MavieM3U.getDemoCatalog()[0];
    var heroImg = posterUrl(hero);
    var liveList = getItemsByKind('live');
    var vodList = getItemsByKind('vod');
    var seriesList = getItemsByKind('series');
    var favList = state.items.filter(isFavorite);
    var contList = state.mode === 'companion' ? state.continueWatching : buildStandaloneContinue();

    var html = '<section class="tv-hero">'
      + (heroImg ? '<div class="tv-hero-bg" style="background-image:url(\'' + esc(heroImg) + '\')"></div>' : '')
      + '<div class="tv-hero-shade"></div>'
      + '<div class="tv-hero-body">'
      + '<span class="tv-hero-kicker">' + (state.mode === 'companion' ? 'EV SUNUCUSU · ÖNE ÇIKAN' : 'MAVIE TV · ÖNE ÇIKAN') + '</span>'
      + '<h2 class="tv-hero-title">' + esc(hero.name) + '</h2>'
      + '<div class="tv-hero-meta">' + esc((hero.year ? hero.year + ' · ' : '') + (hero.categoryName || 'Mavie')) + '</div>'
      + '<p class="tv-hero-plot">' + esc(hero.plot || 'Kumandadan OK tuşuna basarak anında tam ekran izlemeye başlayın.') + '</p>'
      + '<div class="tv-hero-actions">'
      + '<button type="button" class="tv-btn tv-btn-primary" data-tv-focusable="true" data-action="play-item" data-id="' + esc(hero.id) + '">&#9654; Hemen İzle</button>'
      + '<button type="button" class="tv-btn tv-btn-secondary" data-tv-focusable="true" data-action="detail-item" data-id="' + esc(hero.id) + '">Ayrıntılar</button>'
      + '<button type="button" class="tv-btn tv-btn-secondary" data-tv-focusable="true" data-action="go-route" data-route="settings">QR / Liste Bağla</button>'
      + '</div></div></section>';

    html += renderRailHtml('İzlemeye Devam Et', contList);
    html += renderRailHtml('Canlı TV Kanalları', liveList);
    html += renderRailHtml('Filmler & Açık Sinema', vodList);
    html += renderRailHtml('Diziler', seriesList);
    html += renderRailHtml('Favorilerim', favList);
    return html;
  }

  function renderCategoryGrid(kind, emptyTitle, emptyDesc) {
    var all = getItemsByKind(kind);
    if (all.length === 0) {
      return '<div class="tv-empty"><h2>' + esc(emptyTitle) + '</h2><p>' + esc(emptyDesc) + '</p>'
        + '<button type="button" class="tv-btn tv-btn-primary" data-tv-focusable="true" data-action="go-route" data-route="settings">Ayarlar / Liste Bağla</button></div>';
    }
    var catSet = {};
    var cats = [];
    var i, item, cName;
    for (i = 0; i < all.length; i++) {
      cName = all[i].categoryName || 'Genel';
      if (!catSet[cName]) {
        catSet[cName] = 1;
        cats.push(cName);
      }
    }
    var filtered = state.activeCategory
      ? all.filter(function (x) { return (x.categoryName || 'Genel') === state.activeCategory; })
      : all;

    var chips = ['<button type="button" class="tv-chip' + (!state.activeCategory ? ' active' : '') + '" data-tv-focusable="true" data-action="filter-cat" data-cat="">Tümü (' + all.length + ')</button>'];
    for (i = 0; i < Math.min(cats.length, 14); i++) {
      chips.push('<button type="button" class="tv-chip' + (state.activeCategory === cats[i] ? ' active' : '') + '" data-tv-focusable="true" data-action="filter-cat" data-cat="' + esc(cats[i]) + '">' + esc(cats[i]) + '</button>');
    }

    var cards = [];
    for (i = 0; i < Math.min(filtered.length, 60); i++) {
      cards.push(renderCardHtml(filtered[i]));
    }
    return '<div class="tv-chips">' + chips.join('') + '</div><div class="tv-grid">' + cards.join('') + '</div>';
  }

  function renderSports() {
    if (state.sportsLoading) {
      return '<div class="tv-loading-box"><div class="tv-spinner"></div><p>Spor Ekranı maç takvimi yükleniyor…</p></div>';
    }
    var guide = state.sportsGuide;
    if (!guide || !Array.isArray(guide.events) || guide.events.length === 0) {
      return '<div class="tv-empty"><h2>Spor Ekranı</h2>'
        + '<p>Günün canlı maç ve yarış takvimini görmek için Ev Sunucusuna bağlanın veya yenileyin.</p>'
        + '<button type="button" class="tv-btn tv-btn-primary" data-tv-focusable="true" data-action="refresh-sports">Takvimi Yenile</button>'
        + '<button type="button" class="tv-btn tv-btn-secondary" data-tv-focusable="true" data-action="go-route" data-route="settings">Ev Sunucusu Bağla</button></div>';
    }

    var channels = guide.channels || {};
    var rows = [];
    var i, ev, firstCh, match, chBadge;
    for (i = 0; i < Math.min(guide.events.length, 40); i++) {
      ev = guide.events[i];
      firstCh = (ev.channels && ev.channels[0]) || '';
      match = firstCh && channels[firstCh] ? channels[firstCh] : null;
      chBadge = match
        ? '<span class="tv-sport-channel">&#9654; ' + esc(firstCh) + '</span>'
        : '<span class="tv-sport-channel">' + esc(firstCh || 'Yayın Bilgisi') + '</span>';

      rows.push('<button type="button" class="tv-sport-row" data-tv-focusable="true" data-action="' + (match ? 'play-sport' : 'noop-sport') + '" data-id="' + esc(match ? match.id : '') + '" data-ch="' + esc(firstCh) + '">'
        + '<div class="tv-sport-time">' + esc(ev.time || '--:--') + '</div>'
        + '<div class="tv-sport-main">'
        + '<div class="tv-sport-league">' + esc((ev.sport || '') + (ev.league ? ' · ' + ev.league : '')) + '</div>'
        + '<div class="tv-sport-title">' + esc(ev.title || '') + '</div>'
        + '</div>'
        + chBadge
        + '</button>');
    }
    return '<div class="tv-section-head"><h2 class="tv-section-title">Bugünün Maçları</h2>'
      + '<button type="button" class="tv-btn tv-btn-secondary tv-btn-small" data-tv-focusable="true" data-action="refresh-sports">Yenile</button></div>'
      + '<div class="tv-sports-list">' + rows.join('') + '</div>';
  }

  function renderFavorites() {
    var favs = state.items.filter(isFavorite);
    if (favs.length === 0) {
      return '<div class="tv-empty"><h2>Henüz Favoriniz Yok</h2><p>Herhangi bir film, dizi veya kanalın detay ekranından favorilere ekleyebilirsiniz.</p>'
        + '<button type="button" class="tv-btn tv-btn-primary" data-tv-focusable="true" data-action="go-route" data-route="home">Ana Sayfaya Dön</button></div>';
    }
    var cards = [];
    var i;
    for (i = 0; i < favs.length; i++) cards.push(renderCardHtml(favs[i]));
    return '<div class="tv-grid">' + cards.join('') + '</div>';
  }

  function renderSearch() {
    var keys = 'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ0123456789'.split('');
    var kb = [];
    var i;
    for (i = 0; i < keys.length; i++) {
      kb.push('<button type="button" class="tv-key" data-tv-focusable="true" data-action="kb-char" data-ch="' + keys[i] + '">' + keys[i] + '</button>');
    }
    kb.push('<button type="button" class="tv-key tv-key-wide" data-tv-focusable="true" data-action="kb-space">Boşluk</button>');
    kb.push('<button type="button" class="tv-key tv-key-wide" data-tv-focusable="true" data-action="kb-back">Sil</button>');
    kb.push('<button type="button" class="tv-key tv-key-wide" data-tv-focusable="true" data-action="kb-clear">Temizle</button>');

    var q = String(state.searchQuery || '').toLowerCase().trim();
    var matches = q
      ? state.items.filter(function (it) {
        return String(it.name || '').toLowerCase().indexOf(q) >= 0
          || String(it.categoryName || '').toLowerCase().indexOf(q) >= 0;
      })
      : state.items.slice(0, 12);

    var cards = [];
    for (i = 0; i < Math.min(matches.length, 36); i++) {
      cards.push(renderCardHtml(matches[i]));
    }

    return '<div class="tv-search-bar">'
      + '<input id="tvSearchInput" type="text" class="tv-input" value="' + esc(state.searchQuery) + '" placeholder="Film, dizi veya kanal ara…" data-tv-focusable="true">'
      + '</div>'
      + '<div class="tv-keyboard">' + kb.join('') + '</div>'
      + '<div class="tv-section-head"><h2 class="tv-section-title">' + (q ? 'Arama Sonuçları' : 'Önerilen İçerikler') + '</h2><span class="tv-section-count">' + matches.length + ' sonuç</span></div>'
      + (cards.length ? '<div class="tv-grid">' + cards.join('') + '</div>' : '<div class="tv-empty"><p>Eşleşen içerik bulunamadı.</p></div>');
  }

  function renderSettings() {
    var tvUrl = (state.tvInfo && state.tvInfo.tv_url)
      || (apiBase() ? apiBase() + '/tv' : 'http://192.168.1.35:8844/tv');
    var pairTarget = (state.tvInfo && state.tvInfo.web_url)
      || (apiBase() || tvUrl);
    var qrSvg = root.MavieQR ? root.MavieQR.toSvg(pairTarget, { quiet: 3 }) : '';
    var pairCode = (state.serverStatus && state.serverStatus.pairingCode) || '6 HANELİ KOD';
    var plat = root.MaviePlatform || { label: 'Universal Smart TV' };
    var engineName = root.MaviePlayer && root.MaviePlayer.hasSamsungAvPlay() ? 'Samsung AVPlay (Donanımsal)' : 'HLS.js / HTML5 Video';

    return '<div class="tv-settings-grid">'
      + '<section class="tv-panel">'
      + '<h2 class="tv-panel-title">Telefondan QR & 6 Haneli Kurulum</h2>'
      + '<p class="tv-panel-desc">Kumandayla uzun URL yazmanıza gerek yok. QR kodu telefonunuzla okutup aynı Wi-Fi ağındaki Mavie uygulamasından listenizi eşleştirin.</p>'
      + '<div class="tv-qr-row">'
      + '<div class="tv-qr-box" id="tvQrContainer">' + qrSvg + '</div>'
      + '<div class="tv-qr-copy">'
      + '<div class="tv-field-label">TV Erişim Adresi</div>'
      + '<div class="tv-panel-desc" style="margin-bottom:6px;color:#e2ecff;font-family:monospace;">' + esc(tvUrl) + '</div>'
      + '<div class="tv-code-pill">' + esc(pairCode) + '</div>'
      + '<div class="tv-btn-row"><button type="button" class="tv-btn tv-btn-primary tv-btn-small" data-tv-focusable="true" data-action="open-pair">6 Haneli Kod Gir</button></div>'
      + '</div></div></section>'

      + '<section class="tv-panel">'
      + '<h2 class="tv-panel-title">Ev Sunucusu (Companion Modu)</h2>'
      + '<p class="tv-panel-desc">Bilgisayarınızdaki Mavie sunucusuna bağlanarak yerel MKV/DTS filmlerinizi (FFmpeg) ve kütüphanenizi TV\'de izleyin.</p>'
      + '<label class="tv-field-label" for="tvServerUrlInput">Sunucu Adresi</label>'
      + '<div class="tv-field-row"><input id="tvServerUrlInput" type="text" class="tv-input" value="' + esc(state.serverUrl || apiBase() || 'http://192.168.1.35:8844') + '" placeholder="http://192.168.1.35:8844" data-tv-focusable="true"></div>'
      + '<div class="tv-btn-row">'
      + '<button type="button" class="tv-btn tv-btn-primary tv-btn-small" data-tv-focusable="true" data-action="connect-server">Bağlan ve Test Et</button>'
      + '<button type="button" class="tv-btn tv-btn-secondary tv-btn-small" data-tv-focusable="true" data-action="use-demo">Açık Sinema Demo</button>'
      + '</div></section>'

      + '<section class="tv-panel">'
      + '<h2 class="tv-panel-title">Bağımsız M3U / M3U8 (PC Kapalıyken)</h2>'
      + '<p class="tv-panel-desc">Doğrudan TV içinde çalışan bağımsız M3U oynatma listesi URL\'si yükleyin.</p>'
      + '<label class="tv-field-label" for="tvM3uUrlInput">M3U / M3U8 Adresi</label>'
      + '<div class="tv-field-row"><input id="tvM3uUrlInput" type="text" class="tv-input" value="' + esc(state.m3uUrl) + '" placeholder="https://ornek.com/playlist.m3u8" data-tv-focusable="true"></div>'
      + '<div class="tv-btn-row"><button type="button" class="tv-btn tv-btn-primary tv-btn-small" data-tv-focusable="true" data-action="load-m3u">M3U Listesini Yükle</button></div>'
      + '</section>'

      + '<section class="tv-panel">'
      + '<h2 class="tv-panel-title">Bağımsız Xtream Codes & Cihaz Bilgisi</h2>'
      + '<label class="tv-field-label" for="tvXtreamHost">Sunucu / Kullanıcı / Şifre</label>'
      + '<div class="tv-field-row"><input id="tvXtreamHost" type="text" class="tv-input" value="' + esc(state.xtreamHost) + '" placeholder="http://sunucu:8080" data-tv-focusable="true"></div>'
      + '<div class="tv-field-row"><input id="tvXtreamUser" type="text" class="tv-input" value="' + esc(state.xtreamUser) + '" placeholder="Kullanıcı adı" data-tv-focusable="true" style="margin-right:10px;"><input id="tvXtreamPass" type="password" class="tv-input" value="" placeholder="Şifre" data-tv-focusable="true"></div>'
      + '<div class="tv-btn-row"><button type="button" class="tv-btn tv-btn-primary tv-btn-small" data-tv-focusable="true" data-action="load-xtream">Xtream Yükle</button></div>'
      + '<ul class="tv-info-list" style="margin-top:16px;">'
      + '<li><strong>Platform:</strong> ' + esc(plat.label) + '</li>'
      + '<li><strong>Oynatıcı Motoru:</strong> ' + esc(engineName) + '</li>'
      + '<li><strong>Çalışma Modu:</strong> ' + (state.mode === 'companion' ? 'Ev Sunucusu (Companion)' : 'Bağımsız (Standalone)') + '</li>'
      + '<li><strong>Yasal Not:</strong> Mavie tamamen ücretsiz, hesapsız kişisel bir oynatıcıdır; telifli yayın barındırmaz.</li>'
      + '</ul></section>'
      + '</div>';
  }

  function renderView(focusTarget) {
    var content = byId('tvContent');
    var titleEl = byId('tvPageTitle');
    if (!content) return;

    if (titleEl) titleEl.textContent = ROUTE_TITLES[state.route] || 'Mavie TV';

    var navBtns = document.querySelectorAll('.tv-nav-item');
    var i;
    for (i = 0; i < navBtns.length; i++) {
      var isAct = navBtns[i].getAttribute('data-route') === state.route;
      if (isAct) navBtns[i].classList.add('active');
      else navBtns[i].classList.remove('active');
    }

    var html = '';
    if (state.route === 'home') {
      html = renderHome();
    } else if (state.route === 'live') {
      html = renderCategoryGrid('live', 'Canlı TV Kanalı Yok', 'Ayarlar bölümünden Ev Sunucunuza bağlanın veya kendi M3U/Xtream listenizi ekleyin.');
    } else if (state.route === 'vod') {
      html = renderCategoryGrid('vod', 'Film Bulunamadı', 'Açık Sinema demo filmlerini veya kendi kütüphanenizi Ayarlar ekranından yükleyebilirsiniz.');
    } else if (state.route === 'series') {
      html = renderCategoryGrid('series', 'Dizi Bulunamadı', 'M3U/Xtream veya Ev Sunucusu bağlayarak dizilerinizi sezon ve bölümlere göre izleyebilirsiniz.');
    } else if (state.route === 'sports') {
      html = renderSports();
    } else if (state.route === 'favorites') {
      html = renderFavorites();
    } else if (state.route === 'search') {
      html = renderSearch();
    } else if (state.route === 'settings') {
      html = renderSettings();
    }

    content.innerHTML = html;
    content.scrollTop = 0;
    updateStatusBar();

    if (state.route === 'search') {
      var sIn = byId('tvSearchInput');
      if (sIn) {
        sIn.addEventListener('input', function () {
          state.searchQuery = sIn.value;
          renderView('keep-search');
        });
      }
    }

    if (root.MavieSpatial) {
      if (focusTarget === 'keep-search') {
        var inp = byId('tvSearchInput');
        if (inp) root.MavieSpatial.focusElement(inp);
      } else if (focusTarget === 'content') {
        root.MavieSpatial.focusFirst(content);
      } else if (focusTarget === 'rail') {
        root.MavieSpatial.focusElement(byId('nav-' + state.route));
      }
    }
  }

  function fetchSportsGuide(force) {
    if (state.mode !== 'companion' || !apiBase()) {
      state.sportsGuide = null;
      renderView('content');
      return;
    }
    state.sportsLoading = true;
    renderView();
    httpJson(apiBase() + '/api/sports' + (force ? '?refresh=1' : '')).then(function (guide) {
      state.sportsGuide = guide;
      state.sportsLoading = false;
      if (state.route === 'sports') renderView('content');
    }).catch(function () {
      state.sportsLoading = false;
      if (state.route === 'sports') renderView('content');
    });
  }

  function navigate(route, focusTarget) {
    state.route = ROUTE_TITLES[route] ? route : 'home';
    state.activeCategory = '';
    if (state.route === 'sports' && !state.sportsGuide && !state.sportsLoading) {
      fetchSportsGuide(false);
    } else {
      renderView(focusTarget || 'content');
    }
  }

  /* ---- Modals ---- */
  function openDetailModal(item) {
    var modal = byId('tvDetailModal');
    var body = byId('tvDetailBody');
    if (!modal || !body || !item) return;

    var prevFocus = root.MavieSpatial ? root.MavieSpatial.getCurrent() : null;
    var fav = isFavorite(item);
    var img = posterUrl(item);

    function renderDetail(detailItem, seasons) {
      var epHtml = '';
      if (Array.isArray(seasons) && seasons.length > 0) {
        var rows = [];
        var s, e, season, ep;
        for (s = 0; s < seasons.length; s++) {
          season = seasons[s];
          var eps = season.episodes || [];
          for (e = 0; e < eps.length; e++) {
            ep = eps[e];
            rows.push('<button type="button" class="tv-episode-row" data-tv-focusable="true" data-action="play-ep" data-id="' + esc(ep.id) + '">'
              + '<span>S' + esc(season.season || (s + 1)) + 'B' + esc(ep.episode || (e + 1)) + ' · ' + esc(ep.name || 'Bölüm') + '</span>'
              + '<span>&#9654; İzle</span></button>');
          }
        }
        epHtml = '<h3 class="tv-section-title" style="margin-bottom:12px;">Bölümler</h3><div class="tv-episode-list">' + rows.join('') + '</div>';
      }

      body.innerHTML = '<div class="tv-detail-top">'
        + '<div class="tv-detail-poster">' + (img ? '<img src="' + esc(img) + '" alt="">' : '<div class="tv-card-fallback">' + esc(detailItem.name) + '</div>') + '</div>'
        + '<div class="tv-detail-meta">'
        + '<h2 id="detailTitle" class="tv-modal-title">' + esc(detailItem.name) + '</h2>'
        + '<div class="tv-hero-meta">' + esc((detailItem.year ? detailItem.year + ' · ' : '') + (detailItem.categoryName || 'Mavie') + (detailItem.rating > 0 ? ' · ★ ' + Number(detailItem.rating).toFixed(1) : '')) + '</div>'
        + '<p class="tv-modal-desc">' + esc(detailItem.plot || 'Bu içerik hakkında ek özet bilgisi bulunmuyor.') + '</p>'
        + '<div class="tv-modal-actions">'
        + (detailItem.kind !== 'series' ? '<button type="button" class="tv-btn tv-btn-primary" data-tv-focusable="true" data-action="play-item" data-id="' + esc(detailItem.id) + '">&#9654; Oynat</button>' : '')
        + '<button type="button" class="tv-btn tv-btn-secondary" data-tv-focusable="true" data-action="toggle-fav" data-id="' + esc(detailItem.id) + '">' + (fav ? '&#9829; Favoride' : '&#9825; Favoriye Ekle') + '</button>'
        + '<button type="button" class="tv-btn tv-btn-secondary" data-tv-focusable="true" data-action="close-detail">Kapat</button>'
        + '</div></div></div>'
        + epHtml;

      modal.hidden = false;
      if (root.MavieSpatial) root.MavieSpatial.focusFirst(modal);
    }

    renderDetail(item, []);
    if (root.MavieSpatial) {
      root.MavieSpatial.pushBack(function () {
        closeDetailModal(prevFocus);
        return true;
      });
    }

    if (state.mode === 'companion' && apiBase() && item.kind === 'series') {
      httpJson(apiBase() + '/api/items/' + encodeURIComponent(item.id)).then(function (data) {
        if (!modal.hidden) {
          var eps = [];
          var seasons = data.seasons || [];
          var s, e;
          for (s = 0; s < seasons.length; s++) {
            for (e = 0; e < (seasons[s].episodes || []).length; e++) {
              eps.push(seasons[s].episodes[e]);
            }
          }
          for (e = 0; e < eps.length; e++) {
            if (!findItemById(eps[e].id)) state.items.push(eps[e]);
          }
          renderDetail(data.item || item, seasons);
        }
      }).catch(function () {});
    }
  }

  function closeDetailModal(restoreEl) {
    var modal = byId('tvDetailModal');
    if (modal) modal.hidden = true;
    if (root.MavieSpatial && restoreEl) root.MavieSpatial.focusElement(restoreEl);
  }

  function openPairModal() {
    var modal = byId('tvPairModal');
    var err = byId('tvPairError');
    var inp = byId('tvPairCodeInput');
    if (!modal) return;
    if (err) err.hidden = true;
    if (inp) inp.value = '';
    modal.hidden = false;
    if (root.MavieSpatial) {
      root.MavieSpatial.pushBack(function () {
        modal.hidden = true;
        return true;
      });
      root.MavieSpatial.focusElement(inp || byId('tvPairSubmitBtn'));
    }
  }

  function openExitModal() {
    var modal = byId('tvExitModal');
    if (!modal || !modal.hidden) return;
    modal.hidden = false;
    if (root.MavieSpatial) {
      root.MavieSpatial.pushBack(function () {
        modal.hidden = true;
        root.MavieSpatial.focusElement(byId('nav-' + state.route));
        return true;
      });
      root.MavieSpatial.focusElement(byId('tvExitNoBtn'));
    }
  }

  function handleActionClick(target) {
    var node = target;
    while (node && node !== document.body && node.nodeType === 1) {
      if (node.classList && node.classList.contains('tv-nav-item')) {
        navigate(node.getAttribute('data-route'), 'content');
        return;
      }
      var action = node.getAttribute ? node.getAttribute('data-action') : null;
      if (action) {
        var id = node.getAttribute('data-id');
        if (action === 'open-item') {
          var it = findItemById(id);
          if (it) {
            if (it.kind === 'live') playItem(it, 0);
            else openDetailModal(it);
          }
        } else if (action === 'play-item' || action === 'play-ep' || action === 'play-sport') {
          var pIt = findItemById(id);
          if (pIt) playItem(pIt);
        } else if (action === 'noop-sport') {
          showToast('Bu kanal listenizde eşleşmedi: ' + (node.getAttribute('data-ch') || ''), true);
        } else if (action === 'detail-item') {
          openDetailModal(findItemById(id));
        } else if (action === 'toggle-fav') {
          var fIt = findItemById(id);
          toggleFavorite(fIt);
          openDetailModal(fIt);
        } else if (action === 'close-detail') {
          if (root.MavieSpatial) root.MavieSpatial.triggerBack();
        } else if (action === 'go-route') {
          navigate(node.getAttribute('data-route'), 'content');
        } else if (action === 'filter-cat') {
          state.activeCategory = node.getAttribute('data-cat') || '';
          renderView('content');
        } else if (action === 'refresh-sports') {
          fetchSportsGuide(true);
        } else if (action === 'kb-char') {
          state.searchQuery += node.getAttribute('data-ch') || '';
          renderView();
        } else if (action === 'kb-space') {
          state.searchQuery += ' ';
          renderView();
        } else if (action === 'kb-back') {
          state.searchQuery = state.searchQuery.slice(0, -1);
          renderView();
        } else if (action === 'kb-clear') {
          state.searchQuery = '';
          renderView();
        } else if (action === 'open-pair') {
          openPairModal();
        } else if (action === 'use-demo') {
          loadDemoCatalog();
          showToast('Açık Sinema demo kataloğu yüklendi.', false);
          navigate('home', 'content');
        } else if (action === 'connect-server') {
          var urlIn = byId('tvServerUrlInput');
          var rawUrl = urlIn ? urlIn.value.trim() : '';
          connectCompanion(rawUrl, false).then(function (ok) {
            if (ok) navigate('home', 'content');
          }).catch(function (err) {
            showToast('Bağlantı hatası: ' + (err && err.message ? err.message : 'Erişilemedi'), true);
          });
        } else if (action === 'load-m3u') {
          var m3uIn = byId('tvM3uUrlInput');
          var m3uUrl = m3uIn ? m3uIn.value.trim() : '';
          if (!/^https?:\/\//i.test(m3uUrl)) {
            showToast('Geçerli bir http/https M3U adresi girin.', true);
            return;
          }
          showToast('M3U listesi indiriliyor…', false);
          httpText(m3uUrl).then(function (txt) {
            var parsed = root.MavieM3U.parseM3U(txt);
            if (!parsed.items.length) throw new Error('Oynatılabilir yayın bulunamadı.');
            state.mode = 'standalone';
            state.m3uUrl = m3uUrl;
            state.items = parsed.items;
            state.sourceLabel = 'M3U (' + parsed.items.length + ' yayın)';
            savePersisted();
            showToast(parsed.items.length + ' içerik yüklendi!', false);
            navigate('home', 'content');
          }).catch(function (err) {
            showToast('M3U yüklenemedi: ' + (err && err.message ? err.message : 'Hata'), true);
          });
        } else if (action === 'load-xtream') {
          var hEl = byId('tvXtreamHost');
          var uEl = byId('tvXtreamUser');
          var pEl = byId('tvXtreamPass');
          var host = hEl ? hEl.value.trim() : '';
          var user = uEl ? uEl.value.trim() : '';
          var pass = pEl ? pEl.value : '';
          if (!host || !user || !pass) {
            showToast('Xtream sunucu, kullanıcı adı ve şifre gerekli.', true);
            return;
          }
          showToast('Xtream kataloğu yükleniyor…', false);
          var liveUrl = root.MavieM3U.buildXtreamApiUrl(host, user, pass, 'get_live_streams');
          var vodUrl = root.MavieM3U.buildXtreamApiUrl(host, user, pass, 'get_vod_streams');
          Promise.all([
            httpJson(liveUrl).catch(function () { return []; }),
            httpJson(vodUrl).catch(function () { return []; })
          ]).then(function (res) {
            var liveItems = root.MavieM3U.normalizeXtreamStreams(host, user, pass, 'live', res[0], {});
            var vodItems = root.MavieM3U.normalizeXtreamStreams(host, user, pass, 'vod', res[1], {});
            var combined = liveItems.concat(vodItems);
            if (!combined.length) throw new Error('Xtream listesi boş döndü.');
            state.mode = 'standalone';
            state.xtreamHost = host;
            state.xtreamUser = user;
            state.items = combined;
            state.sourceLabel = 'Xtream (' + combined.length + ' içerik)';
            savePersisted();
            showToast(combined.length + ' Xtream içeriği yüklendi!', false);
            navigate('home', 'content');
          }).catch(function (err) {
            showToast('Xtream hatası: ' + (err && err.message ? err.message : 'Bağlanamadı'), true);
          });
        }
        return;
      }
      node = node.parentNode;
    }
  }

  function bindGlobalModals() {
    var exitNo = byId('tvExitNoBtn');
    var exitYes = byId('tvExitYesBtn');
    var pairCancel = byId('tvPairCancelBtn');
    var pairSubmit = byId('tvPairSubmitBtn');

    if (exitNo) {
      exitNo.addEventListener('click', function () {
        if (root.MavieSpatial) root.MavieSpatial.triggerBack();
      });
    }
    if (exitYes) {
      exitYes.addEventListener('click', function () {
        if (root.MaviePlatform && typeof root.MaviePlatform.exitApp === 'function') {
          root.MaviePlatform.exitApp();
        } else {
          byId('tvExitModal').hidden = true;
          showToast('Tarayıcı sekmesini kapatarak çıkabilirsiniz.', false);
        }
      });
    }
    if (pairCancel) {
      pairCancel.addEventListener('click', function () {
        if (root.MavieSpatial) root.MavieSpatial.triggerBack();
      });
    }
    if (pairSubmit) {
      pairSubmit.addEventListener('click', function () {
        var inp = byId('tvPairCodeInput');
        var errEl = byId('tvPairError');
        var code = inp ? inp.value.trim() : '';
        var base = apiBase();
        if (!base) {
          if (errEl) { errEl.textContent = 'Önce Ayarlar bölümünden sunucu adresini girin.'; errEl.hidden = false; }
          return;
        }
        httpJson(base + '/api/pair', { method: 'POST', body: { code: code } }).then(function () {
          byId('tvPairModal').hidden = true;
          return connectCompanion(base, false);
        }).then(function () {
          navigate('home', 'content');
        }).catch(function (err) {
          if (errEl) {
            errEl.textContent = (err && err.message) || 'Eşleştirme kodu doğrulanamadı.';
            errEl.hidden = false;
          }
        });
      });
    }
  }

  function bootstrap() {
    loadPersisted();
    if (!state.items || state.items.length === 0) {
      state.items = root.MavieM3U.getDemoCatalog();
    }

    updateClock();
    setInterval(updateClock, 30000);

    if (root.MaviePlayer) root.MaviePlayer.bindUiControls();
    bindGlobalModals();

    document.addEventListener('click', function (ev) {
      handleActionClick(ev.target);
    });

    // CSP-safe poster fallback without inline onerror handlers
    document.addEventListener('error', function (ev) {
      var target = ev && ev.target;
      if (target && target.tagName === 'IMG' && target.getAttribute('data-tv-poster') === '1') {
        target.style.display = 'none';
      }
    }, true);

    if (root.MavieSpatial) {
      root.MavieSpatial.init({
        onRootBack: function () {
          if (state.route !== 'home') {
            navigate('home', 'rail');
          } else {
            openExitModal();
          }
        },
        onMediaKey: function (keyCode) {
          if (root.MaviePlayer && root.MaviePlayer.isOpen()) {
            return root.MaviePlayer.handleMediaKey(keyCode);
          }
          return false;
        }
      });
    }

    // Immediate first render so zero blank screens ever appear
    renderView('content');

    // Auto-detect Companion mode when served from Mavie server or saved LAN URL
    var autoBase = '';
    if (root.location && /^https?:$/i.test(root.location.protocol)) {
      autoBase = root.location.protocol + '//' + root.location.host;
    } else if (state.serverUrl) {
      autoBase = state.serverUrl;
    }

    if (autoBase) {
      connectCompanion(autoBase, true).then(function (ok) {
        if (ok) renderView('content');
      }).catch(function () {
        updateStatusBar();
      });
    }
  }

  root.MavieTV = {
    bootstrap: bootstrap,
    navigate: navigate,
    getState: function () { return state; }
  };

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
      bootstrap();
    }
  }
})(typeof window !== 'undefined' ? window : this);
