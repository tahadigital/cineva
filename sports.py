"""Standard XMLTV EPG parser and live program guide matcher for Mavie.

Reads user-configured XMLTV (.xml or .xml.gz) program guides cleanly without scraping third-party sites.
"""
from __future__ import annotations

import datetime as dt
import functools
import gzip
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    ZONE = ZoneInfo('Europe/Istanbul')
except ZoneInfoNotFoundError:
    ZONE = dt.timezone(dt.timedelta(hours=3))
MAX_PAGE = 8 * 1024 * 1024
FRESH = 15 * 60
MAX_STALE = 12 * 60 * 60
_cache = {}
_lock = threading.Lock()
_REGION_RE = re.compile(r'^\s*(?:(?:vip\s+)?(?:tr|en|us|uk|de|fr|es)|turkey|intl)\s*[:|➤\-]\s*')
_QUALITY_RE = re.compile(r'(?:[\s|\[\]()\-]+(?:fhd|hd|uhd|sd|raw|hevc|h265|4k|1080p|720p)\b[\s|\[\]()\-]*)+$')
_NONALNUM_RE = re.compile(r'[^a-z0-9+]')
_XMLTV_TS_RE = re.compile(r'^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\s*([+-]\d{4}))?')
_SPORT_CATEGORY_RE = re.compile(r'\b(sport|sports|spor|futbol|football|soccer|basketbol|basketball|tennis|tenis|motorsport|formula|racing|boxing|ufc|golf)\b', re.I)


@functools.lru_cache(maxsize=32000)
def _ascii(value):
    text = str(value or '').replace('ı', 'i').replace('İ', 'i')
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).lower()


@functools.lru_cache(maxsize=32000)
def channel_key(name):
    text = _REGION_RE.sub('', _ascii(name))
    text = _QUALITY_RE.sub('', text)
    return _NONALNUM_RE.sub('', text)


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


def parse_xmltv(raw_payload, day, tz=ZONE):
    """Parse standard XMLTV guide bytes safely without entity expansion."""
    if isinstance(raw_payload, bytes):
        if raw_payload[:2] == b'\x1f\x8b':
            raw_payload = gzip.decompress(raw_payload)
            if len(raw_payload) > MAX_PAGE * 2:
                raise RuntimeError('EPG rehberi çok büyük.')
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


def get_listings(day, fetch, epg_url='', refresh=False, tz=ZONE):
    source = str(epg_url or '').strip()
    if not source:
        return {'date': day.isoformat(), 'timezone': str(tz), 'source': '', 'stale': False, 'events': [], 'configured': False}
    cache_key = (source, day)
    with _lock:
        now = time.time()
        cached = _cache.get(cache_key)
        if not cached or now - cached[0] >= (15 if refresh else FRESH):
            try:
                with fetch(source, timeout=15, headers={'User-Agent': 'Mavie/3.0 (XMLTV EPG)'}) as response:
                    payload = response.read(MAX_PAGE + 1)
                if len(payload) > MAX_PAGE:
                    raise RuntimeError('XMLTV rehberi çok büyük.')
                events = parse_xmltv(payload, day, tz)
                cached = _cache[cache_key] = (time.time(), events)
                for old in list(_cache):
                    if now - _cache[old][0] > MAX_STALE:
                        _cache.pop(old, None)
                stale = False
            except (OSError, RuntimeError, UnicodeError, ValueError):
                if not cached or now - cached[0] > MAX_STALE:
                    raise RuntimeError('XMLTV yayın rehberine ulaşılamadı. Bağlantıyı kontrol edin.') from None
                stale = True
        else:
            stale = False
    return {
        'date': day.isoformat(),
        'timezone': str(tz),
        'source': source,
        'stale': stale,
        'events': cached[1],
        'configured': True,
    }
