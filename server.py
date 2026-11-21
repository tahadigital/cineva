#!/usr/bin/env python3
"""Mavie: local personal media, M3U/Xtream/XMLTV EPG catalog, state and playback service."""
from __future__ import annotations
import argparse, base64, collections, contextlib, datetime as dt, hashlib, html, http.cookies
import ipaddress, json, math, mimetypes, os, re, secrets, signal, socket, sqlite3, sys
import threading, time, unicodedata, ssl, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playback import PlaybackManager, BITMAP_SUBTITLES, _infer_language as infer_subtitle_language
import discovery
import local_media
import m3u
import sports


def configure_utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding='utf-8', errors='replace')


configure_utf8_stdio()

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA = Path(os.environ.get('MAVIE_DATA_DIR') or os.environ.get('CINEVA_DATA_DIR') or os.environ.get('AKIS_DATA_DIR') or str(ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
with contextlib.suppress(OSError):
    os.chmod(DATA, 0o700)
with contextlib.suppress(OSError):
    os.umask(0o077)
DB = DATA / 'state.sqlite3'
CONFIG_FILE = DATA / 'config.json'
PUBLIC = ROOT / 'public'
MAX_JSON = 12 * 1024 * 1024
UA = 'VLC/3.0.21 LibVLC/3.0.21'
KINDS = ('live', 'vod', 'series')
ID_RE = re.compile(r'^(live|vod|series|episode):[A-Za-z0-9_-]{1,100}$')


class PlaybackError(RuntimeError):
    def __init__(self, message, mode=None, code=None):
        super().__init__(message)
        self.mode = mode
        self.code = code


def stamp(): return dt.datetime.now(dt.timezone.utc).isoformat()
def number(v, default=0):
    try:
        n = float(v)
        return n if math.isfinite(n) else default
    except (ValueError, TypeError, OverflowError): return default

def fold(s):
    s = str(s or '').translate(str.maketrans({'ı': 'i', 'İ': 'i'})).casefold()
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))

def string(s, length=500): return html.unescape(str(s or ''))[:length]

def duration_seconds(value):
    if isinstance(value, str) and ':' in value:
        parts = value.split(':')
        if len(parts) <= 3:
            total = 0
            for part in parts: total = total * 60 + number(part)
            return total
    return number(value)


def codec_metadata(info):
    video = info.get('video') if isinstance(info.get('video'), dict) else {}
    audio = info.get('audio') if isinstance(info.get('audio'), dict) else {}
    return {'videoCodec': string(video.get('codec_name'), 40).lower(),
            'audioCodec': string(audio.get('codec_name'), 40).lower(),
            'pixelFormat': string(video.get('pix_fmt'), 40).lower()}


class DatabaseConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()


def connect():
    c = sqlite3.connect(DB, timeout=20, factory=DatabaseConnection)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def initialize():
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, kind TEXT NOT NULL, provider_id TEXT NOT NULL,
          name TEXT NOT NULL, search TEXT NOT NULL, poster TEXT DEFAULT '', category_id TEXT DEFAULT '',
          category_name TEXT DEFAULT '', year TEXT DEFAULT '', rating REAL DEFAULT 0, extension TEXT DEFAULT '',
          added REAL DEFAULT 0, extra TEXT DEFAULT '{}');
        CREATE INDEX IF NOT EXISTS items_kind_category ON items(kind,category_id);
        CREATE INDEX IF NOT EXISTS items_added ON items(kind,added DESC);
        CREATE INDEX IF NOT EXISTS items_name ON items(kind,name);
        CREATE INDEX IF NOT EXISTS items_parent ON items(kind,json_extract(extra,'$.parentId'));
        CREATE TABLE IF NOT EXISTS categories(id TEXT NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL,PRIMARY KEY(id,kind));
        CREATE TABLE IF NOT EXISTS favorites(item_id TEXT PRIMARY KEY,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS progress(item_id TEXT PRIMARY KEY,position REAL NOT NULL,duration REAL NOT NULL,completed INTEGER DEFAULT 0,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS playlists(id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS playlist_items(playlist_id TEXT NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,item_id TEXT NOT NULL,position INTEGER NOT NULL,PRIMARY KEY(playlist_id,item_id));
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS media_tracks(item_id TEXT PRIMARY KEY,data TEXT NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS track_preferences(item_id TEXT PRIMARY KEY,data TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS devices(token_hash TEXT PRIMARY KEY,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT NOT NULL,avatar_color TEXT NOT NULL,is_kids INTEGER DEFAULT 0,pin_hash TEXT DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profile_snapshots(profile_id TEXT PRIMARY KEY,data TEXT NOT NULL);
        INSERT OR IGNORE INTO profiles VALUES('default','Ana Profil','#7C3AED',0,'',datetime('now'));
        ''')
    os.chmod(DB, 0o600)


def meta_get(key, default=None):
    with connect() as c: r = c.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    if not r: return default
    try: return json.loads(r[0])
    except (ValueError, TypeError): return default


def meta_set(key, value):
    with connect() as c: c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', (key, json.dumps(value)))


def load_config():
    try: return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError): return {}


def save_config(c):
    tmp = CONFIG_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(c, ensure_ascii=False))
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_FILE)


def validate_host(value):
    u = urllib.parse.urlsplit(str(value).strip())
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('Sunucu adresini http:// veya https:// ile girin.')
    try: _ = u.port
    except ValueError: raise ValueError('Sunucu portu geçersiz.') from None
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path.rstrip('/'), '', ''))


def safe_public_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise ValueError('Geçersiz kaynak adresi.')
    try:
        addresses = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == 'https' else 80), type=socket.SOCK_STREAM)
        if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('Yerel ağ adresi kaynak olarak kullanılamaz.')
    except socket.gaierror: raise ValueError('Kaynak sunucusu bulunamadı.') from None
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


TLS_CONTEXT = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if Path('/etc/ssl/cert.pem').exists() else None)
OPENER = urllib.request.build_opener(SafeRedirect(), urllib.request.HTTPSHandler(context=TLS_CONTEXT))


def remote(url, timeout=35, headers=None):
    safe_public_url(url)
    return OPENER.open(urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})}), timeout=timeout)


class Provider:
    def __init__(self, config): self.config = config
    @property
    def mode(self):
        if self.config.get('type') == 'demo': return 'demo'
        if self.config.get('type') == 'local' and self.config.get('localDir'): return 'local'
        if self.config.get('type') == 'm3u' and self.config.get('m3uUrl'): return 'm3u'
        if all(self.config.get(k) for k in ('host', 'username', 'password')): return 'xtream'
        return 'none'
    @property
    def configured(self): return self.mode != 'none'
    def api(self, action=None, **kwargs):
        if self.mode != 'xtream': raise ValueError('Bu işlem yalnızca Xtream sunucu bağlantısında kullanılabilir.')
        q = {'username': self.config['username'], 'password': self.config['password']}
        if action: q['action'] = action
        q.update(kwargs)
        try:
            with remote(self.config['host'] + '/player_api.php?' + urllib.parse.urlencode(q), timeout=60) as r:
                payload = r.read(200 * 1024 * 1024 + 1)
                if len(payload) > 200 * 1024 * 1024: raise ValueError('Sunucu kataloğu çok büyük.')
                return json.loads(payload)
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError('Sunucuya ulaşılamadı. Ağ bağlantısını kontrol edip yeniden deneyin.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError('Sunucu geçerli katalog verisi göndermedi.') from None
    def account(self):
        if self.mode == 'demo':
            return {'status': 'Demo', 'expires': None, 'maxConnections': 1, 'activeConnections': 0}
        if self.mode in ('m3u', 'local'):
            return {'status': 'Active', 'expires': None, 'maxConnections': 1, 'activeConnections': 0}
        d = self.api()
        u = d.get('user_info', {}) if isinstance(d, dict) else {}
        if str(u.get('auth')) != '1': raise ValueError('Kullanıcı adı veya şifresi doğrulanamadı.')
        exp = number(u.get('exp_date'))
        return {'status': string(u.get('status')), 'expires': dt.datetime.fromtimestamp(exp, dt.timezone.utc).isoformat() if exp else None,
                'maxConnections': int(number(u.get('max_connections'), 1)), 'activeConnections': int(number(u.get('active_cons')))}
    def source(self, row, hls=False):
        try: extra = json.loads(row['extra'])
        except (ValueError, TypeError): extra = {}
        local_path = extra.get('localPath')
        if isinstance(local_path, str) and local_path:
            return 'local://' + local_path
        direct_url = extra.get('sourceUrl')
        if isinstance(direct_url, str) and direct_url.startswith(('http://', 'https://')):
            return direct_url
        if self.mode != 'xtream': raise ValueError('Bu içerik için doğrudan yayın adresi bulunamadı.')
        kind = row['kind']
        folder = {'live': 'live', 'vod': 'movie', 'episode': 'series'}.get(kind)
        if not folder: raise ValueError('Dizi sayfasından bir bölüm seçin.')
        ext = 'm3u8' if kind == 'live' and hls else ('ts' if kind == 'live' else (row['extension'] or 'mp4'))
        ext = ext if re.fullmatch(r'[A-Za-z0-9]{1,8}', ext) else 'mp4'
        return '/'.join([self.config['host'], folder, urllib.parse.quote(self.config['username'], safe=''), urllib.parse.quote(self.config['password'], safe=''), urllib.parse.quote(row['provider_id'], safe='') + '.' + ext])


provider = Provider(load_config())
sync_lock = threading.Lock()
sync_state = {'syncing': False, 'error': None}
play_lock = threading.Lock()
resource_lock = threading.RLock()
media_sessions = {}
internal_sources = {}
play_clients = {}
latest_play_request = 0
multiview_slot_requests = {}
playback = None
HTTP_PORT = 8844
PAIR_CODE = f'{secrets.randbelow(1000000):06d}'
pair_attempts = collections.defaultdict(list)
image_locks = [threading.Lock() for _ in range(16)]


def normalize_item(d, kind, cats, parent=None):
    pid = string(d.get('series_id') if kind == 'series' else d.get('stream_id', d.get('id')), 100)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', pid): return None
    name = string(d.get('name') or d.get('title') or f'İsimsiz {pid}')
    cat = string(d.get('category_id'), 100)
    if parent: cat = parent['category_id']
    inf = d.get('info') if isinstance(d.get('info'), dict) else {}
    poster = string(d.get('stream_icon') or d.get('cover') or inf.get('movie_image') or (parent['poster'] if parent else ''), 3000)
    year = string(d.get('year') or (d.get('releaseDate') or d.get('release_date') or '')[:4], 10)
    if not re.fullmatch(r'\d{4}', year):
        match = re.search(r'\b((?:19|20)\d{2})\b', name)
        year = match[1] if match else ''
    extra = {'duration': duration_seconds(inf.get('duration_secs') or inf.get('duration') or d.get('duration')),
             'plot': string(d.get('plot') or inf.get('plot'), 12000), 'genre': string(d.get('genre') or inf.get('genre')),
             'cast': string(d.get('cast') or inf.get('cast'), 2000), 'director': string(d.get('director') or inf.get('director'))}
    tmdb = string(d.get('tmdb') or d.get('tmdb_id') or inf.get('tmdb_id') or inf.get('tmdb'), 40)
    imdb = string(d.get('imdb_id') or d.get('imdb') or inf.get('imdb_id') or inf.get('imdb'), 40)
    if tmdb: extra['tmdbId'] = tmdb
    if imdb: extra['imdbId'] = imdb
    extra.update(codec_metadata(inf))
    if parent: extra.update({'parentId': parent['id'], 'season': int(number(d.get('season'))), 'episode': int(number(d.get('episode_num'))), 'seriesName': parent['name']})
    return (f'{kind}:{pid}', kind, pid, name, fold(name), poster, cat, cats.get(cat, parent['category_name'] if parent else 'Diğer'),
            year, max(0, min(10, number(d.get('rating') or inf.get('rating')))), string(d.get('container_extension') or ('m3u8' if kind == 'live' else 'mp4'), 12),
            number(d.get('added') or d.get('last_modified')), json.dumps(extra, ensure_ascii=False))


UPSERT_ITEM = '''INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,provider_id=excluded.provider_id,name=excluded.name,search=excluded.search,poster=excluded.poster,category_id=excluded.category_id,category_name=excluded.category_name,year=excluded.year,rating=excluded.rating,extension=excluded.extension,added=excluded.added,extra=excluded.extra'''


def sync_catalog():
    if not sync_lock.acquire(blocking=False): return
    sync_state.update(syncing=True, error=None)
    try:
        allrows, catrows = [], []
        if provider.mode == 'demo':
            account = provider.account()
            seen_cats = {}
            for item in m3u.DEMO_CATALOG:
                cid, cname, kind = item['category_id'], item['category_name'], item['kind']
                seen_cats[(cid, kind)] = cname
                extra = {**item['extra'], 'sourceUrl': item['url']}
                allrows.append((item['id'], kind, item['provider_id'], item['name'], fold(item['name']),
                                item['poster'], cid, cname, item['year'], item['rating'], item['extension'],
                                time.time(), json.dumps(extra, ensure_ascii=False)))
            catrows = [(cid, kind, cname) for (cid, kind), cname in seen_cats.items()]
        elif provider.mode == 'local':
            account = provider.account()
            scanned = local_media.scan_local_folder(provider.config['localDir'])
            catrows = [(cid, 'vod', cname) for cid, cname in scanned['categories'].items()]
            for item in scanned['items']:
                extra = {'localPath': item['localPath'], 'subtitles': item['subtitles']}
                allrows.append((item['id'], 'vod', item['provider_id'], item['name'], fold(item['name']),
                                '', item['category_id'], item['category_name'], item['year'], 0.0,
                                item['extension'], item['added'], json.dumps(extra, ensure_ascii=False)))
        elif provider.mode == 'm3u':
            account = provider.account()
            with remote(provider.config['m3uUrl'], timeout=45) as r:
                raw = r.read(30 * 1024 * 1024 + 1)
            if len(raw) > 30 * 1024 * 1024: raise ValueError('M3U listesi çok büyük.')
            parsed = m3u.parse_m3u(raw.decode('utf-8-sig', errors='replace'))
            if parsed['epgUrl'] and not provider.config.get('epgUrl'):
                provider.config['discoveredEpgUrl'] = parsed['epgUrl']
                save_config(provider.config)
            seen_cats = {}
            now_ts = time.time()
            for item in parsed['items']:
                cid, cname, kind = item['category_id'], item['category_name'], item['kind']
                seen_cats[(cid, kind)] = cname
                extra = {'sourceUrl': item['url'], 'tvgId': item.get('tvg_id', '')}
                allrows.append((item['id'], kind, item['provider_id'], item['name'], fold(item['name']),
                                item['poster'], cid, cname, '', 0.0, item['extension'],
                                now_ts, json.dumps(extra, ensure_ascii=False)))
            catrows = [(cid, kind, cname) for (cid, kind), cname in seen_cats.items()]
        else:
            account = provider.account()
            if fold(account['status']) != 'active': raise ValueError('Hesap aktif görünmüyor. Sağlayıcınızla kontrol edin.')
            for kind in KINDS:
                prefix = {'live': 'live', 'vod': 'vod', 'series': 'series'}[kind]
                cs = provider.api('get_' + prefix + '_categories')
                if not isinstance(cs, list): raise ValueError('Sunucu kategorileri alınamadı. Mevcut katalog korundu.')
                cats = {string(x.get('category_id'), 100): string(x.get('category_name')) for x in cs if isinstance(x, dict)}
                catrows.extend((cid, kind, name) for cid, name in cats.items())
                action = {'live': 'get_live_streams', 'vod': 'get_vod_streams', 'series': 'get_series'}[kind]
                rows = provider.api(action)
                if not isinstance(rows, list): raise ValueError('Sunucu kataloğu alınamadı. Mevcut katalog korundu.')
                for d in rows:
                    if isinstance(d, dict):
                        row = normalize_item(d, kind, cats)
                        if row: allrows.append(row)
        with connect() as c:
            # Atomic replacement; favorites/progress/list references survive refreshes.
            c.execute("DELETE FROM items WHERE kind != 'episode'")
            c.execute('DELETE FROM categories')
            c.executemany('INSERT OR REPLACE INTO categories VALUES(?,?,?)', catrows)
            c.executemany(UPSERT_ITEM, allrows)
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('catalog_updated', json.dumps(stamp())))
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('account', json.dumps(account)))
    except Exception as e:
        sync_state['error'] = str(e) if isinstance(e, (ValueError, RuntimeError)) else 'Katalog güncellenemedi. Mevcut içerikler korundu.'
    finally:
        sync_state['syncing'] = False
        sync_lock.release()


def launch_sync():
    if not sync_state['syncing']: threading.Thread(target=sync_catalog, daemon=True, name='catalog-sync').start()


ITEM_SELECT = '''SELECT i.*,f.item_id IS NOT NULL AS favorite,p.position AS p_position,p.duration AS p_duration,p.completed AS p_completed,p.updated_at AS p_updated FROM items i LEFT JOIN favorites f ON f.item_id=i.id LEFT JOIN progress p ON p.item_id=i.id'''


def item_json(r, extra=None):
    if extra is None: extra = json.loads(r['extra'])
    p = None if r['p_updated'] is None else {'position': r['p_position'], 'duration': r['p_duration'], 'completed': bool(r['p_completed']), 'updatedAt': r['p_updated']}
    return {'id': r['id'], 'kind': r['kind'], 'providerId': r['provider_id'], 'name': r['name'], 'poster': r['poster'],
            'categoryId': r['category_id'], 'categoryName': r['category_name'], 'year': r['year'], 'rating': r['rating'],
            'extension': r['extension'], 'added': r['added'], 'favorite': bool(r['favorite']), 'progress': p,
            **{k: v for k, v in extra.items() if k in ('episode', 'season', 'parentId', 'seriesName', 'duration', 'videoCodec', 'audioCodec', 'pixelFormat')}}


def get_row(iid):
    if not ID_RE.fullmatch(iid): raise ValueError('İçerik kimliği geçersiz.')
    with connect() as c: r = c.execute(ITEM_SELECT + ' WHERE i.id=?', (iid,)).fetchone()
    if not r: raise ValueError('İçerik katalogda bulunamadı. Kataloğu yenileyin.')
    return r


def counts():
    with connect() as c: rows = c.execute('SELECT kind,count(*) n FROM items GROUP BY kind').fetchall()
    result = {k: 0 for k in KINDS}
    result.update({r['kind']: r['n'] for r in rows if r['kind'] in KINDS})
    return result


_ADULT_RE = re.compile(r'(?:^|\W)(?:\+18|18\+)(?=$|\W)|\b(?:adult|yetişkin|yetiskin|erotic|erotik|xxx|porn|korku|horror)\b', re.I)


def _hash_pin(pin):
    pin_str = str(pin or '').strip()
    if not pin_str:
        return ''
    if not re.fullmatch(r'\d{4,8}', pin_str):
        raise ValueError('Profil PIN kodu 4-8 rakamdan oluşmalıdır.')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', pin_str.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + digest.hex()


def _verify_pin(pin, stored):
    if not stored:
        return True
    try:
        salt_hex, digest_hex = stored.split(':', 1)
        check = hashlib.pbkdf2_hmac('sha256', str(pin or '').strip().encode('utf-8'), bytes.fromhex(salt_hex), 100000)
        return secrets.compare_digest(check.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def active_profile_id():
    return meta_get('active_profile', 'default') or 'default'


def active_profile():
    pid = active_profile_id()
    with connect() as c:
        row = c.execute('SELECT id,name,avatar_color,is_kids,pin_hash FROM profiles WHERE id=?', (pid,)).fetchone()
    if not row:
        return {'id': 'default', 'name': 'Ana Profil', 'avatarColor': '#7C3AED', 'isKids': False, 'hasPin': False}
    return {'id': row['id'], 'name': row['name'], 'avatarColor': row['avatar_color'], 'isKids': bool(row['is_kids']), 'hasPin': bool(row['pin_hash'])}


def list_profiles():
    with connect() as c:
        rows = c.execute('SELECT id,name,avatar_color,is_kids,pin_hash,created_at FROM profiles ORDER BY CASE WHEN id="default" THEN 0 ELSE 1 END, created_at').fetchall()
    return [{'id': r['id'], 'name': r['name'], 'avatarColor': r['avatar_color'], 'isKids': bool(r['is_kids']), 'hasPin': bool(r['pin_hash']), 'active': r['id'] == active_profile_id()} for r in rows]


def _dump_profile_tables(c):
    return {
        'favorites': [dict(r) for r in c.execute('SELECT * FROM favorites')],
        'progress': [dict(r) for r in c.execute('SELECT * FROM progress')],
        'playlists': [dict(r) for r in c.execute('SELECT * FROM playlists')],
        'playlistItems': [dict(r) for r in c.execute('SELECT * FROM playlist_items')],
        'trackPreferences': [dict(r) for r in c.execute('SELECT * FROM track_preferences')],
    }


def _restore_profile_tables(c, snap):
    for table in ('playlist_items', 'playlists', 'favorites', 'progress', 'track_preferences'):
        c.execute('DELETE FROM ' + table)
    for r in snap.get('favorites', []):
        c.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)', (r['item_id'], r['created_at']))
    for r in snap.get('progress', []):
        c.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?,?,?)', (r['item_id'], r['position'], r['duration'], r['completed'], r['updated_at']))
    for r in snap.get('playlists', []):
        c.execute('INSERT OR IGNORE INTO playlists VALUES(?,?,?)', (r['id'], r['name'], r['created_at']))
    for r in snap.get('playlistItems', []):
        c.execute('INSERT OR IGNORE INTO playlist_items VALUES(?,?,?)', (r['playlist_id'], r['item_id'], r['position']))
    for r in snap.get('trackPreferences', []):
        c.execute('INSERT OR REPLACE INTO track_preferences VALUES(?,?,?)', (r['item_id'], r['data'], r['updated_at']))


def switch_profile(target_id, pin=''):
    with sync_lock:
        current_id = active_profile_id()
        with connect() as c:
            row = c.execute('SELECT id,pin_hash FROM profiles WHERE id=?', (target_id,)).fetchone()
            if not row:
                raise ValueError('Profil bulunamadı.')
            if row['pin_hash'] and not _verify_pin(pin, row['pin_hash']):
                raise ValueError('Profil PIN kodu hatalı.')
            if target_id == current_id:
                return active_profile()
            c.execute('INSERT OR REPLACE INTO profile_snapshots VALUES(?,?)', (current_id, json.dumps(_dump_profile_tables(c), ensure_ascii=False)))
            snap_row = c.execute('SELECT data FROM profile_snapshots WHERE profile_id=?', (target_id,)).fetchone()
            snap = json.loads(snap_row['data']) if snap_row else {}
            _restore_profile_tables(c, snap)
            c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)', ('active_profile', json.dumps(target_id)))
    return active_profile()


def surprise_pick():
    data = home()
    watched_ids = {i['id'] for i in data.get('continueWatching', [])}
    candidates = []
    for shelf in data.get('discovery', {}).get('shelves', []):
        if shelf['id'].startswith(('for-you-', 'trending-', 'new-')):
            for item in shelf.get('items', []):
                if item['id'] not in watched_ids and item['kind'] in ('vod', 'series'):
                    candidates.append(item)
    if not candidates:
        candidates = [i for i in data.get('recent', []) if i['kind'] in ('vod', 'series')]
    if not candidates:
        raise ValueError('Önerilecek içerik bulunamadı. Kütüphaneyi yenileyin.')
    # Weight higher-rated top picks and pick deterministically or randomly among top 12.
    pool = sorted({c['id']: c for c in candidates}.values(), key=lambda i: (bool(i.get('poster')), i.get('rating', 0)), reverse=True)[:12]
    return {'item': pool[secrets.randbelow(len(pool))]}


def catalog(q):
    kind = q.get('kind', ['vod'])[0]
    if kind not in KINDS: raise ValueError('İçerik türü geçersiz.')
    limit = max(1, min(100, int(number(q.get('limit', [48])[0], 48))))
    page = max(1, int(number(q.get('page', [1])[0], 1)))
    where, args = ['i.kind=?'], [kind]
    search = fold(q.get('q', [''])[0])[:200]
    if search:
        where.append("i.search LIKE ? ESCAPE '\\'")
        args.append('%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    category = q.get('category', [''])[0]
    if category: where.append('i.category_id=?'); args.append(category)
    sort = {'recent': 'i.added DESC,i.id', 'name': 'i.search,i.id', 'rating': 'i.rating DESC,i.search'}.get(q.get('sort', ['recent'])[0], 'i.added DESC,i.id')
    with connect() as c:
        total = c.execute('SELECT count(*) FROM items i WHERE ' + ' AND '.join(where), args).fetchone()[0]
        pages = max(1, math.ceil(total / limit))
        page = min(page, pages)
        rows = c.execute(ITEM_SELECT + ' WHERE ' + ' AND '.join(where) + ' ORDER BY ' + sort + ' LIMIT ? OFFSET ?', args + [limit, (page - 1) * limit]).fetchall()
        cats = c.execute('SELECT category_id AS id,category_name AS name,count(*) AS count FROM items WHERE kind=? GROUP BY category_id ORDER BY category_name', (kind,)).fetchall()
    items_out = [item_json(r) for r in rows]
    cats_out = [dict(r) for r in cats]
    if active_profile()['isKids']:
        items_out = [i for i in items_out if not (_ADULT_RE.search(i.get('categoryName', '')) or _ADULT_RE.search(i.get('name', '')))]
        cats_out = [cat for cat in cats_out if not _ADULT_RE.search(cat.get('name', ''))]
    return {'items': items_out, 'total': total, 'page': page, 'pages': pages, 'categories': cats_out}


_home_cache = {'lib_key': None, 'library': [], 'rec_key': None, 'recommendations': None}
_home_lock = threading.Lock()


def home():
    def home_item(row):
        info = json.loads(row['extra'])
        item = item_json(row, info)
        for key in ('backdrop', 'plot', 'genre', 'imdbId', 'tmdbId'):
            if info.get(key): item[key] = info[key]
        return item

    with connect() as c:
        # Choose the latest activity for each series before filtering completed
        # episodes or applying the rail limit. Older unfinished episodes must
        # never replace the viewer's latest episode.
        watched = c.execute(ITEM_SELECT + " WHERE (p.position>0 OR p.completed=1) AND i.kind IN ('vod','episode') ORDER BY p.updated_at DESC,i.id").fetchall()
        continuing, seen_series = [], set()
        for row in watched:
            item = home_item(row)
            if item['kind'] == 'episode':
                parent = item.get('parentId')
                key = parent or item.get('seriesName') or item['id']
                if key in seen_series: continue
                seen_series.add(key)
                if item['progress']['completed']:
                    episodes = series_episode_rows(c, parent) if parent else []
                    following = next((b for a, b in zip(episodes, episodes[1:]) if a['id'] == item['id']), None)
                    if following is None: continue
                    item = home_item(following)
                    item['continueReason'] = 'nextEpisode'
            elif item['progress']['completed'] or item['progress']['position'] <= 10:
                continue
            continuing.append(item)
            if len(continuing) == 20: break
        fav = c.execute(ITEM_SELECT + ' WHERE f.item_id IS NOT NULL ORDER BY f.created_at DESC LIMIT 16').fetchall()
        rows_by_kind = {
            kind: c.execute(ITEM_SELECT + ' WHERE i.kind=? ORDER BY i.added DESC,i.id LIMIT 120', (kind,)).fetchall()
            for kind in ('vod', 'series')
        }
    is_kids = active_profile()['isKids']
    def kid_safe(item):
        return not is_kids or not (_ADULT_RE.search(item.get('categoryName', '')) or _ADULT_RE.search(item.get('name', '')))
    recent = []
    for rows in rows_by_kind.values():
        seen = set()
        for row in rows:
            poster = urllib.parse.urlsplit(row['poster']).path.rsplit('/', 1)[-1]
            key = poster if len(poster) > 10 else fold(row['name'])
            if key in seen: continue
            item = home_item(row)
            if not kid_safe(item): continue
            seen.add(key)
            recent.append(item)
            if len(seen) == 12: break
    feed = discovery.snapshot(DATA, enabled=bool(provider.config.get('host')))
    with connect() as c:
        lib_key = (str(DB), tuple(c.execute("SELECT count(*), coalesce(max(added),0), coalesce(max(rowid),0) FROM items WHERE kind IN ('vod','series')").fetchone()))
        hist_key = (
            tuple(c.execute("SELECT count(*), coalesce(max(updated_at),''), coalesce(sum(position),0), coalesce(sum(completed),0) FROM progress").fetchone()),
            tuple(c.execute("SELECT count(*), coalesce(max(created_at),'') FROM favorites").fetchone()),
        )
        rec_key = (lib_key, hist_key, is_kids, feed.get('updatedAt'), len(feed.get('metas', ())), len(feed.get('charts', ())))
        with _home_lock:
            cached_rec = _home_cache['recommendations'] if _home_cache['rec_key'] == rec_key else None
            cached_lib = _home_cache['library'] if _home_cache['lib_key'] == lib_key else None
        if cached_rec is not None:
            recommendations = cached_rec
        else:
            library = cached_lib if cached_lib is not None else [home_item(r) for r in c.execute(ITEM_SELECT + " WHERE i.kind IN ('vod','series')")]
            filtered_lib = [i for i in library if kid_safe(i)] if is_kids else library
            history = [home_item(r) for r in c.execute(ITEM_SELECT + " WHERE p.item_id IS NOT NULL OR f.item_id IS NOT NULL")]
            recommendations = discovery.build(filtered_lib, history, feed)
            with _home_lock:
                _home_cache.update(lib_key=lib_key, library=library, rec_key=rec_key, recommendations=recommendations)
    return {'continueWatching': continuing, 'favorites': [home_item(r) for r in fav], 'recent': recent, 'counts': counts(), 'discovery': recommendations}


def series_episode_rows(c, parent_id):
    return c.execute(ITEM_SELECT + """ WHERE i.kind='episode' AND json_extract(i.extra,'$.parentId')=?
        ORDER BY CAST(json_extract(i.extra,'$.season') AS INTEGER),CAST(json_extract(i.extra,'$.episode') AS INTEGER),i.id""",
        (parent_id,)).fetchall()


def following_episode(iid, parent_id):
    with connect() as c:
        rows = series_episode_rows(c, parent_id)
    return next((item_json(following) for current, following in zip(rows, rows[1:]) if current['id'] == iid), None)


def detail(iid):
    r = get_row(iid)
    info = json.loads(r['extra'])
    seasons = []
    if r['kind'] == 'vod':
        if provider.mode == 'xtream':
            try: d = provider.api('get_vod_info', vod_id=r['provider_id'])
            except (RuntimeError, ValueError):
                if not info.get('plot') and not info.get('duration'): raise
                d = None
        else:
            d = None
        if isinstance(d, dict) and isinstance(d.get('info'), dict):
            p = d['info']
            info.update(codec_metadata(p))
            for k in ('plot', 'genre', 'cast', 'director', 'rating'):
                if p.get(k): info[k] = string(p[k], 12000 if k == 'plot' else 2000)
            info['duration'] = duration_seconds(p.get('duration_secs') or p.get('duration'))
            backdrop = p.get('backdrop_path')
            if backdrop: info['backdrop'] = string(backdrop[0] if isinstance(backdrop, list) else backdrop, 3000)
            info['year'] = string(p.get('releasedate') or r['year'], 10)[:4]
    elif r['kind'] == 'series':
        try:
            d = provider.api('get_series_info', series_id=r['provider_id'])
            if not isinstance(d, dict): raise RuntimeError('Dizi bölümleri alınamadı.')
        except (RuntimeError, ValueError):
            with connect() as c: saved = series_episode_rows(c, iid)
            if not saved: raise
            d = None
        if d is not None:
            p = d.get('info', {})
            if isinstance(p, dict):
                for k in ('plot', 'genre', 'cast', 'director', 'rating'):
                    if p.get(k): info[k] = string(p[k], 12000 if k == 'plot' else 2000)
                b = p.get('backdrop_path')
                if b: info['backdrop'] = string(b[0] if isinstance(b, list) else b, 3000)
            eps = d.get('episodes', {})
            if isinstance(eps, list): eps = {str(i + 1): x for i, x in enumerate(eps)}
            rows = []
            if isinstance(eps, dict):
                for season, entries in eps.items():
                    if not isinstance(entries, list): continue
                    for e in entries:
                        if not isinstance(e, dict): continue
                        e = dict(e)
                        e['season'] = number(e.get('season'), number(season))
                        nr = normalize_item(e, 'episode', {}, parent=r)
                        if nr: rows.append(nr)
            with connect() as c:
                if rows:
                    c.execute("DELETE FROM items WHERE kind='episode' AND json_extract(extra,'$.parentId')=?", (iid,))
                    c.executemany(UPSERT_ITEM, rows)
                saved = series_episode_rows(c, iid)
        grouped = collections.defaultdict(list)
        for row in saved:
            e = item_json(row)
            grouped[e.get('season', 1)].append(e)
        seasons = [{'season': n, 'name': f'{n}. Sezon', 'episodes': es} for n, es in sorted(grouped.items())]
    if r['kind'] in ('vod', 'series'):
        with connect() as c: c.execute('UPDATE items SET extra=? WHERE id=?', (json.dumps(info, ensure_ascii=False), iid))
        r = get_row(iid)
    return {'item': item_json(r), 'info': info, 'seasons': seasons}


def playlists():
    with connect() as c:
        lists = c.execute('SELECT * FROM playlists ORDER BY created_at').fetchall()
        output = []
        for p in lists:
            rows = c.execute(ITEM_SELECT + ' JOIN playlist_items pi ON pi.item_id=i.id WHERE pi.playlist_id=? ORDER BY pi.position', (p['id'],)).fetchall()
            output.append({'id': p['id'], 'name': p['name'], 'count': len(rows), 'items': [item_json(r) for r in rows]})
    return {'playlists': output}


_lan_cache = (0.0, [])


def lan_ips():
    global _lan_cache
    now = time.monotonic()
    if now - _lan_cache[0] < 30.0:
        return _lan_cache[1]
    out = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80)); out.add(s.getsockname()[0])
    except OSError: pass
    try:
        for a in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET): out.add(a[4][0])
    except OSError: pass
    result = sorted(x for x in out if ipaddress.ip_address(x).is_private and not ipaddress.ip_address(x).is_loopback)
    _lan_cache = (now, result)
    return result


def resource_for(sid, url):
    with resource_lock:
        s = media_sessions.get(sid)
        if not s: raise ValueError('Oynatma oturumu kapandı. Yeniden oynatın.')
        if url in s['reverse']: token = s['reverse'][url]
        else:
            if len(s['resources']) > 2000:
                old = next(iter(s['resources']))
                s['reverse'].pop(s['resources'].pop(old), None)
            token = secrets.token_urlsafe(18)
            s['resources'][token] = url
            s['reverse'][url] = token
        s['touched'] = time.monotonic()
    return f'/media/{sid}/proxy/{token}'


def abort_connections(connections):
    for response in connections:
        try:
            response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (AttributeError, OSError): pass
        with contextlib.suppress(OSError, ValueError): response.close()


def stop_session(sid):
    with resource_lock:
        s = media_sessions.pop(sid, None)
        source = internal_sources.pop(s.get('sourceToken'), None) if s else None
        connections = list(s.get('connections', ())) if s else []
        if source: connections.extend(source.get('connections', ()))
    abort_connections(connections)
    playback.stop(sid)


def stop_all():
    with resource_lock:
        sessions = list(media_sessions)
        orphan_sources = list(internal_sources.values())
    for sid in sessions: stop_session(sid)
    with resource_lock: internal_sources.clear()
    for source in orphan_sources: abort_connections(list(source.get('connections', ())))



def backup_items(c):
    """Portable metadata for saved titles, including episodes not in catalogs."""
    rows = c.execute("SELECT i.* FROM items i WHERE EXISTS(SELECT 1 FROM progress p WHERE p.item_id=i.id) OR EXISTS(SELECT 1 FROM favorites f WHERE f.item_id=i.id) OR EXISTS(SELECT 1 FROM playlist_items pi WHERE pi.item_id=i.id) ORDER BY i.id").fetchall()
    output = []
    for r in rows:
        extra = json.loads(r['extra'])
        parent_id = extra.get('parentId')
        parent = c.execute('SELECT poster,extra FROM items WHERE id=?', (parent_id,)).fetchone() if parent_id else None
        output.append({'id': r['id'], 'providerId': r['provider_id'], 'name': r['name'], 'kind': r['kind'],
            'categoryId': r['category_id'], 'categoryName': r['category_name'], 'poster': r['poster'] or (parent['poster'] if parent else ''),
            'backdrop': extra.get('backdrop', ''), 'year': r['year'], 'rating': r['rating'], 'extension': r['extension'] or 'mp4',
            'durationSeconds': number(extra.get('duration')), 'plot': extra.get('plot', ''), 'season': int(number(extra.get('season'))),
            'episode': int(number(extra.get('episode'))), 'parentId': parent_id, 'addedAt': int(number(r['added'])),
            'videoCodec': extra.get('videoCodec', ''), 'audioCodec': extra.get('audioCodec', '')})
    return output



def portable_item_row(r):
    if not isinstance(r, dict): raise ValueError('Yedekteki içerik bilgisi geçersiz.')
    iid, kind, pid = str(r.get('id', '')), str(r.get('kind', '')), str(r.get('providerId', ''))
    if not ID_RE.fullmatch(iid) or iid != f'{kind}:{pid}': raise ValueError('Yedekteki içerik kimliği geçersiz.')
    name = string(r.get('name'), 2000).strip()
    if not name: raise ValueError('Yedekteki içerik adı eksik.')
    parent = r.get('parentId')
    if parent is not None and (not isinstance(parent, str) or not re.fullmatch(r'series:[A-Za-z0-9_-]{1,100}', parent)):
        raise ValueError('Yedekteki dizi kimliği geçersiz.')
    extra = {'duration': max(0, number(r.get('durationSeconds'))), 'plot': string(r.get('plot'), 20000),
        'backdrop': string(r.get('backdrop'), 5000), 'season': int(number(r.get('season'))), 'episode': int(number(r.get('episode'))),
        'parentId': parent, 'videoCodec': string(r.get('videoCodec'), 40), 'audioCodec': string(r.get('audioCodec'), 40)}
    extension = str(r.get('extension', 'mp4')).lower()
    if not re.fullmatch(r'[a-z0-9]{1,10}', extension): raise ValueError('Yedekteki içerik biçimi geçersiz.')
    return (iid, kind, pid, name, fold(name), string(r.get('poster'), 5000), string(r.get('categoryId'), 100),
        string(r.get('categoryName'), 500), string(r.get('year'), 4), number(r.get('rating')), extension,
        number(r.get('addedAt')), json.dumps(extra, ensure_ascii=False))


def track_preferences(iid):
    with connect() as c: row = c.execute('SELECT data FROM track_preferences WHERE item_id=?', (iid,)).fetchone()
    defaults = {'audio': 'auto', 'subtitle': 'off', 'clientAudio': None, 'clientSubtitle': None}
    if row:
        try: defaults.update(json.loads(row[0]))
        except (ValueError, TypeError): pass
    return defaults


def save_track_preferences(iid, changes):
    pref = track_preferences(iid)
    patterns = {'audio': r'(?:auto|stream:[0-9]{1,5})', 'subtitle': r'(?:off|stream:[0-9]{1,5})',
                'clientAudio': r'(?:auto|hls:[0-9]{1,5}|native:[0-9]{1,5})',
                'clientSubtitle': r'(?:off|hls:[0-9]{1,5}|native:[0-9]{1,5})'}
    for key, pattern in patterns.items():
        if key in changes:
            value = changes[key]
            if value is not None and (not isinstance(value, str) or not re.fullmatch(pattern, value)):
                raise ValueError('Ses veya altyazı seçimi geçersiz.')
            if value is None and key in ('audio', 'subtitle'): raise ValueError('Parça seçimi boş olamaz.')
            pref[key] = value
    with connect() as c: c.execute('INSERT OR REPLACE INTO track_preferences VALUES(?,?,?)', (iid, json.dumps(pref), stamp()))
    return pref


def cached_tracks(iid, fresh=False):
    with connect() as c: row = c.execute('SELECT data,updated FROM media_tracks WHERE item_id=?', (iid,)).fetchone()
    if row and (not fresh or time.time() - row['updated'] < (300 if iid.startswith('live:') else 86400)):
        try: return json.loads(row['data'])
        except (ValueError, TypeError): pass
    return None


def sidecar_subtitles(iid, r=None):
    row = r or get_row(iid)
    try:
        extra = json.loads(row['extra'])
    except (ValueError, TypeError):
        extra = {}
    subs = extra.get('subtitles')
    if not isinstance(subs, list) or not subs:
        return []
    out = []
    for idx, sub_path in enumerate(subs[:8]):
        if not isinstance(sub_path, str) or not sub_path.strip():
            continue
        p = Path(sub_path)
        lang = infer_subtitle_language('und', p.stem)
        out.append({
            'id': f'sidecar:{idx}',
            'index': idx,
            'language': lang,
            'title': p.name,
            'url': f'/api/subtitles/{urllib.parse.quote(iid, safe="")}/{idx}.vtt',
        })
    return out


def tracks_response(iid, probe=False):
    r = get_row(iid)
    tracks = cached_tracks(iid, fresh=probe)
    if probe and (not isinstance(tracks, dict) or not tracks.get('scanned')) and playback.available and r['kind'] != 'series':
        token = secrets.token_urlsafe(32)
        with resource_lock:
            internal_sources[token] = {'url': provider.source(r, hls=False), 'touched': time.monotonic()}
        try:
            probed = playback.probe(f'http://127.0.0.1:{HTTP_PORT}/internal/source/{token}')
            if isinstance(probed, dict) and probed.get('scanned'):
                probed.setdefault('duration', None)
                with connect() as c:
                    c.execute('INSERT OR REPLACE INTO media_tracks VALUES(?,?,?)', (iid, json.dumps(probed, ensure_ascii=False), time.time()))
                tracks = probed
        except (RuntimeError, OSError):
            pass
        finally:
            with resource_lock:
                source = internal_sources.pop(token, None)
            if source:
                abort_connections(list(source.get('connections', ())))
    return {
        'tracks': tracks or {'audio': [], 'subtitles': [], 'scanned': False},
        'selection': track_preferences(iid),
        'externalSubtitles': sidecar_subtitles(iid, r),
    }


def register_play_request(options):
    """Reject late slider requests before they can replace newer playback."""
    global latest_play_request
    if options.get('multiview'):
        slot = options.get('multiviewSlot')
        if slot is not None:
            if isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= 3:
                raise ValueError('Çoklu ekran yuvası geçersiz.')
            with resource_lock:
                seq = multiview_slot_requests.get(slot, 0) + 1
                multiview_slot_requests[slot] = seq
                return ('multiview', slot, seq)
        return ('multiview', None, None)
    client, generation = options.get('clientId'), options.get('generation')
    if client is not None or generation is not None:
        if (not isinstance(client, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', client)
                or not isinstance(generation, int) or isinstance(generation, bool) or not 0 < generation < 2**53):
            raise ValueError('Oynatma isteği geçersiz.')
    with resource_lock:
        now = time.monotonic()
        for key in [key for key, (_, touched) in play_clients.items() if now - touched > 3600]: play_clients.pop(key, None)
        if client is not None:
            if generation <= play_clients.get(client, (0, 0))[0]:
                raise PlaybackError('Daha yeni bir izleme konumu seçildi.', code='superseded')
            if client not in play_clients and len(play_clients) >= 64: play_clients.pop(next(iter(play_clients)))
            play_clients[client] = (generation, now)
        latest_play_request += 1
        return ('single', latest_play_request)


def ensure_current_play_request(request):
    with resource_lock:
        if isinstance(request, tuple) and request[0] == 'multiview':
            _, slot, seq = request
            if slot is not None and seq != multiview_slot_requests.get(slot):
                raise PlaybackError('Daha yeni bir oynatma isteği alındı.', code='superseded')
            return
        expected = request[1] if isinstance(request, tuple) else request
        if expected != latest_play_request:
            raise PlaybackError('Daha yeni bir oynatma isteği alındı.', code='superseded')


def play_item(iid, mode, start, options=None):
    options = options or {}
    r = get_row(iid)
    if r['kind'] == 'series': raise ValueError('Oynatmak için bir dizi bölümü seçin.')
    if mode not in ('direct', 'remux', 'transcode'): raise ValueError('Oynatma modu geçersiz.')
    is_multiview = bool(options.get('multiview'))
    request = register_play_request(options)
    mv_slot = request[1] if isinstance(request, tuple) and request[0] == 'multiview' else None
    start = max(0, number(start))
    if r['kind'] == 'vod' and not number(json.loads(r['extra']).get('duration')):
        try:
            detail(iid)
            r = get_row(iid)
        except (RuntimeError, ValueError): pass
    extra = json.loads(r['extra'])
    if r['kind'] == 'episode' and not extra.get('videoCodec') and extra.get('parentId'):
        try:
            detail(extra['parentId'])
            r = get_row(iid)
            extra = json.loads(r['extra'])
        except (RuntimeError, ValueError): pass
    next_episode = following_episode(iid, extra['parentId']) if r['kind'] == 'episode' and extra.get('parentId') else None
    codec, pixels = extra.get('videoCodec', ''), extra.get('pixelFormat', '')
    if mode == 'remux' and ((codec and codec not in ('h264', 'avc', 'avc1')) or
                            (pixels and pixels not in ('yuv420p', 'yuvj420p', 'nv12'))): mode = 'transcode'
    selection = track_preferences(iid)
    for key, field, default in (('audio', 'audioTrack', 'auto'), ('subtitle', 'subtitleTrack', 'off')):
        if field in options:
            value = options[field]
            if not isinstance(value, str) or not re.fullmatch(r'(?:' + default + r'|stream:[0-9]{1,5})', value):
                raise ValueError('Ses veya altyazı parçası geçersiz.')
            selection[key] = value
            selection['clientAudio' if key == 'audio' else 'clientSubtitle'] = None
    with play_lock:
        ensure_current_play_request(request)
        if is_multiview:
            with resource_lock:
                to_stop = [
                    s_id for s_id, s_data in media_sessions.items()
                    if not s_data.get('multiview')
                    or (mv_slot is not None and s_data.get('multiviewSlot') == mv_slot)
                ]
                if mv_slot is None:
                    remaining_mv = [
                        (s_data.get('touched', 0), s_id)
                        for s_id, s_data in media_sessions.items()
                        if s_id not in to_stop and s_data.get('multiview')
                    ]
                    if len(remaining_mv) >= 4:
                        remaining_mv.sort()
                        to_stop.extend(s_id for _, s_id in remaining_mv[:len(remaining_mv) - 3])
            for s_id in to_stop:
                stop_session(s_id)
        else:
            stop_all()
        live = r['kind'] == 'live'
        duration = max(0, number(extra.get('duration'))) or (r['p_duration'] or None)
        skip_probe = is_multiview and mode == 'direct'
        token = None if skip_probe else secrets.token_urlsafe(32)
        if token is not None:
            with resource_lock: internal_sources[token] = {'url': provider.source(r, hls=False), 'touched': time.monotonic()}
        local_source = f'http://127.0.0.1:{HTTP_PORT}/internal/source/{token}' if token is not None else ''
        tracks = None if options.get('refreshTracks') else cached_tracks(iid, fresh=True)
        try:
            if not skip_probe and (not isinstance(tracks, dict) or (not live and not duration and 'duration' not in tracks)) and playback.available:
                try: tracks = playback.probe(local_source)
                except (RuntimeError, OSError): tracks = None
                # The input probe exits before playback starts: release its TCP
                # connection explicitly to respect single-connection accounts.
                with resource_lock:
                    source = internal_sources.get(token, {})
                    connections = list(source.pop('connections', ()))
                    failure = source.get('source_error')
                abort_connections(connections)
                if failure: raise PlaybackError(failure['error'], mode=mode, code=failure['code'])
                if isinstance(tracks, dict) and tracks.get('scanned'):
                    tracks.setdefault('duration', None)
                    with connect() as c: c.execute('INSERT OR REPLACE INTO media_tracks VALUES(?,?,?)', (iid, json.dumps(tracks, ensure_ascii=False), time.time()))
            if not isinstance(tracks, dict): tracks = {'audio': [], 'subtitles': [], 'scanned': False}
            if mode == 'remux':
                p_codec = codec or tracks.get('videoCodec', '')
                p_pixels = pixels or tracks.get('pixelFormat', '')
                if ((p_codec and p_codec not in ('h264', 'avc', 'avc1')) or
                        (p_pixels and p_pixels not in ('yuv420p', 'yuvj420p', 'nv12'))): mode = 'transcode'
            if not live:
                duration = max(0, number(tracks.get('duration'))) or duration
                if duration:
                    start = min(start, max(0, duration - .1))
            audio = next((x for x in tracks.get('audio', []) if x['id'] == selection['audio']), None)
            subtitle = next((x for x in tracks.get('subtitles', []) if x['id'] == selection['subtitle']), None)
            # A saved stream can disappear when a live channel changes its feed.
            # Explicit invalid requests fail; old preferences safely revert.
            for key, field, group, default in (('audio', 'audioTrack', 'audio', 'auto'), ('subtitle', 'subtitleTrack', 'subtitles', 'off')):
                if selection[key] != default and not any(x['id'] == selection[key] for x in tracks.get(group, [])):
                    if field in options: raise ValueError('Seçilen parça bu içerikte bulunamadı. Parçaları yeniden tarayın.')
                    selection[key] = default
            if selection['audio'] != 'auto' or selection['subtitle'] != 'off':
                if not playback.available: raise RuntimeError('Ses ve altyazı seçimi için yerel oynatma bileşeni gerekiyor.')
                if mode == 'direct': mode = 'remux'
            if subtitle and subtitle.get('bitmap'): mode = 'transcode'
            ensure_current_play_request(request)
            if mode == 'direct':
                if token is not None:
                    with resource_lock: internal_sources.pop(token, None)
                sid = secrets.token_urlsafe(18)
                source = provider.source(r, hls=live)
                with resource_lock: media_sessions[sid] = {'resources': {}, 'reverse': {}, 'touched': time.monotonic(), 'owner': None, 'item': iid, 'multiview': is_multiview, 'multiviewSlot': mv_slot}
                result = {'sessionId': sid, 'url': resource_for(sid, source), 'type': 'hls' if live else 'file', 'startOffset': 0, 'duration': duration, 'mode': mode}
            else:
                if audio is None and selection['audio'] == 'auto':
                    audio = next((x for x in tracks.get('audio', []) if x.get('default')), next(iter(tracks.get('audio', [])), None))
                kwargs = {}
                if audio: kwargs['audio_index'] = audio['index']
                if subtitle:
                    kwargs.update(subtitle_index=subtitle['index'], subtitle_codec=subtitle.get('codec', ''),
                                  subtitle_name=subtitle.get('title') or subtitle.get('language') or 'Altyazı',
                                  subtitle_language=subtitle.get('language') or 'und')
                result = playback.start(local_source, mode=mode, start=0 if live else start, duration=duration, live=live, **kwargs)
                sid = result['sessionId']
                try: ensure_current_play_request(request)
                except PlaybackError:
                    playback.stop(sid)
                    raise
                with resource_lock: media_sessions[sid] = {'resources': {}, 'reverse': {}, 'touched': time.monotonic(), 'sourceToken': token, 'owner': None, 'item': iid, 'multiview': is_multiview, 'multiviewSlot': mv_slot}
                result['mode'] = mode
            save_track_preferences(iid, selection)
            result.update(tracks=tracks, selection=selection, externalSubtitles=sidecar_subtitles(iid, r))
            if next_episode:
                result['nextEpisode'] = next_episode
            return result
        except Exception as exc:
            source = None
            if token is not None:
                with resource_lock: source = internal_sources.pop(token, None)
            if source:
                abort_connections(list(source.get('connections', ())))
                failure = source.get('source_error')
                if failure: raise PlaybackError(failure['error'], mode=mode, code=failure['code']) from None
            if isinstance(exc, PlaybackError): raise
            if isinstance(exc, RuntimeError): raise PlaybackError(str(exc), mode=mode, code='playback_failed') from None
            raise


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Mavie/3.0'
    def setup(self):
        super().setup()
        self.connection.settimeout(35)
    def handle(self):
        try: super().handle()
        except (ConnectionResetError, BrokenPipeError, TimeoutError): pass
    def log_message(self, fmt, *args):
        # Never log query strings, media source addresses, credentials or request bodies.
        if self.path == '/api/play' and self.command == 'POST':
            print(f'[{stamp()}] Oynatıcı isteği', flush=True)
    @property
    def is_local(self):
        try: return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError: return False
    def host_allowed(self):
        try: host = urllib.parse.urlsplit('http://' + self.headers.get('Host', '')).hostname or ''
        except ValueError: return False
        host = host.lower()
        return host in ('localhost', '127.0.0.1', '::1') or host in lan_ips()
    def authorized(self):
        try:
            c = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
            token = c.get('mavie_device') or c.get('cineva_device') or c.get('akis_device')
            if not token: return False
            digest = hashlib.sha256(token.value.encode()).hexdigest()
            with connect() as db: return db.execute('SELECT 1 FROM devices WHERE token_hash=?', (digest,)).fetchone() is not None
        except (http.cookies.CookieError, ValueError): return False
    def device_cookie(self):
        token = secrets.token_urlsafe(32)
        with connect() as c: c.execute('INSERT INTO devices VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), stamp()))
        return f'mavie_device={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000'
    def headers_out(self, code, content_type, length=None, extra=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        if not extra or 'Content-Security-Policy' not in extra:
            self.send_header('Content-Security-Policy', "default-src 'none'; sandbox")
        self.send_header('Cache-Control', 'no-store')
        if length is not None: self.send_header('Content-Length', str(length))
        else:
            self.send_header('Connection', 'close'); self.close_connection = True
        for k, v in (extra or {}).items(): self.send_header(k, str(v))
        self.end_headers()
    def send_json(self, data, code=200, extra=None):
        b = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.headers_out(code, 'application/json; charset=utf-8', len(b), extra)
        if self.command != 'HEAD': self.wfile.write(b)
    def body(self):
        if 'application/json' not in self.headers.get('Content-Type', ''):
            raise ValueError('İstek JSON biçiminde olmalı.')
        n = int(self.headers.get('Content-Length', '0'))
        if n < 1 or n > MAX_JSON: raise ValueError('İstek boyutu geçersiz.')
        try: d = json.loads(self.rfile.read(n))
        except (ValueError, UnicodeError): raise ValueError('JSON okunamadı.') from None
        if not isinstance(d, dict): raise ValueError('İstek nesne olmalı.')
        return d
    def guard(self, mutation=False):
        if not self.host_allowed(): self.send_json({'error': 'Sunucu adresine izin verilmiyor.'}, 403); return False
        if mutation:
            origin = self.headers.get('Origin')
            if origin and origin not in ('http://' + self.headers.get('Host', ''), 'https://' + self.headers.get('Host', '')):
                self.send_json({'error': 'Bu kaynaktan değişiklik yapılamaz.'}, 403); return False
        return True
    def require_auth(self):
        if not self.authorized(): self.send_json({'error': 'Bu cihazı ana cihazdaki eşleştirme koduyla bağlayın.'}, 401); return False
        return True
    def handle_error(self, e):
        if isinstance(e, (BrokenPipeError, ConnectionResetError)): return
        code = 400 if isinstance(e, ValueError) else (502 if isinstance(e, (RuntimeError, urllib.error.URLError, TimeoutError)) else 500)
        message = str(e) if isinstance(e, (ValueError, RuntimeError)) else 'İşlem tamamlanamadı. Yeniden deneyin.'
        payload = {'error': message}
        if isinstance(e, PlaybackError):
            if e.code == 'superseded': code = 409
            if e.mode: payload['mode'] = e.mode
            if e.code: payload['code'] = e.code
        try: self.send_json(payload, code)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        try:
            if not self.guard(): return
            u = urllib.parse.urlsplit(self.path); p = urllib.parse.unquote(u.path); q = urllib.parse.parse_qs(u.query)
            if p == '/api/health': return self.send_json({'app': 'mavie', 'ok': True})
            if p == '/api/legal':
                return self.send_json({
                    'app': 'Mavie',
                    'disclaimer': 'Mavie kişisel bir medya oynatıcı ve kütüphane düzenleyicidir. Telifli içerik barındırmaz veya sağlamaz.',
                    'licenses': ['LibVLC (LGPL-2.1+)', 'hls.js (Apache-2.0)', 'TMDB Discovery (opsiyonel resmi API)'],
                })
            if p.startswith('/internal/source/'):
                if not self.is_local: return self.send_json({'error': 'Erişim yok.'}, 403)
                token = p.split('/')[-1]
                with resource_lock: source = internal_sources.get(token)
                if not source: return self.send_json({'error': 'Kaynak süresi doldu.'}, 404)
                # FFmpeg intentionally stops reading while its prefetch buffer
                # is full or the user pauses. That must not time out a local
                # proxy write. Upstream reads retain their network timeout.
                self.connection.settimeout(None)
                return self.proxy(source['url'], source_token=token)
            if p == '/api/status':
                if not self.authorized(): return self.send_json({'authorized': False, 'pairingRequired': True})
                result = {
                    'authorized': True,
                    'configured': provider.configured,
                    'connection': {
                        'name': provider.config.get('name', 'Medya Kaynağı'),
                        'type': provider.mode,
                        'host': provider.config.get('host', ''),
                        'm3uUrl': provider.config.get('m3uUrl', ''),
                        'localDir': provider.config.get('localDir', '') if self.is_local else '',
                        'epgUrl': provider.config.get('epgUrl') or provider.config.get('discoveredEpgUrl', ''),
                    },
                    'profile': active_profile(),
                    'account': meta_get('account', {}),
                    'catalog': {**counts(), 'updatedAt': meta_get('catalog_updated'), **sync_state},
                    'network': {'localUrl': f'http://localhost:{HTTP_PORT}', 'lanUrls': [f'http://{ip}:{HTTP_PORT}' for ip in lan_ips()]},
                    'ffmpeg': playback.available,
                }
                if self.is_local: result['pairingCode'] = PAIR_CODE
                return self.send_json(result)
            if p.startswith('/api/') or p.startswith('/media/'):
                if not self.require_auth(): return
                if p == '/api/home': return self.send_json(home())
                if p == '/api/surprise': return self.send_json(surprise_pick())
                if p == '/api/profiles': return self.send_json({'activeProfileId': active_profile_id(), 'profiles': list_profiles()})
                if p == '/api/sports':
                    day = sports.selected_date(q.get('date', [''])[0])
                    epg_url = q.get('epgUrl', [''])[0].strip() or provider.config.get('epgUrl') or provider.config.get('discoveredEpgUrl', '')
                    if epg_url: validate_host(epg_url)
                    guide = sports.get_listings(day, remote, epg_url=epg_url, refresh=q.get('refresh') == ['1'])
                    with connect() as c:
                        channels = c.execute("SELECT id,name FROM items WHERE kind='live' ORDER BY id").fetchall()
                    guide['channels'] = sports.match_channels(guide['events'], channels)
                    return self.send_json(guide)
                if p == '/api/catalog': return self.send_json(catalog(q))
                if p.startswith('/api/items/'): return self.send_json(detail(p[len('/api/items/'):]))
                if p.startswith('/api/tracks/'): return self.send_json(tracks_response(p[len('/api/tracks/'):], probe=q.get('probe') == ['1']))
                if p.startswith('/api/subtitles/'): return self.serve_sidecar_subtitle(p[len('/api/subtitles/'):])
                if p == '/api/playlists': return self.send_json(playlists())
                if p == '/api/favorites':
                    with connect() as c: rows = c.execute(ITEM_SELECT + ' WHERE f.item_id IS NOT NULL ORDER BY f.created_at DESC').fetchall()
                    return self.send_json({'items': [item_json(r) for r in rows]})
                if p == '/api/progress':
                    with connect() as c: rows = c.execute(ITEM_SELECT + ' WHERE p.item_id IS NOT NULL ORDER BY p.updated_at DESC').fetchall()
                    return self.send_json({'items': [item_json(r) for r in rows]})
                if p.startswith('/api/image'): return self.image(q.get('url', [''])[0])
                if p.startswith('/api/epg/'): return self.epg(p[len('/api/epg/'):])
                if p == '/api/export':
                    return self.send_json(export_state_dict(), extra={'Content-Disposition': 'attachment; filename="mavie-yedek.json"'})
                if p.startswith('/media/'): return self.media(p)
                return self.send_json({'error': 'Sayfa bulunamadı.'}, 404)
            return self.static(p)
        except Exception as e: self.handle_error(e)
    def do_POST(self): self.mutate('POST')
    def do_PATCH(self): self.mutate('PATCH')
    def do_DELETE(self): self.mutate('DELETE')
    def mutate(self, method):
        global provider
        try:
            if not self.guard(mutation=True): return
            p = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if p == '/api/pair' and method == 'POST':
                code_attempt = str(self.body().get('code', ''))
                now = time.monotonic(); ip = self.client_address[0]
                with resource_lock:
                    pair_attempts[ip] = [x for x in pair_attempts[ip] if x > now - 300]
                    if len(pair_attempts[ip]) >= 10: return self.send_json({'error': 'Çok fazla deneme. 5 dakika sonra yeniden deneyin.'}, 429)
                    pair_attempts[ip].append(now)
                    if not secrets.compare_digest(code_attempt, PAIR_CODE): return self.send_json({'error': 'Eşleştirme kodu yanlış.'}, 403)
                    pair_attempts[ip].clear()
                return self.send_json({'ok': True}, extra={'Set-Cookie': self.device_cookie()})
            if not self.require_auth(): return
            d = self.body() if method != 'DELETE' or int(self.headers.get('Content-Length', '0') or 0) > 0 else {}
            if p == '/api/demo' and method == 'POST':
                if not self.is_local: return self.send_json({'error': 'Demo kaynağı yalnızca ana cihaz üzerinden açılabilir.'}, 403)
                if sync_state['syncing']: raise ValueError('Katalog güncelleniyor. Bittikten sonra tekrar deneyin.')
                stop_all()
                with connect() as c:
                    for table in ('items', 'categories', 'favorites', 'progress', 'playlist_items', 'media_tracks', 'track_preferences'): c.execute('DELETE FROM ' + table)
                    c.execute("DELETE FROM meta WHERE key='catalog_updated'")
                config = {'type': 'demo', 'name': 'Açık Sinema (Demo)'}
                save_config(config); provider = Provider(config); sync_catalog()
                return self.send_json({'ok': True})
            if p == '/api/profiles' and method == 'POST':
                name = string(d.get('name'), 60).strip()
                if not name: raise ValueError('Profil adı boş olamaz.')
                is_kids = bool(d.get('isKids', False))
                color = str(d.get('avatarColor') or '#7C3AED')
                if not re.fullmatch(r'#[0-9A-Fa-f]{6}', color): color = '#7C3AED'
                raw_pin = str(d.get('pin', '')).strip()
                pin_hash = _hash_pin(raw_pin)
                pid = 'p_' + secrets.token_urlsafe(8)
                with connect() as c:
                    c.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?)', (pid, name, color, int(is_kids), pin_hash, stamp()))
                return self.send_json({'ok': True, 'profile': {'id': pid, 'name': name, 'avatarColor': color, 'isKids': is_kids, 'hasPin': bool(pin_hash)}}, 201)
            if p == '/api/profiles/switch' and method == 'POST':
                pid = str(d.get('id', '')).strip()
                ip = self.client_address[0]
                now = time.monotonic()
                with resource_lock:
                    pair_attempts['pin:' + ip] = [x for x in pair_attempts['pin:' + ip] if x > now - 300]
                    if len(pair_attempts['pin:' + ip]) >= 10:
                        return self.send_json({'error': 'Çok fazla PIN denemesi. 5 dakika bekleyin.'}, 429)
                    try:
                        profile = switch_profile(pid, d.get('pin', ''))
                        pair_attempts['pin:' + ip].clear()
                    except ValueError as err:
                        if 'PIN' in str(err):
                            pair_attempts['pin:' + ip].append(now)
                            return self.send_json({'error': str(err)}, 403)
                        raise
                return self.send_json({'ok': True, 'profile': profile})
            if p.startswith('/api/profiles/') and method == 'DELETE':
                pid = p[len('/api/profiles/'):]
                if pid == 'default': raise ValueError('Ana profil silinemez.')
                if pid == active_profile_id(): switch_profile('default')
                with connect() as c:
                    c.execute('DELETE FROM profiles WHERE id=?', (pid,))
                    c.execute('DELETE FROM profile_snapshots WHERE profile_id=?', (pid,))
                return self.send_json({'ok': True})
            if p == '/api/settings' and method == 'POST':
                if not self.is_local: return self.send_json({'error': 'Medya kaynağını yalnızca ana cihaz üzerinden değiştirebilirsiniz.'}, 403)
                source_type = str(d.get('type') or ('local' if d.get('localDir') else ('m3u' if d.get('m3uUrl') else 'xtream'))).strip().lower()
                epg_url = validate_host(d['epgUrl']) if str(d.get('epgUrl', '')).strip() else ''
                if source_type == 'local':
                    local_dir = str(local_media.validate_local_dir(d.get('localDir', '')))
                    config = {'type': 'local', 'name': string(d.get('name') or 'Yerel Klasör', 80), 'localDir': local_dir, 'epgUrl': epg_url}
                    test_provider = Provider(config); account = test_provider.account()
                    changed = config.get('localDir') != provider.config.get('localDir') or provider.mode != 'local'
                elif source_type == 'm3u':
                    m3u_url = validate_host(d.get('m3uUrl', ''))
                    config = {'type': 'm3u', 'name': string(d.get('name') or 'M3U Listesi', 80), 'm3uUrl': m3u_url, 'epgUrl': epg_url}
                    test_provider = Provider(config); account = test_provider.account()
                    changed = config.get('m3uUrl') != provider.config.get('m3uUrl') or provider.mode != 'm3u'
                else:
                    config = {'type': 'xtream', 'name': string(d.get('name') or 'Sunucu', 80), 'host': validate_host(d.get('host', '')), 'username': str(d.get('username') or provider.config.get('username', '')).strip()[:200], 'password': str(d.get('password') or provider.config.get('password', ''))[:200], 'epgUrl': epg_url}
                    if not config['username'] or not config['password']: raise ValueError('Kullanıcı adı ve şifre gerekli.')
                    test_provider = Provider(config); account = test_provider.account()
                    changed = provider.mode != 'xtream' or any(config[k] != provider.config.get(k) for k in ('host', 'username', 'password'))
                if sync_state['syncing']: raise ValueError('Katalog güncelleniyor. Bittikten sonra kaynağı değiştirin.')
                if changed:
                    stop_all()
                    with connect() as c:
                        for table in ('items', 'categories', 'favorites', 'progress', 'playlist_items', 'media_tracks', 'track_preferences'): c.execute('DELETE FROM ' + table)
                        c.execute("DELETE FROM meta WHERE key='catalog_updated'")
                save_config(config); provider = test_provider; meta_set('account', account); launch_sync()
                return self.send_json({'ok': True})
            if p == '/api/catalog/sync' and method == 'POST': launch_sync(); return self.send_json({'ok': True}, 202)
            if p == '/api/favorites' and method == 'POST':
                iid = str(d.get('id', '')); get_row(iid)
                with connect() as c:
                    if d.get('favorite', True): c.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)', (iid, stamp()))
                    else: c.execute('DELETE FROM favorites WHERE item_id=?', (iid,))
                return self.send_json({'ok': True})
            if p == '/api/progress' and method == 'POST':
                iid = str(d.get('id', '')); r = get_row(iid)
                if d.get('sessionId'):
                    with resource_lock: session = media_sessions.get(str(d['sessionId']))
                    if not session or session['item'] != iid:
                        return self.send_json({'error': 'İzleme başka bir oturumda devam ediyor.'}, 410)
                if r['kind'] not in ('vod', 'episode'): return self.send_json({'ok': True})
                pos = max(0, number(d.get('position'))); dur = max(0, number(d.get('duration')))
                if dur: pos = min(pos, dur)
                completed = bool(d.get('completed')) or (dur > 0 and pos / dur >= .95)
                with connect() as c: c.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?,?,?)', (iid, pos, dur, int(completed), stamp()))
                return self.send_json({'ok': True})
            if p.startswith('/api/progress/') and method == 'DELETE':
                with connect() as c: c.execute('DELETE FROM progress WHERE item_id=?', (p[len('/api/progress/'):],))
                return self.send_json({'ok': True})
            if p == '/api/playlists' and method == 'POST':
                name = string(d.get('name'), 100).strip()
                if not name: raise ValueError('Liste adı boş olamaz.')
                pid = secrets.token_urlsafe(12)
                with connect() as c: c.execute('INSERT INTO playlists VALUES(?,?,?)', (pid, name, stamp()))
                return self.send_json({'ok': True, 'id': pid}, 201)
            if p.startswith('/api/playlists/') and method in ('PATCH', 'DELETE'):
                pid = p[len('/api/playlists/'):]
                with connect() as c:
                    if not c.execute('SELECT 1 FROM playlists WHERE id=?', (pid,)).fetchone(): raise ValueError('Liste bulunamadı.')
                    if method == 'DELETE': c.execute('DELETE FROM playlists WHERE id=?', (pid,))
                    else:
                        if 'name' in d:
                            name = string(d['name'], 100).strip()
                            if not name: raise ValueError('Liste adı boş olamaz.')
                            c.execute('UPDATE playlists SET name=? WHERE id=?', (name, pid))
                        if d.get('itemId'):
                            iid = str(d['itemId']); get_row(iid)
                            n = c.execute('SELECT coalesce(max(position),-1)+1 FROM playlist_items WHERE playlist_id=?', (pid,)).fetchone()[0]
                            c.execute('INSERT OR IGNORE INTO playlist_items VALUES(?,?,?)', (pid, iid, n))
                        if d.get('removeItemId'): c.execute('DELETE FROM playlist_items WHERE playlist_id=? AND item_id=?', (pid, str(d['removeItemId'])))
                        if isinstance(d.get('order'), list):
                            existing = {r[0] for r in c.execute('SELECT item_id FROM playlist_items WHERE playlist_id=?', (pid,))}
                            order = d['order']
                            if not all(isinstance(x, str) for x in order) or len(order) != len(existing) or set(order) != existing: raise ValueError('Sıralama listedeki tüm içerikleri içermeli.')
                            c.executemany('UPDATE playlist_items SET position=? WHERE playlist_id=? AND item_id=?', [(i, pid, iid) for i, iid in enumerate(order)])
                return self.send_json({'ok': True})
            if p == '/api/play' and method == 'POST': return self.send_json(play_item(str(d.get('id', '')), str(d.get('mode', 'direct')), d.get('start', 0), d))
            if p.startswith('/api/play/'):
                sid = p.split('/')[3]
                with resource_lock:
                    s = media_sessions.get(sid)
                    if s: s['touched'] = time.monotonic()
                if method == 'DELETE':
                    stop_session(sid)
                    return self.send_json({'ok': True})
                if method == 'POST' and p.endswith('/ping'):
                    if not s: return self.send_json({'error': 'Oynatma başka cihazda başlatıldı veya oturum sona erdi.'}, 410)
                    window = playback.ping(sid, position=d.get('position')) if s.get('sourceToken') else {}
                    return self.send_json({'ok': True, **(window or {})})
                if method == 'POST' and p.endswith('/pause'):
                    if not s: return self.send_json({'error': 'Oynatma oturumu sona erdi.'}, 410)
                    if s.get('sourceToken'): playback.pause(sid, bool(d.get('paused')))
                    return self.send_json({'ok': True})
            if p == '/api/track-preferences' and method == 'POST':
                iid = str(d.get('id', '')); get_row(iid)
                return self.send_json({'ok': True, 'selection': save_track_preferences(iid, d)})
            if p == '/api/import' and method == 'POST': return self.import_state(d.get('data'))
            if p == '/api/devices/revoke' and method == 'POST':
                if not self.is_local: return self.send_json({'error': 'Bu işlem yalnızca ana cihaz üzerinde kullanılabilir.'}, 403)
                with connect() as c: c.execute('DELETE FROM devices')
                stop_all()
                return self.send_json({'ok': True}, extra={'Set-Cookie': self.device_cookie()})
            self.send_json({'error': 'İşlem bulunamadı.'}, 404)
        except Exception as e: self.handle_error(e)
    def static(self, p):
        if p == '/': p = '/index.html'
        target = (PUBLIC / p.lstrip('/')).resolve()
        if not target.is_relative_to(PUBLIC.resolve()) or not target.is_file():
            return self.send_json({'error': 'Dosya bulunamadı.'}, 404)
        ext = {}
        if self.is_local and p == '/index.html' and not self.authorized(): ext['Set-Cookie'] = self.device_cookie()
        # Assets are app-owned; provider metadata never becomes HTML.
        ext['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        raw = target.read_bytes()
        typ = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
        self.headers_out(200, typ + ('; charset=utf-8' if typ.startswith('text/') else ''), len(raw), ext)
        if self.command != 'HEAD': self.wfile.write(raw)
    def image(self, url):
        if not url: return self.send_json({'error': 'Görsel yok.'}, 404)
        digest = hashlib.sha256(url.encode()).hexdigest()
        folder = DATA / 'images'; folder.mkdir(exist_ok=True)
        target = folder / digest
        with image_locks[int(digest[0], 16)]:
            if target.exists():
                b = target.read_bytes()
            else:
                with remote(url, timeout=12) as r:
                    if not r.headers.get('Content-Type', '').lower().startswith('image/'): return self.send_json({'error': 'Görsel bulunamadı.'}, 404)
                    b = r.read(5 * 1024 * 1024 + 1)
                if len(b) > 5 * 1024 * 1024: raise ValueError('Görsel çok büyük.')
                # Persist only raster images, never active SVG/HTML returned by a provider.
                if not (b.startswith(b'\xff\xd8\xff') or b.startswith(b'\x89PNG') or b.startswith(b'GIF8') or (b.startswith(b'RIFF') and b[8:12] == b'WEBP')):
                    return self.send_json({'error': 'Görsel biçimi desteklenmiyor.'}, 404)
                target.write_bytes(b)
        typ = 'image/jpeg' if b.startswith(b'\xff\xd8') else ('image/png' if b.startswith(b'\x89PNG') else ('image/gif' if b.startswith(b'GIF') else 'image/webp'))
        self.headers_out(200, typ, len(b), {'Cache-Control': 'private, max-age=86400'})
        if self.command != 'HEAD': self.wfile.write(b)
    def epg(self, iid):
        r = get_row(iid)
        if r['kind'] != 'live': raise ValueError('Yayın akışı yalnızca canlı yayınlar için kullanılabilir.')
        if provider.mode != 'xtream':
            return self.send_json({'programs': []})
        d = provider.api('get_short_epg', stream_id=r['provider_id'], limit=12)
        programs = []
        def decode(x):
            try: return base64.b64decode(str(x), validate=True).decode('utf-8')
            except (ValueError, UnicodeError): return string(x, 10000)
        for e in d.get('epg_listings', []) if isinstance(d, dict) else []:
            if not isinstance(e, dict): continue
            programs.append({'title': decode(e.get('title', '')), 'description': decode(e.get('description', '')), 'start': e.get('start_timestamp') or e.get('start'), 'end': e.get('stop_timestamp') or e.get('end')})
        return self.send_json({'programs': programs})
    def source_failure(self, message, code, sid=None, source_token=None):
        with resource_lock:
            owner = media_sessions.get(sid) if sid else internal_sources.get(source_token)
            if owner is not None: owner['source_error'] = {'error': message, 'code': code}
        return PlaybackError(message, code=code)
    def serve_sidecar_subtitle(self, tail):
        if provider.mode != 'local':
            return self.send_json({'error': 'Yerel altyazı yalnızca yerel klasör modunda kullanılabilir.'}, 403)
        parts = tail.strip('/').split('/')
        if len(parts) != 2 or not parts[1].endswith('.vtt'):
            return self.send_json({'error': 'Altyazı adresi geçersiz.'}, 404)
        iid = urllib.parse.unquote(parts[0])
        try:
            idx = int(parts[1][:-4])
        except ValueError:
            return self.send_json({'error': 'Altyazı dizini geçersiz.'}, 404)
        r = get_row(iid)
        subs = json.loads(r['extra']).get('subtitles') or []
        if idx < 0 or idx >= len(subs):
            return self.send_json({'error': 'Altyazı bulunamadı.'}, 404)
        root = local_media.validate_local_dir(provider.config.get('localDir', ''))
        target = Path(subs[idx]).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return self.send_json({'error': 'Altyazı dosyası bulunamadı.'}, 404)
        raw_bytes = target.read_bytes()[:2 * 1024 * 1024]
        try:
            text = raw_bytes.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw_bytes.decode('cp1254', errors='replace')
        if not text.lstrip().startswith('WEBVTT'):
            text = 'WEBVTT\n\n' + re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', text.replace('\r\n', '\n'))
        out = text.encode('utf-8')
        self.headers_out(200, 'text/vtt; charset=utf-8', len(out))
        if self.command != 'HEAD':
            self.wfile.write(out)

    def proxy_local(self, raw_path, sid=None):
        if provider.mode != 'local':
            return self.send_json({'error': 'Yerel dosya modu etkin değil.'}, 403)
        try:
            root = local_media.validate_local_dir(provider.config.get('localDir', ''))
            target = Path(raw_path).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                return self.send_json({'error': 'Medya dosyası bulunamadı.'}, 404)
            size = target.stat().st_size
            typ = mimetypes.guess_type(str(target))[0] or 'video/mp4'
            range_hdr = self.headers.get('Range', '')
            start, end, status = 0, size - 1, 200
            extra = {'Accept-Ranges': 'bytes'}
            m = re.fullmatch(r'bytes=(\d+)-(\d*)', range_hdr.strip())
            if m and size > 0:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                if start >= size or start > end:
                    return self.send_json({'error': 'Geçersiz zaman aralığı.'}, 416)
                end = min(end, size - 1)
                status = 206
                extra['Content-Range'] = f'bytes {start}-{end}/{size}'
            remaining = max(0, end - start + 1) if size > 0 else 0
            self.headers_out(status, typ, remaining, extra)
            if self.command == 'HEAD' or remaining == 0:
                return
            with target.open('rb') as f:
                f.seek(start)
                while remaining > 0:
                    if sid:
                        with resource_lock:
                            session = media_sessions.get(sid)
                            if not session: break
                            session['touched'] = time.monotonic()
                    chunk = f.read(min(128 * 1024, remaining))
                    if not chunk: break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except ValueError:
            return self.send_json({'error': 'Medya dosyasına erişilemiyor.'}, 403)
    def proxy(self, url, sid=None, source_token=None):
        if isinstance(url, str) and url.startswith('local://'):
            return self.proxy_local(url[len('local://'):], sid)
        hdr = {}
        for k in ('Range', 'If-Range'):
            if self.headers.get(k): hdr[k] = self.headers[k]
        try: upstream = remote(url, timeout=30, headers=hdr)
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 416:
                return self.send_json({'error': 'Bu zaman aralığı sunucu tarafından desteklenmiyor.'}, 416)
            raise self.source_failure('IPTV sağlayıcısı bu içeriğin video bağlantısını açamadı. Daha sonra yeniden deneyin.', 'upstream_unavailable', sid, source_token) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise self.source_failure('IPTV video sunucusuna ulaşılamadı. Daha sonra yeniden deneyin.', 'upstream_unavailable', sid, source_token) from None
        with upstream as r:
            with resource_lock:
                owner = media_sessions.get(sid) if sid else internal_sources.get(source_token)
                if (sid or source_token) and owner is None:
                    abort_connections([r])
                    return self.send_json({'error': 'Oynatma oturumu sona erdi.'}, 410)
                if owner is not None:
                    # Completed responses are discarded on the next request to bound bookkeeping.
                    owner['connections'] = {x for x in owner.get('connections', ()) if not x.closed}
                    owner['connections'].add(r)
            typ = r.headers.get('Content-Type', 'application/octet-stream').split(';')[0]
            if typ.lower() in ('text/html', 'application/xhtml+xml', 'image/svg+xml'):
                if not r.read(1):
                    raise self.source_failure('IPTV sağlayıcısı bu içerik için video göndermiyor (boş yanıt). Daha sonra yeniden deneyin.', 'upstream_empty', sid, source_token)
                raise self.source_failure('IPTV sağlayıcısı video yerine bir hata sayfası döndürdü. Daha sonra yeniden deneyin.', 'upstream_unavailable', sid, source_token)
            final_url = r.geturl()
            is_hls = 'mpegurl' in typ.lower() or urllib.parse.urlsplit(final_url).path.endswith('.m3u8')
            if sid and is_hls:
                content = r.read(3 * 1024 * 1024 + 1)
                if len(content) > 3 * 1024 * 1024: raise RuntimeError('Yayın listesi çok büyük.')
                text = content.decode('utf-8-sig')
                if not text.lstrip().startswith('#EXTM3U'): raise RuntimeError('Sunucu geçerli bir HLS yayını göndermedi.')
                def rewrite(match): return 'URI="' + resource_for(sid, urllib.parse.urljoin(final_url, match[1])) + '"'
                lines = []
                for line in text.splitlines():
                    if line.startswith('#'): lines.append(re.sub(r'URI="([^"]+)"', rewrite, line))
                    elif line.strip(): lines.append(resource_for(sid, urllib.parse.urljoin(final_url, line.strip())))
                    else: lines.append(line)
                b = ('\n'.join(lines) + '\n').encode()
                self.headers_out(200, 'application/vnd.apple.mpegurl', len(b))
                if self.command != 'HEAD': self.wfile.write(b)
                return
            extra = {k: r.headers[k] for k in ('Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified') if r.headers.get(k)}
            length = r.headers.get('Content-Length')
            first_block = r.read(1) if self.command != 'HEAD' else b''
            if self.command != 'HEAD' and not first_block:
                raise self.source_failure('IPTV sağlayıcısı bu içerik için video göndermiyor (boş yanıt). Daha sonra yeniden deneyin.', 'upstream_empty', sid, source_token)
            self.headers_out(r.status, typ, length, extra)
            if self.command == 'HEAD': return
            self.wfile.write(first_block)
            while True:
                if sid:
                    with resource_lock:
                        session = media_sessions.get(sid)
                        if not session: break
                        session['touched'] = time.monotonic()
                # Forward available bytes without waiting for a full 128 KiB
                # block, especially on slower live feeds.
                block = r.read1(64 * 1024) if hasattr(r, 'read1') else r.read(64 * 1024)
                if not block: break
                self.wfile.write(block)
    def media(self, p):
        parts = p.strip('/').split('/')
        if len(parts) < 3: raise ValueError('Yayın adresi geçersiz.')
        sid = parts[1]
        with resource_lock:
            s = media_sessions.get(sid)
            if not s: return self.send_json({'error': 'Oynatma oturumu sona erdi.'}, 410)
            s['touched'] = time.monotonic()
        if len(parts) == 4 and parts[2] == 'proxy':
            with resource_lock: url = s['resources'].get(parts[3])
            if not url: return self.send_json({'error': 'Yayın parçası bulunamadı.'}, 404)
            return self.proxy(url, sid)
        if len(parts) != 3: raise ValueError('Yayın dosyası geçersiz.')
        try: path = playback.get_file(sid, parts[2])
        except (ValueError, FileNotFoundError): return self.send_json({'error': 'Yayın parçası hazırlanıyor veya oturum sona erdi.'}, 404)
        typ = 'application/vnd.apple.mpegurl' if path.suffix == '.m3u8' else ('text/vtt; charset=utf-8' if path.suffix == '.vtt' else 'video/mp2t')
        # Segments are immutable for their opaque session. Stream them instead
        # of allocating an entire high bitrate segment in every request thread.
        try:
            with path.open('rb') as content:
                size = os.fstat(content.fileno()).st_size
                self.headers_out(200, typ, size)
                if self.command != 'HEAD':
                    while block := content.read(64 * 1024): self.wfile.write(block)
        except FileNotFoundError:
            return self.send_json({'error': 'Yayın parçası hazırlanıyor veya oturum sona erdi.'}, 404)
    def import_state(self, data):
        merge_state_dict(data)
        return self.send_json({'ok': True})


def export_state_dict():
    with connect() as c:
        return {
            'version': 1,
            'exportedAt': stamp(),
            'favorites': [dict(r) for r in c.execute('SELECT * FROM favorites')],
            'progress': [dict(r) for r in c.execute('SELECT * FROM progress')],
            'playlists': [dict(r) for r in c.execute('SELECT * FROM playlists')],
            'playlistItems': [dict(r) for r in c.execute('SELECT * FROM playlist_items')],
            'trackPreferences': [dict(r) for r in c.execute('SELECT * FROM track_preferences')],
            'items': backup_items(c),
        }


def merge_state_dict(data):
    if not isinstance(data, dict) or data.get('version') != 1: raise ValueError('Geçerli bir Mavie yedeği seçin.')
    tables = ('favorites', 'progress', 'playlists', 'playlistItems', 'trackPreferences', 'items')
    if any(not isinstance(data.get(t, []), list) or len(data.get(t, [])) > 100000 for t in tables): raise ValueError('Yedek biçimi veya boyutu geçersiz.')
    metadata = [portable_item_row(r) for r in data.get('items', [])]
    def parse_iso(value):
        if value is None or value == '': return stamp()
        if not isinstance(value, str) or len(value) > 64: raise ValueError('Yedek zaman bilgisi geçersiz.')
        try:
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).isoformat()
        except ValueError: raise ValueError('Yedek zaman bilgisi geçersiz.') from None
    def is_newer(c, table, item_id, incoming_iso):
        row = c.execute(f'SELECT updated_at FROM {table} WHERE item_id=?', (item_id,)).fetchone()
        if not row or not row[0]: return True
        try:
            existing = dt.datetime.fromisoformat(str(row[0]).replace('Z', '+00:00'))
            if existing.tzinfo is None: existing = existing.replace(tzinfo=dt.timezone.utc)
            incoming = dt.datetime.fromisoformat(incoming_iso.replace('Z', '+00:00'))
            return incoming >= existing
        except ValueError: return True
    # Merge state; never run SQL or accept settings/credentials from an imported backup.
    try:
        with connect() as c:
            c.executemany('INSERT OR IGNORE INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', metadata)
            for r in data.get('favorites', []):
                if ID_RE.fullmatch(str(r['item_id'])): c.execute('INSERT OR IGNORE INTO favorites VALUES(?,?)', (r['item_id'], parse_iso(r.get('created_at'))))
            for r in data.get('progress', []):
                if ID_RE.fullmatch(str(r['item_id'])):
                    updated = parse_iso(r.get('updated_at'))
                    if is_newer(c, 'progress', r['item_id'], updated):
                        pos = max(0, number(r.get('position'))); dur = max(0, number(r.get('duration')))
                        c.execute('INSERT OR REPLACE INTO progress VALUES(?,?,?,?,?)', (r['item_id'], min(pos, dur) if dur else pos, dur, int(bool(r.get('completed'))), updated))
            for r in data.get('playlists', []):
                if re.fullmatch(r'[A-Za-z0-9_-]{1,100}', str(r['id'])):
                    c.execute('INSERT OR IGNORE INTO playlists VALUES(?,?,?)', (r['id'], string(r.get('name') or 'İçe aktarılan liste', 100), parse_iso(r.get('created_at'))))
            for r in data.get('playlistItems', []):
                if ID_RE.fullmatch(str(r['item_id'])) and c.execute('SELECT 1 FROM playlists WHERE id=?', (r['playlist_id'],)).fetchone():
                    c.execute('INSERT OR IGNORE INTO playlist_items VALUES(?,?,?)', (r['playlist_id'], r['item_id'], int(number(r.get('position')))))
            for r in data.get('trackPreferences', []):
                if not isinstance(r, dict) or not ID_RE.fullmatch(str(r.get('item_id', ''))): raise ValueError('Yedekteki parça seçimi geçersiz.')
                updated = parse_iso(r.get('updated_at'))
                pref = r.get('data', '{}')
                if isinstance(pref, str): pref = json.loads(pref)
                if not isinstance(pref, dict): raise ValueError('Yedekteki parça seçimi geçersiz.')
                checks = {'audio': r'(?:auto|stream:[0-9]{1,5})', 'subtitle': r'(?:off|stream:[0-9]{1,5})',
                          'clientAudio': r'(?:auto|hls:[0-9]{1,5}|native:[0-9]{1,5})', 'clientSubtitle': r'(?:off|hls:[0-9]{1,5}|native:[0-9]{1,5})'}
                if any(value is not None and (key not in checks or not isinstance(value, str) or not re.fullmatch(checks[key], value)) for key, value in pref.items()):
                    raise ValueError('Yedekteki parça seçimi geçersiz.')
                if pref.get('audio', 'auto') is None or pref.get('subtitle', 'off') is None: raise ValueError('Parça seçimi boş olamaz.')
                if is_newer(c, 'track_preferences', r['item_id'], updated):
                    c.execute('INSERT OR REPLACE INTO track_preferences VALUES(?,?,?)', (r['item_id'], json.dumps({key:value for key,value in pref.items() if key in checks}), updated))

    except (KeyError, TypeError, sqlite3.IntegrityError): raise ValueError('Yedek verileri geçersiz. Hiçbir değişiklik kaydedilmedi.') from None


def cleanup_loop(stop_event):
    while not stop_event.wait(5):
        now = time.monotonic()
        with resource_lock: stale = [sid for sid, s in media_sessions.items() if now - s['touched'] > 65]
        for sid in stale:
            stop_session(sid)


def run_server(
    host='0.0.0.0',
    port=8844,
    parent_pid=None,
    install_signals=True,
    stop_event=None,
    ready_event=None,
):
    global HTTP_PORT, playback
    configure_utf8_stdio()
    HTTP_PORT = int(port)
    initialize()
    ffmpeg_path = None
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        pass
    playback = PlaybackManager(DATA, ffmpeg_path)
    server = ThreadingHTTPServer((host, int(port)), Handler)
    server.daemon_threads = True
    HTTP_PORT = int(server.server_address[1])
    (DATA / 'server.pid').write_text(str(os.getpid()))
    if stop_event is None:
        stop_event = threading.Event()

    def stop(signum=None, frame=None):
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    if install_signals and threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

    def watch_stop():
        stop_event.wait()
        with contextlib.suppress(Exception):
            server.shutdown()

    threading.Thread(target=watch_stop, daemon=True, name='server-stop-watcher').start()
    threading.Thread(target=cleanup_loop, args=(stop_event,), daemon=True).start()
    if parent_pid is not None:
        def watch_app():
            while not stop_event.wait(.5):
                if os.getppid() != parent_pid:
                    stop(None, None)
                    return
        threading.Thread(target=watch_app, daemon=True, name='app-lifetime').start()
    if provider.configured:
        if not meta_get('catalog_updated'):
            launch_sync()
        else:
            def check_account():
                try:
                    meta_set('account', provider.account())
                except (ValueError, RuntimeError):
                    pass
            threading.Thread(target=check_account, daemon=True).start()
    if ready_event is not None:
        ready_event.set()
    print(f'Mavie hazır: http://localhost:{HTTP_PORT}', flush=True)
    try:
        server.serve_forever(poll_interval=.3)
    finally:
        stop_event.set()
        stop_all()
        playback.close()
        server.server_close()
        with contextlib.suppress(OSError):
            if (DATA / 'server.pid').read_text().strip() == str(os.getpid()):
                (DATA / 'server.pid').unlink()


def main():
    p = argparse.ArgumentParser(description='Mavie yerel medya sunucusu')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=8844)
    p.add_argument('--parent-pid', type=int, default=None, help='Exit when the owning app process exits')
    args = p.parse_args()
    run_server(host=args.host, port=args.port, parent_pid=args.parent_pid, install_signals=True)


if __name__ == '__main__':
    main()
