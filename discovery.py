"""Public catalog discovery (Cinemeta, Netflix Türkiye Top 10, optional TMDB) for Mavie.

Only public catalog/chart metadata is downloaded. Viewing history and media source
credentials never leave the device; matching and personalized ranking run 100% locally.
Recommendations never manufacture playable IDs: every item comes from the local library.
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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ZONE = ZoneInfo('Europe/Istanbul')
except ZoneInfoNotFoundError:
    ZONE = dt.timezone(dt.timedelta(hours=3))

CINEMETA = 'https://v3-cinemeta.strem.io'
NETFLIX = 'https://www.netflix.com/tudum/top10/turkey'
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
_EXTRA_GENRE_ALIASES = {
    'dramalar': 'Drama',
    'drama': 'Drama',
    'komediler': 'Comedy',
    'gerilimler': 'Thriller',
    'korkular': 'Horror',
    'korkufilmleri': 'Horror',
    'belgeseller': 'Documentary',
    'aksiyonvemacera': 'Action',
    'bilimkurguvefantastik': 'Sci-Fi',
    'bilimkurgu': 'Sci-Fi',
    'scifi': 'Sci-Fi',
    'sciencefiction': 'Sci-Fi',
    'sucdizileri': 'Crime',
    'sucfilmleri': 'Crime',
    'romantikfilmler': 'Romance',
    'romantikdiziler': 'Romance',
    'ailevecocuk': 'Family',
    'cocukveaile': 'Family',
    'animasyonlar': 'Animation',
    'anime': 'Animation',
    'fantastikfilmler': 'Fantasy',
    'gizemli': 'Mystery',
}
_lock = threading.Lock()
_running = False
_attempt = 0
_memory = None
TLS = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)
_PREFIX_RE = re.compile(r'^\s*(?:tr|en|us|uk|de|fr|es|vip)\s*[:|]\s*')
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
    return (explicit or os.environ.get('MAVIE_TMDB_API_KEY') or os.environ.get('CINEVA_TMDB_API_KEY') or '').strip()


def get(url, timeout=18):
    request = urllib.request.Request(
        url,
        headers={'User-Agent': 'curl/8.7.1', 'Accept': '*/*', 'Accept-Encoding': 'gzip'},
    )
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
        return raw.decode('utf-8')


def get_json(url, timeout=12):
    return json.loads(get(url, timeout=timeout))


def netflix_entries(page):
    match = re.search(r"netflix\.reactContext\.models\.graphql\s*=\s*JSON\.parse\('(.*?)'\);", page, re.S)
    if not match:
        raise ValueError('Netflix chart format changed')
    data = json.loads(re.sub(r"\\([\\'])", r'\1', match[1]))['data']
    entries = {}
    for value in data.values():
        if not isinstance(value, dict) or not value.get('top10Video'):
            continue
        info, chart = value['top10Video'], value['top10']
        parent = info.get('parentShow') or {}
        title = parent.get('title') or info.get('title', '')
        kind = 'series' if chart['category'] != 'MOVIES' else 'vod'
        entry = {
            'name': title,
            'kind': kind,
            'year': str(info.get('releaseYear') or ''),
            'rank': chart['weeklyRank'],
            'week': chart['weekEndDate'],
            'netflixId': parent.get('videoId') or info.get('videoId'),
            'source': 'netflix',
        }
        entries[kind, title, entry['week']] = entry
    return list(entries.values())


def localize_chart(entry):
    try:
        page = get('https://www.netflix.com/tr/title/' + str(entry['netflixId']))
        blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S)
        for block in blocks:
            info = json.loads(block)
            if isinstance(info, dict) and info.get('name'):
                entry['aliases'] = [info['name']]
                entry['genre'] = info.get('genre', '')
                break
    except Exception:
        pass
    return entry


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
        now = dt.datetime.now(ZONE).date()
        requests = [
            (kind, catalog, extra)
            for kind in ('movie', 'series')
            for catalog, extra in [('top', ''), ('year', f'/genre={now.year}'), ('year', f'/genre={now.year - 1}')]
        ]
        requests += [
            (kind, 'top', f'/genre={genre}')
            for kind in ('movie', 'series')
            for genre in ('Comedy', 'Drama', 'Action', 'Crime', 'Sci-Fi', 'Horror', 'Romance', 'Animation')
        ]

        def fetch_cinemeta(spec):
            kind, catalog, extra = spec
            data = json.loads(get(f'{CINEMETA}/catalog/{kind}/{catalog}{extra}.json'))
            return kind, catalog, extra, data.get('metas', [])

        old = _memory or {}
        metas = {m['id']: m for m in old.get('metas', []) if isinstance(m, dict) and m.get('id')}
        successes = 0
        has_cinemeta = False
        has_tmdb = False

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for future in [pool.submit(fetch_cinemeta, spec) for spec in requests]:
                try:
                    kind, catalog, extra, rows = future.result()
                    for index, m in enumerate(rows):
                        if not isinstance(m, dict) or not m.get('id') or not m.get('name'):
                            continue
                        item = dict(m)
                        item['kind'] = 'vod' if kind == 'movie' else 'series'
                        item['globalRank'] = (
                            index + 1 if catalog == 'top' and not extra
                            else metas.get(item['id'], {}).get('globalRank', 999)
                        )
                        metas[item['id']] = item
                    successes += 1
                    has_cinemeta = True
                except Exception:
                    pass

        charts = []
        for url in (NETFLIX, NETFLIX + '/tv'):
            try:
                charts.extend(netflix_entries(get(url)))
            except Exception:
                pass
        if charts:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                charts = list(pool.map(localize_chart, charts))

        if key_value:
            week_date = now.isoformat()
            specs = [
                ('movie', 'trending/movie/week'),
                ('tv', 'trending/tv/week'),
                ('movie', 'movie/popular'),
                ('tv', 'tv/popular'),
            ]

            def fetch_tmdb(spec):
                mtype, endpoint = spec
                qs = urllib.parse.urlencode({'api_key': key_value, 'language': language})
                data = get_json(f'{TMDB_API}/{endpoint}?{qs}')
                return mtype, endpoint, data.get('results', [])

            tmdb_charts = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                for future in [pool.submit(fetch_tmdb, spec) for spec in specs]:
                    try:
                        mtype, endpoint, rows = future.result()
                        parsed = parse_tmdb_results(rows, mtype)
                        for item in parsed:
                            metas[item['id']] = item
                            if endpoint.startswith('trending/'):
                                tmdb_charts.append({**item, 'rank': item['globalRank'], 'week': week_date, 'source': 'tmdb'})
                        successes += 1
                        has_tmdb = True
                    except Exception:
                        pass
            if not charts and tmdb_charts:
                charts = tmdb_charts

        if not successes and not charts:
            return
        chart_source = (
            'netflix' if any(c.get('source') == 'netflix' or c.get('netflixId') for c in charts)
            else ('tmdb' if charts else old.get('chartSource', 'netflix'))
        )
        result = {
            'version': 3,
            'updatedAt': time.time(),
            'metas': list(metas.values()),
            'charts': charts or old.get('charts', []),
            'chartSource': chart_source,
            'hasCinemeta': has_cinemeta or bool(old.get('hasCinemeta')),
            'hasTmdb': has_tmdb or bool(old.get('hasTmdb')),
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
        if enabled and time.time() - _memory.get('updatedAt', 0) > 21600 and not _running and time.time() - _attempt > 900:
            _running = True
            _attempt = time.time()
            threading.Thread(target=refresh, args=(directory,), daemon=True).start()
        return dict(_memory)


_genre_names = (
    {key(k): k for k in GENRES}
    | {key(v): k for k, v in GENRES.items()}
    | _EXTRA_GENRE_ALIASES
)


@functools.lru_cache(maxsize=2000)
def _genre_set(raw):
    out = []
    seen = set()
    for v in re.split(r'[,/|&]', raw):
        part = v.strip()
        if not part:
            continue
        canonical = _genre_names.get(key(part))
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return tuple(out)


def genres(item):
    raw = item.get('genres') or item.get('genre') or ''
    return _genre_set(raw if isinstance(raw, str) else ','.join(raw))


def build(catalog, history, feed, today=None):
    today = today or dt.datetime.now(ZONE).date()
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
        valid = [
            i for i in options.values()
            if not year.isdigit() or not str(i.get('year', '')).isdigit() or i['year'] == year or meta['kind'] == 'series'
        ]
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
        return (
            sum(weights.get(g, 0) for g in genres(i))
            + min(10, float(i.get('rating') or 0)) * .08
            + 1 / (1 + float(i.get('globalRank', 999)))
        )

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

    charts = feed.get('charts', [])
    week = max((e.get('week', '') for e in charts), default='')
    chart_fresh = bool(week and 0 <= (today - dt.date.fromisoformat(week)).days <= 21)
    is_tmdb_chart = feed.get('chartSource') == 'tmdb' or (
        bool(charts) and all(c.get('source') == 'tmdb' for c in charts)
    )

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

    top_genre_keys = sorted(weights, key=lambda g: weights[g], reverse=True)
    top_genre_labels = [GENRES[g] for g in top_genre_keys if g in GENRES][:3]

    for kind, label in [('vod', 'Filmler'), ('series', 'Diziler')]:
        if chart_fresh:
            rows, used = [], set()
            for meta in sorted(charts, key=lambda m: m.get('rank', 99)):
                if meta['kind'] != kind or meta.get('week') != week:
                    continue
                item = match(meta)
                if item and item['id'] not in used:
                    rows.append(item)
                    used.add(item['id'])
            chart_subtitle = (
                'Haftalık trend listesi · ' + week
                if is_tmdb_chart
                else 'Netflix Türkiye Top 10 · ' + week + ' haftası'
            )
            shelf('turkey-' + kind, 'Türkiye’de Popüler ' + label, rows, chart_subtitle)
        shelf('new-' + kind, 'Yeni Çıkan ' + label, [i for i in fresh if i['kind'] == kind], 'Yayın yılı ve çıkış tarihine göre')
        if seeds:
            genre_hint = (' · ' + ', '.join(top_genre_labels[:2])) if top_genre_labels else ''
            personal_sub = seeds[0]['name'] + ' ve izleme geçmişine göre' + genre_hint
        else:
            personal_sub = 'Türler ve güncel keşif listeleriyle'
        shelf(
            'for-you-' + kind,
            'Sana Özel ' + label if weights else 'Keşfet: ' + label,
            personal_by_kind[kind],
            personal_sub,
        )

    # Order genre shelves dynamically by the user's watched genre affinity,
    # keeping canonical GENRES order as tie-breaker for unwatched genres.
    ordered_genres = sorted(
        GENRES.items(),
        key=lambda pair: (-weights.get(pair[0], 0.0), list(GENRES).index(pair[0])),
    )
    for genre, label in ordered_genres:
        promoted_sub = 'İzleme geçmişine göre öne çıkarıldı' if weights.get(genre, 0.0) > 0 else ''
        for kind, name in [('vod', 'Filmleri'), ('series', 'Dizileri')]:
            shelf('genre-' + kind + '-' + genre, label + ' ' + name, by_genre.get((kind, genre), []), promoted_sub)

    films = [i for i in fresh if i['kind'] == 'vod' and i['id'] not in watched and i.get('poster')][:4]
    shows = [i for i in fresh if i['kind'] == 'series' and i['id'] not in watched and i.get('poster')][:4]
    showcase = [i for pair in __import__('itertools').zip_longest(films, shows) for i in pair if i]
    if not showcase:
        fallback_vod = [i for i in ranked if i['kind'] == 'vod' and i.get('poster')][:4]
        fallback_series = [i for i in ranked if i['kind'] == 'series' and i.get('poster')][:4]
        showcase = [i for pair in __import__('itertools').zip_longest(fallback_vod, fallback_series) for i in pair if i]

    sources = [
        {'name': 'Cinemeta', 'url': CINEMETA + '/manifest.json'},
        {'name': 'Netflix Türkiye Top 10', 'url': NETFLIX},
    ]
    if feed.get('hasTmdb') or is_tmdb_chart:
        sources.append({'name': 'TMDB', 'url': 'https://www.themoviedb.org'})
    return {
        'shelves': shelves,
        'showcase': showcase,
        'updatedAt': feed.get('updatedAt'),
        'sources': sources,
        'personalized': bool(weights),
        'topGenres': top_genre_labels,
    }
