"""Secure local folder media scanner, filename parser, and subtitle sidecar finder for Mavie."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

VIDEO_EXTS = frozenset({'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.ts'})
SUBTITLE_EXTS = frozenset({'.srt', '.vtt', '.ass', '.ssa'})
BLOCKED_ROOTS = frozenset({'/', '/bin', '/sbin', '/usr', '/etc', '/var', '/System', '/Library', 'C:\\', 'C:\\Windows'})

_YEAR_RE = re.compile(r'\b((?:19|20)\d{2})\b')
_EPISODE_RE = re.compile(r'\bS(\d{1,2})E(\d{1,2})\b', re.I)
_NOISE_RE = re.compile(
    r'\b(?:1080p|720p|2160p|4k|uhd|fhd|hd|bluray|bdrip|web-?dl|webrip|hdtv|x264|x265|hevc|aac|ac3|dts|dual|tr|eng|sub|dub)\b.*',
    re.I,
)


def validate_local_dir(raw_path):
    """Validate and resolve a user-chosen local media root folder."""
    text = str(raw_path or '').strip()
    if not text:
        raise ValueError('Klasör yolu boş olamaz.')
    path = Path(text).expanduser().resolve()
    if str(path) in BLOCKED_ROOTS or len(path.parts) <= 1:
        raise ValueError('Sistem kök dizinleri medya klasörü olarak seçilemez.')
    if not path.exists() or not path.is_dir():
        raise ValueError('Seçilen yerel klasör bulunamadı.')
    if not os.access(path, os.R_OK):
        raise ValueError('Seçilen klasörü okuma izni yok.')
    return path


def parse_media_filename(stem):
    """Extract clean display title, optional year, and optional (season, episode) from filename."""
    clean = stem.replace('.', ' ').replace('_', ' ').strip()
    ep_match = _EPISODE_RE.search(clean)
    season, episode = (int(ep_match.group(1)), int(ep_match.group(2))) if ep_match else (0, 0)
    year_match = _YEAR_RE.search(clean)
    year = year_match.group(1) if year_match else ''
    title = _NOISE_RE.sub('', clean)
    if ep_match:
        title = title[:ep_match.start()]
    elif year_match:
        title = title[:year_match.start()]
    title = re.sub(r'[\[\]()\-]+$', '', title).strip() or clean
    return title[:300], year, season, episode


def scan_local_folder(raw_dir, max_files=8000, max_depth=6):
    """Safely scan local folder respecting symlink containment inside root."""
    root = validate_local_dir(raw_dir)
    items = []
    categories = {}
    root_str = str(root)

    for dirpath, dirnames, filenames in os.walk(root_str, followlinks=False):
        rel = os.path.relpath(dirpath, root_str)
        depth = 0 if rel == '.' else len(Path(rel).parts)
        if depth >= max_depth:
            dirnames[:] = []
        # Skip hidden directories such as .git or .Trash.
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))

        dir_files = set(filenames)
        for fname in sorted(filenames):
            if fname.startswith('.'):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in VIDEO_EXTS:
                continue
            full = Path(dirpath) / fname
            try:
                resolved = full.resolve()
                if not resolved.is_relative_to(root) or not resolved.is_file():
                    continue
                stat = resolved.stat()
            except OSError:
                continue

            stem = os.path.splitext(fname)[0]
            subtitles = []
            for sub_candidate in sorted(dir_files):
                sub_ext = os.path.splitext(sub_candidate)[1].lower()
                if sub_ext in SUBTITLE_EXTS and sub_candidate.startswith(stem):
                    sub_path = (Path(dirpath) / sub_candidate).resolve()
                    if sub_path.is_relative_to(root) and sub_path.is_file():
                        subtitles.append(str(sub_path))

            title, year, season, episode = parse_media_filename(stem)
            folder_name = root.name if rel == '.' else Path(rel).parts[0]
            cat_id = 'loc_' + hashlib.sha1(folder_name.encode()).hexdigest()[:10]
            categories[cat_id] = folder_name[:120]
            digest = hashlib.sha1(str(resolved).encode()).hexdigest()[:18]
            items.append({
                'id': f'vod:loc_{digest}',
                'provider_id': f'loc_{digest}',
                'kind': 'vod',
                'name': f'{title} (S{season:02d}E{episode:02d})' if season and episode else title,
                'category_id': cat_id,
                'category_name': folder_name[:120],
                'year': year,
                'extension': ext.lstrip('.'),
                'added': stat.st_mtime,
                'localPath': str(resolved),
                'subtitles': subtitles[:6],
            })
            if len(items) >= max_files:
                return {'root': str(root), 'categories': categories, 'items': items}

    return {'root': str(root), 'categories': categories, 'items': items}
