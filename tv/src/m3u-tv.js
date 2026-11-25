/* Mavie TV — ES2018 / ES5-Safe M3U, Xtream & Open-License Demo Catalog Module
 * Works standalone inside Samsung Tizen (.wgt), LG webOS (.ipk), and /tv browsers.
 */
(function (root) {
  'use strict';

  var VOD_EXTS = { mp4: 1, mkv: 1, avi: 1, mov: 1, webm: 1, m4v: 1, flv: 1 };

  var DEMO_CATALOG = [
    {
      id: 'vod:demo_bbb',
      providerId: 'demo_bbb',
      kind: 'vod',
      name: 'Big Buck Bunny (Demo · 1080p)',
      poster: 'https://peach.blender.org/wp-content/uploads/poster_bunny_small.jpg',
      backdrop: 'https://peach.blender.org/wp-content/uploads/poster_bunny_small.jpg',
      categoryId: 'demo_anim',
      categoryName: 'Açık Sinema / Demo',
      year: '2008',
      rating: 8.2,
      extension: 'mp4',
      duration: 596,
      genre: 'Animasyon, Komedi, Aile',
      plot: 'Blender Vakfı tarafından Creative Commons Attribution 3.0 lisansıyla sunulan açık kaynaklı kısa animasyon filmi.',
      url: 'https://distribution.bbb3d.renderfarming.net/video/mp4/bbb_sunflower_1080p_30fps_normal.mp4'
    },
    {
      id: 'vod:demo_sintel',
      providerId: 'demo_sintel',
      kind: 'vod',
      name: 'Sintel (Demo · 1080p)',
      poster: 'https://archive.org/download/Sintel/Poster.jpg',
      backdrop: 'https://archive.org/download/Sintel/Poster.jpg',
      categoryId: 'demo_anim',
      categoryName: 'Açık Sinema / Demo',
      year: '2010',
      rating: 8.5,
      extension: 'mp4',
      duration: 888,
      genre: 'Animasyon, Fantastik, Macera',
      plot: 'Genç bir gezginin yavru ejderhasını arayışını konu alan Blender açık kaynak kısa filmi.',
      url: 'https://archive.org/download/Sintel/sintel-2048-stereo.mp4'
    },
    {
      id: 'vod:demo_tears',
      providerId: 'demo_tears',
      kind: 'vod',
      name: 'Tears of Steel (Demo · Bilim Kurgu)',
      poster: 'https://archive.org/download/Tears-of-Steel/tos-poster.jpg',
      backdrop: 'https://archive.org/download/Tears-of-Steel/tos-poster.jpg',
      categoryId: 'demo_scifi',
      categoryName: 'Bilim Kurgu / Demo',
      year: '2012',
      rating: 7.9,
      extension: 'mp4',
      duration: 734,
      genre: 'Bilim Kurgu, Aksiyon',
      plot: 'Amsterdam’da geçen, Creative Commons açık lisanslı bilim kurgu kısa filmi.',
      url: 'https://archive.org/download/Tears-of-Steel/tears_of_steel_720p.mp4'
    },
    {
      id: 'vod:demo_elephants',
      providerId: 'demo_elephants',
      kind: 'vod',
      name: 'Elephants Dream (Demo · Open Movie)',
      poster: 'https://download.blender.org/ED/cover.jpg',
      backdrop: 'https://download.blender.org/ED/cover.jpg',
      categoryId: 'demo_anim',
      categoryName: 'Açık Sinema / Demo',
      year: '2006',
      rating: 7.5,
      extension: 'mp4',
      duration: 653,
      genre: 'Animasyon, Bilim Kurgu',
      plot: 'Dünyanın ilk açık kaynaklı 3D kısa animasyon filmi (Orange Open Movie Project).',
      url: 'https://archive.org/download/ElephantsDream/ed_1024_512kb.mp4'
    }
  ];

  function hashId(str) {
    var h = 2166136261;
    var i;
    var s = String(str || '');
    for (i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
    }
    return h.toString(36);
  }

  function splitExtinfTitle(line) {
    var inQuotes = false;
    var escaped = false;
    var i, ch;
    for (i = 0; i < line.length; i++) {
      ch = line.charAt(i);
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === '\\' && inQuotes) {
        escaped = true;
        continue;
      }
      if (ch === '"') {
        inQuotes = !inQuotes;
        continue;
      }
      if (ch === ',' && !inQuotes) {
        return line.slice(i + 1).trim();
      }
    }
    return '';
  }

  function extractAttrs(line) {
    var attrs = {};
    var re = /([A-Za-z0-9_-]+)="([^"]*)"/g;
    var m;
    while ((m = re.exec(line)) !== null) {
      attrs[m[1].toLowerCase()] = m[2];
    }
    return attrs;
  }

  function detectExtension(url) {
    var m = /\.([a-z0-9]{2,5})(?:[?#]|$)/i.exec(String(url || ''));
    return m ? m[1].toLowerCase() : '';
  }

  function classifyKind(url, groupTitle, title, ext) {
    var g = String(groupTitle || '').toLowerCase();
    var u = String(url || '').toLowerCase();
    var t = String(title || '').toLowerCase();
    if (/\/series\//i.test(u) || /s\d{1,2}\s*e\d{1,2}/i.test(t) || g.indexOf('dizi') >= 0 || g.indexOf('series') >= 0) {
      return 'series';
    }
    if (/\/movie\//i.test(u) || VOD_EXTS[ext] || g.indexOf('film') >= 0 || g.indexOf('vod') >= 0 || g.indexOf('sinema') >= 0 || g.indexOf('movie') >= 0) {
      return 'vod';
    }
    return 'live';
  }

  function parseM3U(rawText) {
    var clean = String(rawText || '').replace(/^\uFEFF/, '');
    var lines = clean.split(/\r?\n/);
    var epgUrl = '';
    var items = [];
    var currentMeta = null;
    var i, line, attrs, title, ext, kind, groupName, id;

    for (i = 0; i < lines.length; i++) {
      line = lines[i].trim();
      if (!line) continue;

      if (line.indexOf('#EXTM3U') === 0) {
        attrs = extractAttrs(line);
        epgUrl = attrs['url-tvg'] || attrs['x-tvg-url'] || epgUrl;
        continue;
      }

      if (line.indexOf('#EXTINF') === 0) {
        attrs = extractAttrs(line);
        title = splitExtinfTitle(line) || attrs['tvg-name'] || 'Adsız Yayın';
        currentMeta = {
          title: title,
          logo: attrs['tvg-logo'] || '',
          group: attrs['group-title'] || 'Genel',
          tvgId: attrs['tvg-id'] || ''
        };
        continue;
      }

      if (line.charAt(0) === '#') continue;

      if (/^https?:\/\//i.test(line)) {
        if (!currentMeta) {
          currentMeta = { title: 'Yayın ' + (items.length + 1), logo: '', group: 'Genel', tvgId: '' };
        }
        ext = detectExtension(line);
        kind = classifyKind(line, currentMeta.group, currentMeta.title, ext);
        groupName = currentMeta.group || (kind === 'live' ? 'Canlı TV' : (kind === 'series' ? 'Diziler' : 'Filmler'));
        id = kind + ':' + hashId(line + '|' + currentMeta.title);
        items.push({
          id: id,
          providerId: id,
          kind: kind,
          name: currentMeta.title,
          poster: currentMeta.logo,
          backdrop: currentMeta.logo,
          categoryId: 'cat_' + hashId(kind + ':' + groupName),
          categoryName: groupName,
          year: '',
          rating: 0,
          extension: ext || (kind === 'live' ? 'm3u8' : 'mp4'),
          url: line,
          tvgId: currentMeta.tvgId,
          plot: ''
        });
        currentMeta = null;
      }
    }

    return {
      epgUrl: epgUrl,
      items: items
    };
  }

  function normalizeBaseHost(host) {
    var clean = String(host || '').trim().replace(/\/+$/, '');
    if (!clean) return '';
    if (!/^https?:\/\//i.test(clean)) {
      clean = 'http://' + clean;
    }
    return clean;
  }

  function buildXtreamApiUrl(host, username, password, action) {
    var base = normalizeBaseHost(host);
    var url = base + '/player_api.php?username=' + encodeURIComponent(username) + '&password=' + encodeURIComponent(password);
    if (action) url += '&action=' + encodeURIComponent(action);
    return url;
  }

  function normalizeXtreamStreams(host, username, password, kind, rows, categoryMap) {
    var base = normalizeBaseHost(host);
    var list = Array.isArray(rows) ? rows : [];
    var cats = categoryMap || {};
    var out = [];
    var i, row, sid, ext, streamUrl, catId, catName;

    for (i = 0; i < list.length; i++) {
      row = list[i] || {};
      sid = String(row.stream_id || row.series_id || i);
      catId = String(row.category_id || 'genel');
      catName = cats[catId] || (kind === 'live' ? 'Canlı TV' : (kind === 'series' ? 'Diziler' : 'Filmler'));
      ext = String(row.container_extension || (kind === 'live' ? 'm3u8' : 'mp4')).replace(/^\./, '');

      if (kind === 'live') {
        streamUrl = base + '/live/' + encodeURIComponent(username) + '/' + encodeURIComponent(password) + '/' + encodeURIComponent(sid) + '.m3u8';
      } else if (kind === 'vod') {
        streamUrl = base + '/movie/' + encodeURIComponent(username) + '/' + encodeURIComponent(password) + '/' + encodeURIComponent(sid) + '.' + ext;
      } else {
        streamUrl = '';
      }

      out.push({
        id: kind + ':' + sid,
        providerId: sid,
        kind: kind,
        name: String(row.name || row.title || 'İsimsiz'),
        poster: String(row.stream_icon || row.cover || ''),
        backdrop: String(row.stream_icon || row.cover || ''),
        categoryId: catId,
        categoryName: catName,
        year: String(row.year || '').slice(0, 4),
        rating: Number(row.rating_5based ? Number(row.rating_5based) * 2 : (row.rating || 0)) || 0,
        extension: ext,
        url: streamUrl,
        plot: String(row.plot || '')
      });
    }
    return out;
  }

  function getDemoCatalog() {
    return DEMO_CATALOG.slice();
  }

  var api = {
    parseM3U: parseM3U,
    getDemoCatalog: getDemoCatalog,
    normalizeBaseHost: normalizeBaseHost,
    buildXtreamApiUrl: buildXtreamApiUrl,
    normalizeXtreamStreams: normalizeXtreamStreams
  };

  root.MavieM3U = api;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : this);
