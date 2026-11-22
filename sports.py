"""Live Turkish sports schedule (Spor Ekranı) + standard XMLTV EPG parser for Mavie.

Uses Spor Ekranı automatically with zero setup when no custom XMLTV EPG URL is configured,
and cleanly parses user-configured XMLTV (.xml / .xml.gz) guides when provided.
"""
from __future__ import annotations

import datetime as dt
import functools
import gzip
import http.client
import json
import re
import threading
import time
import unicodedata
import urllib.error
import xml.etree.ElementTree as ET
import zlib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ZONE = ZoneInfo('Europe/Istanbul')
except ZoneInfoNotFoundError:
    ZONE = dt.timezone(dt.timedelta(hours=3))

SPOREKRANI_SOURCE = 'https://www.sporekrani.com/home/day/'
SPOREKRANI_MARKER = 'window.__INITIAL_STATE__='
MAX_SPOREKRANI_PAGE = 4 * 1024 * 1024
MAX_PAGE = 8 * 1024 * 1024
SPOREKRANI_FRESH = 5 * 60
FRESH = 15 * 60
MAX_STALE = 12 * 60 * 60
_cache = {}
_lock = threading.Lock()
_REGION_RE = re.compile(r'^\s*(?:(?:vip\s+)?(?:tr|en|us|uk|de|fr|es)|turkey|intl)\s*[:|➤\-]\s*')
_QUALITY_RE = re.compile(r'(?:[\s|\[\]()\-]+(?:fhd|hd|uhd|sd|raw|hevc|h265|4k|1080p|720p)\b[\s|\[\]()\-]*)+$')
_NONALNUM_RE = re.compile(r'[^a-z0-9+]')
_XMLTV_TS_RE = re.compile(r'^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\s*([+-]\d{4}))?')
_SPORT_CATEGORY_RE = re.compile(r'\b(sport|sports|spor|futbol|football|soccer|basketbol|basketball|tennis|tenis|motorsport|formula|racing|boxing|ufc|golf)\b', re.I)
_COMMENTARY_NOISE_RE = re.compile(r'basin toplantisi|spor bulteni|mac (?:onu|sonu|ozel)|tekrar')
_ALIASES = {
    'ssport1': 'ssport',
    'smartsporhd': 'sporsmart',
    'smartspor': 'sporsmart',
    'smartspor2': 'sporsmart2',
    'trtsporstar': 'trtsporyildiz',
}


@functools.lru_cache(maxsize=32000)
def _ascii(value):
    text = str(value or '').replace('ı', 'i').replace('İ', 'i')
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).lower()


@functools.lru_cache(maxsize=32000)
def channel_key(name):
    text = _REGION_RE.sub('', _ascii(name))
    text = _QUALITY_RE.sub('', text)
    normalized = _NONALNUM_RE.sub('', text)
    return _ALIASES.get(normalized, normalized)


def match_channels(events, catalog):
    wanted = {channel_key(label) for event in events for label in event['channels']}
    matches = {}
    for iid, name in catalog:
        key = channel_key(name)
        if not key or key not in wanted:
            continue
        text = _ascii(name)
        quality = 3 if re.search(r'\bfhd\b', text) else 2 if re.search(r'\bhd\b', text) else 1
        score = (quality, text.startswith('tr:') or text.startswith('en:'))
        if key not in matches or score > matches[key][0]:
            matches[key] = (score, {'id': iid, 'kind': 'live', 'name': name})
    return {
        label: matches[channel_key(label)][1]
        for event in events
        for label in event['channels']
        if channel_key(label) in matches
    }


def selected_date(value, today=None, tz=ZONE):
    today = today or dt.datetime.now(tz).date()
    if not value:
        return today
    try:
        day = dt.date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Geçersiz program rehberi tarihi.') from None
    if day.isoformat() != value or not -7 <= (day - today).days <= 14:
        raise ValueError('Program rehberi tarihi aralık dışında.')
    return day


def _label(value, limit=180):
    return ' '.join(value.split())[:limit] if isinstance(value, str) else ''


def parse_sporekrani(page, day):
    """Read only JSON embedded in Spor Ekranı SSR page; never execute scripts.

    Supports both the current normalized schema (`common.eventRows` + `common.eventChannels`)
    and the legacy inline schema (`common.events`).
    """
    try:
        payload = page.split(SPOREKRANI_MARKER, 1)[1]
        data, _ = json.JSONDecoder().raw_decode(payload.lstrip())
        common = data['common']
        if isinstance(common.get('eventRows'), list):
            rows = common['eventRows']
            channel_map = common.get('eventChannels') if isinstance(common.get('eventChannels'), dict) else {}
        elif isinstance(common.get('events'), list):
            rows = common['events']
            channel_map = {}
        else:
            raise TypeError
    except (ValueError, IndexError, TypeError, KeyError):
        raise RuntimeError('Spor yayın rehberi şu anda okunamadı.') from None

    events, seen = [], set()
    date = day.isoformat()
    time_re = re.compile(re.escape(date) + r' (?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d')
    for row in rows:
        if not isinstance(row, dict):
            continue
        iid = row.get('id')
        start = row.get('date_time')
        sport, title = _label(row.get('sport_name'), 50), _label(row.get('name'))
        if not isinstance(iid, int) or iid in seen or not sport or not title:
            continue
        if not isinstance(start, str) or not time_re.fullmatch(start):
            continue
        if _ascii(sport) == 'programlar' or row.get('event_type_name') not in ('match', 'commentary'):
            continue
        league = _label(row.get('league_name'))
        if row.get('event_type_name') == 'commentary' and _COMMENTARY_NOISE_RE.search(_ascii(title)):
            continue
        channels = []
        raw_channels = row.get('channels')
        for entry in raw_channels if isinstance(raw_channels, list) else []:
            if isinstance(entry, dict):
                ch_obj = entry
            elif isinstance(entry, (int, str)):
                ch_obj = channel_map.get(str(entry)) or channel_map.get(entry)
            else:
                ch_obj = None
            if not isinstance(ch_obj, dict) or ch_obj.get('active') in (0, '0', False):
                continue
            name = _label(ch_obj.get('name'), 100)
            if channel_key(name) == 'yayinyok':
                continue
            if name and name not in channels:
                channels.append(name)
        if not channels:
            continue
        qualifier = _label(row.get('post_fix'), 90)
        if qualifier and qualifier not in title:
            title += ' · ' + qualifier
        events.append({
            'id': str(iid),
            'title': title,
            'sport': sport,
            'league': league,
            'time': start[11:16],
            'featured': row.get('featured') in (1, '1', True),
            'channels': channels,
        })
        seen.add(iid)
    if rows and not any(isinstance(row, dict) and str(row.get('date_time', '')).startswith(date + ' ') for row in rows):
        raise RuntimeError('Spor yayın rehberi seçilen gün için doğrulanamadı.')
    return sorted(events, key=lambda event: (event['time'], event['id']))


def _parse_xmltv_time(raw, target_tz=ZONE):
    match = _XMLTV_TS_RE.match(str(raw or '').strip())
    if not match:
        return None
    y, mo, d, h, mi, s, offset = match.groups()
    try:
        naive = dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
    except ValueError:
        return None
    if offset:
        sign = 1 if offset[0] == '+' else -1
        delta = dt.timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5])) * sign
        aware = naive.replace(tzinfo=dt.timezone(delta))
        return aware.astimezone(target_tz)
    return naive.replace(tzinfo=target_tz)


def _gunzip_limited(raw_payload, max_bytes):
    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    chunks = []
    total = 0
    view = memoryview(raw_payload)
    for offset in range(0, len(raw_payload), 65536):
        part = dec.decompress(view[offset:offset + 65536], max_bytes - total + 1)
        total += len(part)
        if total > max_bytes:
            raise RuntimeError('EPG rehberi çok büyük.')
        chunks.append(part)
    tail = dec.flush(max_bytes - total + 1)
    total += len(tail)
    if total > max_bytes:
        raise RuntimeError('EPG rehberi çok büyük.')
    chunks.append(tail)
    return b''.join(chunks)


def parse_xmltv(raw_payload, day, tz=ZONE):
    """Parse standard XMLTV guide bytes safely without entity expansion."""
    if isinstance(raw_payload, bytes):
        if raw_payload[:2] == b'\x1f\x8b':
            try:
                raw_payload = _gunzip_limited(raw_payload, MAX_PAGE * 2)
            except (zlib.error, EOFError, OSError):
                raise RuntimeError('XMLTV yayın rehberi açılamadı.') from None
        text = raw_payload.decode('utf-8', errors='replace')
    else:
        text = str(raw_payload)
    upper = text[:4096].upper()
    if '<!ENTITY' in upper or '<!DOCTYPE' in upper:
        raise RuntimeError('Güvenlik nedeniyle XMLTV DTD bildirimlerine izin verilmiyor.')
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise RuntimeError('XMLTV yayın rehberi okunamadı.') from None
    if root.tag != 'tv':
        raise RuntimeError('Geçerli bir XMLTV dosyası değil.')

    channels_map = {}
    for ch in root.findall('channel'):
        cid = _label(ch.get('id', ''), 120)
        names = [_label(n.text or '', 100) for n in ch.findall('display-name') if _label(n.text or '', 100)]
        if cid:
            channels_map[cid] = names or [cid]

    events = []
    seen = set()
    date_str = day.isoformat()
    for index, prog in enumerate(root.findall('programme')):
        start_dt = _parse_xmltv_time(prog.get('start'), tz)
        if not start_dt or start_dt.date().isoformat() != date_str:
            continue
        title = _label(prog.findtext('title') or '', 180)
        channel_id = _label(prog.get('channel', ''), 120)
        if not title or not channel_id:
            continue
        ch_names = channels_map.get(channel_id) or [channel_id]
        cats = [_label(c.text or '', 60) for c in prog.findall('category') if _label(c.text or '', 60)]
        desc = _label(prog.findtext('desc') or '', 240)
        is_sport = any(_SPORT_CATEGORY_RE.search(c) for c in cats) or bool(_SPORT_CATEGORY_RE.search(title))
        sport_label = cats[0] if cats else ('Spor' if is_sport else 'Canlı Yayın')
        eid = f'{channel_id}:{start_dt.strftime("%H%M")}:{index}'
        if eid in seen:
            continue
        seen.add(eid)
        events.append({
            'id': eid,
            'title': title,
            'sport': sport_label,
            'league': cats[1] if len(cats) > 1 else desc[:90],
            'time': start_dt.strftime('%H:%M'),
            'featured': is_sport,
            'channels': ch_names,
            'channelId': channel_id,
        })
    return sorted(events, key=lambda e: (e['time'], e['id']))


def get_listings(day, fetch, epg_url='', refresh=False, tz=ZONE, source_mode='auto'):
    mode = str(source_mode or 'auto').strip().lower()
    epg = str(epg_url or '').strip()

    if mode == 'xmltv' and not epg:
        return {
            'date': day.isoformat(),
            'timezone': str(tz),
            'source': '',
            'sourceType': 'xmltv',
            'stale': False,
            'events': [],
            'configured': False,
        }

    use_xmltv = bool(epg) and mode != 'sporekrani'
    if use_xmltv:
        source = epg
        source_type = 'xmltv'
        fresh_ttl = FRESH
    else:
        source = SPOREKRANI_SOURCE + day.isoformat()
        source_type = 'sporekrani'
        fresh_ttl = SPOREKRANI_FRESH

    cache_key = (source, day)
    with _lock:
        now = time.time()
        cached = _cache.get(cache_key)
        if not cached or now - cached[0] >= (15 if refresh else fresh_ttl):
            try:
                req_headers = (
                    {'User-Agent': 'Mavie/2.2 (XMLTV EPG)', 'Accept-Encoding': 'gzip'}
                    if use_xmltv
                    else {'User-Agent': 'Mavie/2.2 (sports schedule)', 'Accept-Encoding': 'gzip'}
                )
                req_timeout = 15 if use_xmltv else 9
                max_bytes = MAX_PAGE if use_xmltv else MAX_SPOREKRANI_PAGE
                retryable_codes = (408, 429, 500, 502, 503, 504)
                payload = b''
                enc = ''
                for attempt in range(3):
                    try:
                        with fetch(source, timeout=req_timeout, headers=req_headers) as response:
                            payload = response.read(max_bytes + 1)
                            headers = getattr(response, 'headers', None)
                            enc = (headers.get('Content-Encoding', '') if headers else '').lower()
                        break
                    except urllib.error.HTTPError as err:
                        code = err.code
                        err.close()
                        if code not in retryable_codes or attempt >= 2:
                            raise RuntimeError(f'HTTP {code}') from None
                    except (http.client.HTTPException, urllib.error.URLError, TimeoutError, OSError):
                        if attempt >= 2:
                            raise
                    time.sleep(0.15 * (2 ** attempt))

                if len(payload) > max_bytes:
                    raise RuntimeError('XMLTV rehberi çok büyük.' if use_xmltv else 'Spor yayın rehberi çok büyük.')
                if use_xmltv:
                    if 'gzip' in enc and payload[:2] != b'\x1f\x8b':
                        try:
                            payload = _gunzip_limited(payload, MAX_PAGE * 2)
                        except (zlib.error, EOFError, OSError):
                            raise RuntimeError('XMLTV yayın rehberi açılamadı.') from None
                    events = parse_xmltv(payload, day, tz)
                else:
                    if 'gzip' in enc or payload[:2] == b'\x1f\x8b':
                        try:
                            payload = _gunzip_limited(payload, MAX_SPOREKRANI_PAGE * 2)
                        except (zlib.error, EOFError, OSError):
                            raise RuntimeError('Spor yayın rehberi açılamadı.') from None
                    events = parse_sporekrani(payload.decode('utf-8', errors='replace'), day)
                cached = _cache[cache_key] = (time.time(), events)
                for old in list(_cache):
                    if now - _cache[old][0] > MAX_STALE:
                        _cache.pop(old, None)
                stale = False
            except (OSError, RuntimeError, UnicodeError, ValueError, http.client.HTTPException):
                if not cached or now - cached[0] > MAX_STALE:
                    msg = (
                        'XMLTV yayın rehberine ulaşılamadı. Bağlantıyı kontrol edin.'
                        if use_xmltv
                        else 'Spor yayın rehberine ulaşılamadı. Biraz sonra tekrar dene.'
                    )
                    raise RuntimeError(msg) from None
                stale = True
        else:
            stale = False
    return {
        'date': day.isoformat(),
        'timezone': str(tz),
        'source': source,
        'sourceType': source_type,
        'stale': stale,
        'events': cached[1],
        'configured': True,
    }
