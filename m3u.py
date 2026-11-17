"""Standard M3U/M3U8 playlist parser and Open-License Demo catalog for Cineva."""
from __future__ import annotations

import hashlib
import re

_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
_EXT_RE = re.compile(r'\.([a-z0-9]{2,5})(?:[?#]|$)', re.I)

# 100% legal Creative Commons / Blender Foundation open films for first-run demo & App Review.
DEMO_CATALOG = [
    {
        'id': 'vod:demo_bbb',
        'provider_id': 'demo_bbb',
        'kind': 'vod',
        'name': 'Big Buck Bunny (Demo · 1080p)',
        'poster': 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/BigBuckBunny.jpg',
        'category_id': 'demo_anim',
        'category_name': 'Açık Sinema / Demo',
        'year': '2008',
        'rating': 8.2,
        'extension': 'mp4',
        'url': 'https://storage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
        'extra': {
            'duration': 596,
            'genre': 'Animation, Comedy, Family',
            'plot': 'Blender Vakfı tarafından Creative Commons Attribution 3.0 lisansıyla sunulan açık kaynaklı kısa animasyon filmi.',
            'director': 'Sacha Goedegebure',
            'cast': 'Blender Open Movie Project',
        },
    },
    {
        'id': 'vod:demo_sintel',
        'provider_id': 'demo_sintel',
        'kind': 'vod',
        'name': 'Sintel (Demo · 1080p)',
        'poster': 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/Sintel.jpg',
        'category_id': 'demo_anim',
        'category_name': 'Açık Sinema / Demo',
        'year': '2010',
        'rating': 8.5,
        'extension': 'mp4',
        'url': 'https://storage.googleapis.com/gtv-videos-bucket/sample/Sintel.mp4',
        'extra': {
            'duration': 888,
            'genre': 'Animation, Fantasy, Adventure',
            'plot': 'Genç bir gezginin yavru ejderhasını arayışını konu alan Blender açık kaynak kısa filmi.',
            'director': 'Colin Levy',
            'cast': 'Halina Reijn, Thom Hoffman',
        },
    },
    {
        'id': 'vod:demo_tears',
        'provider_id': 'demo_tears',
        'kind': 'vod',
        'name': 'Tears of Steel (Demo · Sci-Fi)',
        'poster': 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/TearsOfSteel.jpg',
        'category_id': 'demo_scifi',
        'category_name': 'Bilim Kurgu / Demo',
        'year': '2012',
        'rating': 7.9,
        'extension': 'mp4',
        'url': 'https://storage.googleapis.com/gtv-videos-bucket/sample/TearsOfSteel.mp4',
        'extra': {
            'duration': 734,
            'genre': 'Sci-Fi, Action',
            'plot': 'Amsterdam’da geçen, Creative Commons açık lisanslı bilim kurgu kısa filmi.',
            'director': 'Ian Hubert',
            'cast': 'Derek de Lint, Sergio Hasselbaink',
        },
    },
    {
        'id': 'vod:demo_elephants',
        'provider_id': 'demo_elephants',
        'kind': 'vod',
        'name': 'Elephants Dream (Demo · Open Movie)',
        'poster': 'https://storage.googleapis.com/gtv-videos-bucket/sample/images/ElephantsDream.jpg',
        'category_id': 'demo_anim',
        'category_name': 'Açık Sinema / Demo',
        'year': '2006',
        'rating': 7.5,
        'extension': 'mp4',
        'url': 'https://storage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
        'extra': {
            'duration': 653,
            'genre': 'Animation, Sci-Fi, Mystery',
            'plot': 'Dünyanın ilk açık kaynaklı 3D kısa animasyon filmi (Orange Open Movie Project).',
            'director': 'Bassam Kurdali',
            'cast': 'Tygo Gernandt, Cas Jansen',
        },
    },
]


def parse_m3u(text):
    """Parse standard #EXTM3U / #EXTINF playlist into normalized items and optional EPG URL."""
    lines = str(text or '').splitlines()
    epg_url = ''
    items = []
    pending = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#EXTM3U'):
            attrs = dict(_ATTR_RE.findall(line))
            epg_url = attrs.get('url-tvg') or attrs.get('x-tvg-url') or ''
            continue
        if line.startswith('#EXTINF:'):
            attrs = dict(_ATTR_RE.findall(line))
            title = line.split(',', 1)[1].strip() if ',' in line else attrs.get('tvg-name', '')
            pending = {
                'name': title[:500] or attrs.get('tvg-name', '') or 'Adsız Yayın',
                'tvg_id': attrs.get('tvg-id', '')[:100],
                'poster': attrs.get('tvg-logo', '')[:3000],
                'group': attrs.get('group-title', '')[:200] or 'Genel',
                'type': attrs.get('type', '').lower(),
            }
            continue
        if line.startswith('#'):
            continue
        if line.startswith(('http://', 'https://')):
            meta = pending or {'name': line.rsplit('/', 1)[-1][:120] or 'Akış', 'tvg_id': '', 'poster': '', 'group': 'Genel', 'type': ''}
            pending = None
            ext_m = _EXT_RE.search(line)
            ext = ext_m.group(1).lower() if ext_m else 'm3u8'
            is_vod = meta['type'] in ('movie', 'vod') or ext in ('mp4', 'mkv', 'avi', 'mov', 'webm')
            kind = 'vod' if is_vod else 'live'
            digest = hashlib.sha1(f'{kind}:{line}'.encode()).hexdigest()[:16]
            items.append({
                'id': f'{kind}:m3u_{digest}',
                'provider_id': f'm3u_{digest}',
                'kind': kind,
                'name': meta['name'],
                'poster': meta['poster'],
                'category_id': hashlib.sha1(meta['group'].encode()).hexdigest()[:10],
                'category_name': meta['group'],
                'extension': ext[:12],
                'url': line,
                'tvg_id': meta['tvg_id'],
            })
    return {'epgUrl': epg_url, 'items': items}
