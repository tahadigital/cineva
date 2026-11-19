"""Local catalog discovery and optional official TMDB enrichment for Vrelio.

Viewing history and media source credentials never leave the device.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import functools
import gzip
import http.client
import json
import math
import os
import re
import ssl
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

TMDB_API = 'https://api.themoviedb.org/3'
TMDB_IMG = 'https://image.tmdb.org/t/p/w780'
TMDB_GENRES = {
    28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy', 80: 'Crime',
    99: 'Documentary', 18: 'Drama', 10751: 'Family', 14: 'Fantasy', 27: 'Horror',
    9648: 'Mystery', 10749: 'Romance', 878: 'Sci-Fi', 53: 'Thriller',
    10759: 'Action', 10765: 'Sci-Fi',
}
GENRES = {
    'Action': 'Aksiyon', 'Adventure': 'Macera', 'Animation': 'Animasyon',
    'Comedy': 'Komedi', 'Crime': 'Suç', 'Documentary': 'Belgesel',
    'Drama': 'Dram', 'Family': 'Aile', 'Fantasy': 'Fantastik',
    'Horror': 'Korku', 'Mystery': 'Gizem', 'Romance': 'Romantik',
    'Sci-Fi': 'Bilim Kurgu', 'Thriller': 'Gerilim',
}
_lock = threading.Lock()
_running = False
_attempt = 0
_memory = None
TLS = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)
_PREFIX_RE = re.compile(r'^\s*(?:tr|en|us|uk|de|vip)\s*[:|]\s*')
_TECH_RE = re.compile(r'\b(?:19|20)\d{2}\b|\b(?:tr|en|trsub|eng|turkce|altyazili|dublaj|uhd|fhd|hd|4k|1080p|720p)\b')
_SPLIT_RE = re.compile(r'\s+[|/]\s+|\s+\([^)]*\)\s*')
_NONALNUM_RE = re.compile(r'[^a-z0-9]')


@functools.lru_cache(maxsize=60000)
def key(text):
    text = str(text or '').replace('ı', 'i').replace('İ', 'i').lower()
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    text = _PREFIX_RE.sub('', text)
    text = _TECH_RE.sub(' ', text)
    return _NONALNUM_RE.sub('', text)


def titles(name):
    return {k for s in [name, *_SPLIT_RE.split(name)] if len(k := key(s)) >= 2}


def _tmdb_key(explicit=None):
    return (explicit or os.environ.get('VRELIO_TMDB_API_KEY') or os.environ.get('CINEVA_TMDB_API_KEY') or '').strip()


def get_json(url, timeout=12):
    request = urllib.request.Request(url, headers={'User-Agent': 'Vrelio/3.0', 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(request, context=TLS, timeout=timeout) as response:
        try:
            raw = response.read(5 * 1024 * 1024 + 1)
        except http.client.IncompleteRead as error:
            raw = error.partial
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError('Discovery response too large')
        if response.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError('Discovery response too large')
        return json.loads(raw.decode('utf-8'))


def parse_tmdb_results(rows, media_type, page_offset=0):
    entries = []
    for idx, row in enumerate(rows or []):
        if not isinstance(row, dict) or not row.get('id'):
            continue
        kind = 'series' if (row.get('media_type') or media_type) == 'tv' else 'vod'
        title = row.get('title') or row.get('name') or ''
        original = row.get('original_title') or row.get('original_name') or ''
        if not title and not original:
            continue
        released = row.get('release_date') or row.get('first_air_date') or ''
        genre_names = [TMDB_GENRES[g] for g in row.get('genre_ids', []) if g in TMDB_GENRES]
        entry = {
            'id': f'tmdb:{kind}:{row["id"]}',
            'moviedb_id': str(row['id']),
            'kind': kind,
            'name': original or title,
            'aliases': [t for t in (title, original) if t],
            'genres': genre_names,
            'year': released[:4],
            'released': released[:10],
            'globalRank': page_offset + idx + 1,
            'popularity': float(row.get('popularity') or 0),
        }
        if row.get('poster_path'):
            entry['poster'] = TMDB_IMG + row['poster_path']
        if row.get('backdrop_path'):
            entry['background'] = TMDB_IMG + row['backdrop_path']
        entries.append(entry)
    return entries


def refresh(directory, api_key=None, language='tr-TR'):
    global _running, _memory
    path = Path(directory) / 'discovery-public.json'
    key_value = _tmdb_key(api_key)
    try:
        if not key_value:
            return
        old = _memory or {}
        metas = {m['id']: m for m in old.get('metas', []) if m.get('id')}
        charts = []
        week_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
        specs = [('movie', 'trending/movie/week'), ('tv', 'trending/tv/week'), ('movie', 'movie/popular'), ('tv', 'tv/popular')]

        def fetch(spec):
            mtype, endpoint = spec
            qs = urllib.parse.urlencode({'api_key': key_value, 'language': language})
            data = get_json(f'{TMDB_API}/{endpoint}?{qs}')
            return mtype, endpoint, data.get('results', [])

        successes = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for future in [pool.submit(fetch, spec) for spec in specs]:
                try:
                    mtype, endpoint, rows = future.result()
                    parsed = parse_tmdb_results(rows, mtype)
                    for item in parsed:
                        metas[item['id']] = item
                        if endpoint.startswith('trending/'):
                            charts.append({**item, 'rank': item['globalRank'], 'week': week_date})
                    successes += 1
                except Exception:
                    pass
        if not successes:
            return
        result = {
            'version': 2,
            'updatedAt': time.time(),
            'metas': list(metas.values()),
            'charts': charts or old.get('charts', []),
        }
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False))
        temp.replace(path)
        with _lock:
            _memory = result
    finally:
        with _lock:
            _running = False


def snapshot(directory, enabled=True):
    global _memory, _running, _attempt
    with _lock:
        if _memory is None:
            try:
                _memory = json.loads((Path(directory) / 'discovery-public.json').read_text())
            except (OSError, ValueError):
                _memory = {}
        if enabled and _tmdb_key() and time.time() - _memory.get('updatedAt', 0) > 21600 and not _running and time.time() - _attempt > 900:
            _running = True
            _attempt = time.time()
            threading.Thread(target=refresh, args=(directory,), daemon=True).start()
        return dict(_memory)


_genre_names = {key(k): k for k in GENRES} | {key(v): k for k, v in GENRES.items()}


@functools.lru_cache(maxsize=2000)
def _genre_set(raw):
    return frozenset(_genre_names.get(key(v), v.strip()) for v in re.split(r'[,/|]', raw) if v.strip())


def genres(item):
    raw = item.get('genres') or item.get('genre') or ''
    return _genre_set(raw if isinstance(raw, str) else ','.join(raw))


def build(catalog, history, feed, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    candidates = [dict(i) for i in catalog if i['kind'] in ('vod', 'series')]
    index = {}
    for item in candidates:
        for title in titles(item['name']):
            index.setdefault((item['kind'], title), []).append(item)
    identities = {}
    for item in candidates:
        for field in ('imdbId', 'tmdbId'):
            if item.get(field):
                identities[(item['kind'], str(item[field]))] = item

    def match(meta):
        options = {
            i['id']: i
            for title in set().union(*(titles(n) for n in [meta.get('name', ''), *meta.get('aliases', [])]))
            for i in index.get((meta['kind'], title), [])
        }
        for field in ('imdb_id', 'moviedb_id'):
            item = identities.get((meta['kind'], str(meta.get(field, ''))))
            if item:
                options[item['id']] = item
        year = str(meta.get('year') or meta.get('releaseInfo') or '')[:4]
        valid = [i for i in options.values() if not year.isdigit() or not str(i.get('year', '')).isdigit() or i['year'] == year or meta['kind'] == 'series']
        return max(valid, key=lambda i: (bool(i.get('poster')), i.get('rating', 0)), default=None)

    for meta in [*feed.get('metas', []), *feed.get('charts', [])]:
        item = match(meta)
        if item is None:
            continue
        if genres(meta):
            item['genres'] = sorted(genres(meta))
        if meta.get('released'):
            item['releaseDate'] = meta['released'][:10]
        if meta.get('globalRank'):
            item['globalRank'] = meta['globalRank']
        if not item.get('backdrop'):
            item['backdrop'] = meta.get('background', '')
        if not item.get('poster'):
            item['poster'] = meta.get('poster', '')
        if not item.get('year'):
            item['year'] = str(meta.get('year') or meta.get('releaseInfo') or '')[:4]

    unique = {}
    for item in candidates:
        token = (item['kind'], key(item['name']), item.get('year', ''))
        if token not in unique or len(genres(item)) > len(genres(unique[token])):
            unique[token] = item
    candidates = list(unique.values())
    by_id = {i['id']: i for i in catalog}
    by_id.update({i['id']: i for i in candidates})

    watched, weights, seeds = set(), {}, []
    for h in history:
        p = h.get('progress') or {}
        target = h.get('parentId') or h['id']
        item = by_id.get(target)
        if not item:
            continue
        if p.get('position', 0) > 0 or p.get('completed'):
            watched.add(target)
        if p.get('position', 0) < 60 and not p.get('completed') and not h.get('favorite'):
            continue
        affinity = 1 + min(1, p.get('position', 0) / max(1, p.get('duration', 0))) + 2 * bool(h.get('favorite'))
        try:
            days = max(0, (today - dt.date.fromisoformat(p.get('updatedAt', '')[:10])).days)
        except ValueError:
            days = 30
        affinity *= math.pow(.5, days / 90)
        for genre in genres(item):
            weights[genre] = weights.get(genre, 0) + affinity
        if genres(item):
            seeds.append(item)

    def score(i):
        return sum(weights.get(g, 0) for g in genres(i)) + min(10, float(i.get('rating') or 0)) * .08 + 1 / (1 + float(i.get('globalRank', 999)))

    shelves = []

    def shelf(i, title, rows, subtitle=''):
        rows = list(rows)[:20]
        if rows:
            shelves.append({'id': i, 'title': title, 'subtitle': subtitle, 'items': rows})

    fresh = [
        i for i in candidates
        if str(i.get('year', '')).isdigit() and today.year - 1 <= int(i['year']) <= today.year
        and ((today - dt.timedelta(days=365)).isoformat() <= i['releaseDate'] <= today.isoformat() if i.get('releaseDate') else int(i['year']) == today.year)
    ]
    fresh.sort(key=lambda i: (i.get('releaseDate') or i.get('year', ''), -i.get('globalRank', 999)), reverse=True)

    week = max((e.get('week', '') for e in feed.get('charts', [])), default='')
    chart_fresh = bool(week and 0 <= (today - dt.date.fromisoformat(week)).days <= 21)

    ranked = sorted(candidates, key=score, reverse=True)
    personal_by_kind = {'vod': [], 'series': []}
    by_genre = {}
    for i in ranked:
        gs = genres(i)
        if not gs:
            continue
        k = i['kind']
        if i['id'] not in watched and len(personal_by_kind.get(k, ())) < 20:
            personal_by_kind[k].append(i)
        for g in gs:
            bucket = by_genre.setdefault((k, g), [])
            if len(bucket) < 20:
                bucket.append(i)

    for kind, label in [('vod', 'Filmler'), ('series', 'Diziler')]:
        if chart_fresh:
            rows, used = [], set()
            for meta in sorted(feed.get('charts', []), key=lambda m: m.get('rank', 99)):
                if meta['kind'] != kind or meta.get('week') != week:
                    continue
                item = match(meta)
                if item and item['id'] not in used:
                    rows.append(item)
                    used.add(item['id'])
            shelf('trending-' + kind, 'Güncel Popüler ' + label, rows, 'Haftalık trend listesi · ' + week)
        shelf('new-' + kind, 'Yeni Çıkan ' + label, [i for i in fresh if i['kind'] == kind], 'Yayın yılı ve çıkış tarihine göre')
        shelf(
            'for-you-' + kind,
            'Sana Özel ' + label if weights else 'Keşfet: ' + label,
            personal_by_kind[kind],
            (seeds[0]['name'] + ' ve izleme geçmişine göre') if seeds else 'Türler ve güncel seçkilerle',
        )

    for genre, label in GENRES.items():
        for kind, name in [('vod', 'Filmleri'), ('series', 'Dizileri')]:
            shelf('genre-' + kind + '-' + genre, label + ' ' + name, by_genre.get((kind, genre), []))

    films = [i for i in fresh if i['kind'] == 'vod' and i['id'] not in watched and i.get('poster')][:4]
    shows = [i for i in fresh if i['kind'] == 'series' and i['id'] not in watched and i.get('poster')][:4]
    showcase = [i for pair in __import__('itertools').zip_longest(films, shows) for i in pair if i]
    if not showcase:
        fallback_vod = [i for i in ranked if i['kind'] == 'vod' and i.get('poster')][:4]
        fallback_series = [i for i in ranked if i['kind'] == 'series' and i.get('poster')][:4]
        showcase = [i for pair in __import__('itertools').zip_longest(fallback_vod, fallback_series) for i in pair if i]

    sources = [{'name': 'TMDB', 'url': 'https://www.themoviedb.org'}] if feed.get('metas') or feed.get('charts') else []
    return {'shelves': shelves, 'showcase': showcase, 'updatedAt': feed.get('updatedAt'), 'sources': sources, 'personalized': bool(weights)}
