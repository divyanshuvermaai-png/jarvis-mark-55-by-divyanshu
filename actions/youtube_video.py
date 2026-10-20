# youtube_video.py
import json
import re
import sys
import time
import subprocess
import shutil
import webbrowser
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

try:
    import requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    import yt_dlp
    _YTDLP_OK = True
except ImportError:
    _YTDLP_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

from config import get_os, is_windows, is_mac, is_linux


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Cookie": "CONSENT=YES+; SOCS=CAESEwgDEgk0ODE3Nzk3MjQaAmVuIAEaBgiA_LyaBg",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"

# ── Boss (Divyanshu Verma) YouTube Channel Constants ────────────────────────
BOSS_CHANNEL_HANDLE = "@divyanshu_sovereign_agent"
BOSS_CHANNEL_ID = "UCxJZuok742OL87BUplaJ3fw"
BOSS_CHANNEL_VARIANTS = (
    "divyanshu_sovereign_agent",
    "divyanshu_sovereing_agent",  # user/stt typo variant
    "divyanshu sovereign agent",
    "divyansh soren agent",
    "divyansh_soren_agent",
    "divyanshu sovereign",
    "divyanshu verma",
    "my channel",
    "boss channel",
    "boss's channel",
    "my youtube",
    "my video",
    "my recent video",
)

# Static cache of Boss's channel uploads for instant 0-second offline/cached resolution
BOSS_CACHED_VIDEOS = [
    ("T_MV_G3loUc", "I Built My Own JARVIS AI on MacBook 🤖⚡ | JARVIS Mark 55 (demo only)", "Divyanshu Verma"),
    ("dFqqrmdUR4Y", "JARVIS Mark 54 — Full Project Setup, Architecture & Demo", "Divyanshu Verma"),
    ("6_yGCF5GhQA", "I Built a NEW JARVIS AI 🤖 | My Personal AI Assistant — Part 2", "Divyanshu Verma"),
    ("5ovhib-WMS8", "I Built JARVIS AI for My Mac 🤖 | Full AI Assistant Demo #AI #JARVISAI", "Divyanshu Verma"),
    ("3vCqmvZ0D-0", "These 5 AI Tools Can Replace Human Work in Minutes! 🤯", "Divyanshu Verma"),
    ("uUxH_US9-uU", "How to Build an Autonomous AI Agent in Python", "Divyanshu Verma"),
]


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _open_url(url: str) -> bool:
    """Opens a URL in the user's default web browser with OS-level fallbacks."""
    try:
        if webbrowser.open(url):
            return True
    except Exception:
        pass

    try:
        if is_mac():
            subprocess.Popen(["open", url])
            return True
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
            return True
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
            return True
    except Exception as e:
        print(f"[YouTube] ⚠️ open_url failed: {e}")
        return False


def _extract_video_id(url: str) -> str | None:
    """Extracts an 11-character YouTube video ID from standard URLs or raw strings."""
    if not url:
        return None
    raw = url.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):
        return raw
    match = re.search(
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/|\/live\/)([A-Za-z0-9_-]{11})",
        raw,
    )
    return match.group(1) if match else None


def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))


def _is_boss_channel_query(text: str) -> bool:
    """Checks whether the query refers to Boss (Divyanshu Verma)'s YouTube channel or videos."""
    low = (text or "").lower()
    return any(v in low for v in BOSS_CHANNEL_VARIANTS)


def _fetch_channel_videos(handle_or_id: str, max_videos: int = 10) -> list[tuple[str, str, str]]:
    """
    Fetches videos from a YouTube channel in reverse-chronological order (most recent first).
    Returns list of (video_id, title, channel_name).
    """
    target = handle_or_id.strip()
    if not target.startswith("@") and not target.startswith("UC") and not target.startswith("/@"):
        target = "@" + target
    if target.startswith("/"):
        target = target[1:]

    videos: list[tuple[str, str, str]] = []

    # 1. Fast HTML browse via requests
    if _REQUESTS_OK:
        try:
            url = f"https://www.youtube.com/{target}/videos"
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code == 200:
                m = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", r.text)
                if not m:
                    m = re.search(r"ytInitialData\s*=\s*({.+?});", r.text)
                if m:
                    data = json.loads(m.group(1))

                    def _extract(obj):
                        res = []
                        if isinstance(obj, dict):
                            if "lockupViewModel" in obj:
                                lk = obj["lockupViewModel"]
                                cid = lk.get("contentId")
                                if cid and len(cid) == 11:
                                    t = lk.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title", {}).get("content", "")
                                    res.append((cid, t, target))
                            if "videoRenderer" in obj:
                                vr = obj["videoRenderer"]
                                vid = vr.get("videoId")
                                if vid and len(vid) == 11:
                                    t = vr.get("title", {}).get("runs", [{}])[0].get("text", "") or vr.get("title", {}).get("simpleText", "")
                                    chan = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "") or target
                                    res.append((vid, t, chan))
                            for v in obj.values():
                                res.extend(_extract(v))
                        elif isinstance(obj, list):
                            for item in obj:
                                res.extend(_extract(item))
                        return res

                    found = _extract(data)
                    for vid, t, c in found:
                        if not any(v[0] == vid for v in videos):
                            videos.append((vid, t, c))
                        if len(videos) >= max_videos:
                            break
        except Exception as e:
            print(f"[YouTube] ⚠️ Channel HTML fetch failed for {target}: {e}")

    # 2. yt-dlp fallback if HTML failed
    if not videos and _YTDLP_OK:
        try:
            opts = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": False,
                "playlist_items": f"1-{max_videos}",
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                res = ydl.extract_info(f"https://www.youtube.com/{target}/videos", download=False)
                for e in (res or {}).get("entries", []):
                    vid = e.get("id")
                    if vid and len(vid) == 11:
                        videos.append((vid, e.get("title") or "", e.get("uploader") or target))
        except Exception as e:
            print(f"[YouTube] ⚠️ yt-dlp channel fetch failed for {target}: {e}")

    return videos


def _fetch_channel_latest(handle_or_id: str) -> tuple[str, str, str] | None:
    """Resolves the latest video of a specific channel."""
    vids = _fetch_channel_videos(handle_or_id, max_videos=3)
    if vids:
        vid, title, channel = vids[0]
        return f"https://www.youtube.com/watch?v={vid}", title, channel
    return None


def _resolve_boss_video(query: str) -> tuple[str, str, str]:
    """
    Intelligently resolves videos from Boss (Divyanshu Verma)'s YouTube channel.
    - If user asks for recent/latest video, returns his newest video.
    - If user mentions specific project/video keywords (e.g. 'Mark 55', 'Mark 54', 'demo'),
      finds the exact matching video on his channel.
    """
    videos = _fetch_channel_videos(BOSS_CHANNEL_HANDLE, max_videos=10)
    if not videos:
        videos = list(BOSS_CACHED_VIDEOS)

    # Clean query tokens to match specific video
    cleaned = (query or "").lower()
    for b in list(BOSS_CHANNEL_VARIANTS) + [
        "recent", "latest", "video", "play", "watch", "new", "upload",
        "the", "of", "from", "by", "channel", "jarvis", "youtube"
    ]:
        cleaned = re.sub(r"\b" + re.escape(b) + r"\b", " ", cleaned)

    tokens = [w for w in re.findall(r"\w+", cleaned) if len(w) > 1]

    # If no specific video title keywords were given, default to the latest video
    if not tokens:
        top = videos[0]
        return f"https://www.youtube.com/watch?v={top[0]}", top[1], top[2]

    scored = []
    for vid, title, chan in videos:
        title_low = title.lower()
        score = sum(1 for tok in tokens if tok in title_low)
        scored.append((score, vid, title, chan))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    if best[0] > 0:
        return f"https://www.youtube.com/watch?v={best[1]}", best[2], best[3]

    # Default to latest if no tokens matched
    top = videos[0]
    return f"https://www.youtube.com/watch?v={top[0]}", top[1], top[2]


def clean_youtube_query(query: str) -> str:
    """
    Strips conversational noise, polite filler, platform labels, and action keywords
    from user prompts so YouTube's search engine receives clean, accurate intent.
    Handles emotional / mood phrases, Hinglish phrases, channel references, and typos.
    E.g.:
      'play shape of you on youtube' -> 'shape of you'
      'my mood is sad so play song to heal' -> 'songs to heal sad mood'
      'play song to heal' -> 'songs to heal sad mood'
      'play the recent video of divyanshu_sovereing_agent' -> '@divyanshu_sovereign_agent'
      'youtube pe tauba tauba chalao' -> 'tauba tauba'
    """
    raw = (query or "").strip()
    if not raw:
        return ""

    if _is_valid_youtube_url(raw) or _extract_video_id(raw):
        return raw

    # Normalize quotes, backticks, emojis
    cleaned = re.sub(r'[\'\"“”‘’`]', "", raw).strip()

    # Conversational narrative phrases
    cleaned = re.sub(r"^(?:like\s+)?(?:i\s+said\s+)?", "", cleaned, flags=re.I).strip()

    # Mood & Emotion expressions (e.g. "my mood is sad so play song to heal")
    mood_match = re.search(
        r"(?:my\s+mood\s+is\s+|i\s+am\s+(?:feeling\s+)?|feeling\s+)"
        r"(sad|depressed|gloomy|heartbroken|low|down|stressed|tired|exhausted|angry|upset|happy|chill|relaxed|romantic)\s*"
        r"(?:,\s*|\s+so\s+|\s+)?(?:please\s+)?(?:can\s+you\s+)?(?:play|listen\s+to|stream|put\s+on)?\s*(.*)",
        cleaned,
        flags=re.I,
    )
    if mood_match:
        mood = mood_match.group(1).lower()
        sub = mood_match.group(2).strip()
        if not sub or sub.lower() in ("a song", "songs", "music", "something", "gana", "koi gana"):
            if mood in ("sad", "depressed", "gloomy", "heartbroken", "low", "down"):
                return "songs to heal sad mood"
            elif mood in ("stressed", "tired", "exhausted", "angry", "upset"):
                return "calm relaxing stress relief music"
            elif mood in ("happy",):
                return "happy uplifting hit songs"
            elif mood in ("chill", "relaxed"):
                return "chill relaxing lofi beats"
            elif mood in ("romantic",):
                return "best romantic love songs"
        else:
            sub_cleaned = re.sub(r"^(?:a\s+|some\s+)", "", sub, flags=re.I).strip()
            if "heal" in sub_cleaned.lower():
                return f"songs to heal {mood} mood"
            return f"{sub_cleaned} for {mood} mood"

    # Specific healing song phrasing
    if re.search(r"\b(?:song|songs|music)\s+to\s+heal\b", cleaned, re.I):
        return "songs to heal sad mood"

    # Conversational prefixes
    prefix_pattern = (
        r"^(?:(?:can|could|will|would)\s+you\s+)?"
        r"(?:please\s+)?"
        r"(?:i\s+(?:want|would\s+like)\s+(?:to\s+)?)?"
        r"(?:just\s+)?"
        r"(?:play|watch|stream|listen\s+to|open|put\s+on|search\s+for|find\s+me|find|search|show)\s+"
    )
    cleaned = re.sub(prefix_pattern, "", cleaned, flags=re.I).strip()

    # Multilingual / Hinglish prefixes & suffixes
    cleaned = re.sub(r"^(?:youtube\s+(?:pe|par|me|mein)\s+)", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s+(?:chalao|chala\s+do|bajao|baja\s+do|lagao|laga\s+do|sunao|suna\s+do)$", "", cleaned, flags=re.I).strip()

    # Strip YouTube platform suffixes / prefixes
    suffix_pattern = (
        r"\s+(?:on|in|from|at)\s+(?:youtube|yt)$|"
        r"^(?:youtube|yt)\s+(?:video\s+)?|"
        r"\s+(?:on\s+)?(?:youtube|yt)$"
    )
    cleaned = re.sub(suffix_pattern, "", cleaned, flags=re.I).strip()

    # Strip conversational channel prefixes like "the recent video of", "latest video of"
    chan_prefix = re.match(
        r"^(?:the\s+)?(?:recent|latest|newest|last|new)\s+(?:video|upload|clip)\s+(?:of|from|by)\s+(.+)$",
        cleaned,
        flags=re.I,
    )
    if chan_prefix:
        cleaned = chan_prefix.group(1).strip()

    # Strip redundant trailing words like 'full video', 'video song', 'video'
    cleaned = re.sub(r"\s+(?:full\s+)?video(?:\s+song)?$", "", cleaned, flags=re.I).strip()

    # Convert underscores in channel / creator names (e.g. divyanshu_sovereign_agent -> divyanshu sovereign agent)
    # but preserve @ if present
    if "_" in cleaned and not cleaned.startswith("http"):
        cleaned = re.sub(r"(\w)_(\w)", r"\1 \2", cleaned).strip()

    # Generic search queries: avoid playing an obscure video literally titled 'A Song'
    generic_music_terms = {
        "a song", "song", "songs", "some song", "some songs",
        "music", "some music", "something", "anything", "random song",
        "random music", "something to listen to", "gana", "koi gana",
        "video", "videos", "a video", "some video"
    }
    if cleaned.lower() in generic_music_terms:
        return "top popular music hits"

    return cleaned or raw


def _search_innertube(query: str) -> tuple[str, str, str] | None:
    """
    Tier 1 Resolver: Queries YouTube's InnerTube API (used by YouTube's web and mobile apps).
    Direct JSON response with token-relevance scoring, channel discovery, and news filtering.
    Returns (video_url, title, channel) or None.
    """
    if not _REQUESTS_OK:
        return None

    try:
        url = "https://www.youtube.com/youtubei/v1/search"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": HEADERS["User-Agent"],
        }
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240401.01.00",
                    "hl": "en",
                }
            },
            "query": query,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=8)
        if r.status_code != 200:
            return None

        data = r.json()
        sections = (
            data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
        )

        candidates = []
        did_you_mean = None
        matched_channel = None

        # Stop words and tokens for relevance scoring
        stop_words = {
            "a", "an", "the", "on", "in", "at", "of", "for", "to", "and", "by",
            "is", "it", "so", "with", "from", "video", "song", "songs", "music",
            "recent", "latest", "new"
        }
        q_tokens = {w.lower() for w in re.findall(r"\w+", query) if len(w) > 1 and w.lower() not in stop_words}
        is_news_query = any(w in query.lower() for w in ("news", "breaking", "court", "arrest", "police", "crime", "election"))
        news_keywords = ("breaking news", "live news", "court case", "custody", "delhi police", "police case", "cjp", "arrested", "protest")

        for sec in sections:
            for item in sec.get("itemSectionRenderer", {}).get("contents", []):
                # 1. Did you mean?
                if "didYouMeanRenderer" in item:
                    dym = item["didYouMeanRenderer"]
                    endpoint = dym.get("correctedQueryEndpoint", {}).get("searchEndpoint", {})
                    if endpoint.get("query"):
                        did_you_mean = endpoint["query"]

                # 2. Channel result
                if "channelRenderer" in item:
                    cr = item["channelRenderer"]
                    cid = cr.get("channelId")
                    c_title = cr.get("title", {}).get("simpleText", "")
                    c_handle = cr.get("subscriberCountText", {}).get("simpleText", "")
                    nav_url = cr.get("navigationEndpoint", {}).get("browseEndpoint", {}).get("canonicalBaseUrl", "")
                    c_text = f"{c_title} {c_handle} {nav_url}".lower()
                    if any(t in c_text for t in q_tokens):
                        target = nav_url if nav_url.startswith("/@") else (c_handle if c_handle.startswith("@") else cid)
                        if target and not matched_channel:
                            matched_channel = target

                # 3. Traditional videoRenderer
                if "videoRenderer" in item:
                    vr = item["videoRenderer"]
                    vid = vr.get("videoId")
                    if vid and len(vid) == 11:
                        title = ""
                        runs = vr.get("title", {}).get("runs", [])
                        if runs:
                            title = runs[0].get("text", "")
                        elif "simpleText" in vr.get("title", {}):
                            title = vr["title"]["simpleText"]

                        channel = ""
                        owner_runs = vr.get("ownerText", {}).get("runs", [])
                        if owner_runs:
                            channel = owner_runs[0].get("text", "")
                        elif "shortBylineText" in vr:
                            byline_runs = vr["shortBylineText"].get("runs", [])
                            if byline_runs:
                                channel = byline_runs[0].get("text", "")

                        text_tokens = {w.lower() for w in re.findall(r"\w+", f"{title} {channel}")}
                        overlap = len(q_tokens & text_tokens)
                        penalty = 100 if not is_news_query and any(nk in title.lower() for nk in news_keywords) else 0
                        candidates.append((overlap - penalty, vid, title or query, channel))

                # 4. Modern lockupViewModel
                if "lockupViewModel" in item:
                    lk = item["lockupViewModel"]
                    vid = lk.get("contentId")
                    if vid and len(vid) == 11:
                        meta = lk.get("metadata", {}).get("lockupMetadataViewModel", {})
                        title = meta.get("title", {}).get("content", "")
                        channel = ""
                        for row in meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", []):
                            for part in row.get("parts", []):
                                t = part.get("text", {}).get("content", "")
                                if t and not re.search(r"views|\d+\s+(?:days|months|hours|years)\s+ago", t, re.I):
                                    channel = t
                                    break
                        text_tokens = {w.lower() for w in re.findall(r"\w+", f"{title} {channel}")}
                        overlap = len(q_tokens & text_tokens)
                        penalty = 100 if not is_news_query and any(nk in title.lower() for nk in news_keywords) else 0
                        candidates.append((overlap - penalty, vid, title or query, channel))

        # If a channel strongly matched the query and user asked for channel/creator, resolve channel's video
        if matched_channel:
            chan_res = _fetch_channel_latest(matched_channel)
            if chan_res:
                return chan_res

        # If candidates exist, sort by score descending
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best = candidates[0]
            # If best candidate is penalized or 0 overlap when did_you_mean is available, retry
            if best[0] <= 0 and did_you_mean and did_you_mean != query:
                retry_res = _search_innertube(did_you_mean)
                if retry_res:
                    return retry_res
            if best[0] > -50:  # Avoid completely disqualified news videos
                return f"https://www.youtube.com/watch?v={best[1]}", best[2], best[3]

    except Exception as e:
        print(f"[YouTube] ⚠️ InnerTube search failed: {e}")

    return None


def _search_ytdlp(query: str) -> tuple[str, str, str] | None:
    """
    Tier 2 Resolver: Uses yt-dlp flat search with multi-result inspection & news filtering.
    Returns (video_url, title, channel) or None.
    """
    if not _YTDLP_OK:
        return None

    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "playlist_items": "1-5",
            "extract_flat": True,
        }
        stop_words = {"a", "an", "the", "on", "in", "at", "of", "for", "to", "and", "by", "is", "so", "video", "song"}
        q_tokens = {w.lower() for w in re.findall(r"\w+", query) if len(w) > 1 and w.lower() not in stop_words}
        is_news_query = any(w in query.lower() for w in ("news", "breaking", "court", "arrest", "police"))
        news_keywords = ("breaking news", "live news", "delhi police", "court case", "custody", "arrested")

        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = (res or {}).get("entries", [])
            if entries:
                candidates = []
                for e in entries:
                    vid = e.get("id")
                    if vid and len(vid) == 11:
                        title = e.get("title") or query
                        channel = e.get("uploader") or e.get("channel") or ""
                        text_tokens = {w.lower() for w in re.findall(r"\w+", f"{title} {channel}")}
                        overlap = len(q_tokens & text_tokens)
                        penalty = 100 if not is_news_query and any(nk in title.lower() for nk in news_keywords) else 0
                        candidates.append((overlap - penalty, vid, title, channel))

                if candidates:
                    candidates.sort(key=lambda x: x[0], reverse=True)
                    best = candidates[0]
                    if best[0] > -50:
                        return f"https://www.youtube.com/watch?v={best[1]}", best[2], best[3]
    except Exception as e:
        print(f"[YouTube] ⚠️ yt-dlp search failed: {e}")

    return None


def _search_ytinitialdata(query: str) -> tuple[str, str, str] | None:
    """
    Tier 3 Resolver: Parses ytInitialData from YouTube's desktop HTML with relevance scoring.
    """
    if not _REQUESTS_OK:
        return None

    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )

    try:
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text

        m = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", html)
        if not m:
            m = re.search(r"ytInitialData\s*=\s*({.+?});", html)

        if m:
            data = json.loads(m.group(1))
            sections = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for sec in sections:
                for item in sec.get("itemSectionRenderer", {}).get("contents", []):
                    if "videoRenderer" in item:
                        vr = item["videoRenderer"]
                        vid = vr.get("videoId")
                        if vid and len(vid) == 11:
                            title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                            channel = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                            return f"https://www.youtube.com/watch?v={vid}", title or query, channel

    except Exception as e:
        print(f"[YouTube] ⚠️ ytInitialData search failed: {e}")

    return None


def _resolve_youtube_video(query_or_url: str) -> tuple[str, str, str]:
    """
    Main resolver. Accepts a URL, video ID, or search phrase.
    Returns (video_url, title, channel).
    """
    raw = (query_or_url or "").strip()

    # Case 1: Direct Video ID or URL provided
    vid = _extract_video_id(raw)
    if vid:
        url = f"https://www.youtube.com/watch?v={vid}"
        # Fetch metadata quickly via oEmbed if available
        title = raw
        channel = ""
        info = _get_video_info(vid)
        if info:
            title = info.get("title") or title
            channel = info.get("channel") or channel
            return url, title, channel
        # If oEmbed failed, verify it exists before returning
        if _is_valid_youtube_url(raw):
            return url, title, channel

    # Case 2: Boss (Divyanshu Verma)'s channel check
    if _is_boss_channel_query(raw):
        print(f"[YouTube] 👑 Boss channel matched: '{raw}' -> resolving from {BOSS_CHANNEL_HANDLE}")
        return _resolve_boss_video(raw)

    # Case 3: Explicit channel handle provided (e.g. "@mkbhd")
    if raw.startswith("@") or re.match(r"^@[\w.-]+$", raw):
        chan_res = _fetch_channel_latest(raw)
        if chan_res:
            return chan_res

    # Case 4: Clean the search query
    cleaned = clean_youtube_query(raw)
    if not cleaned:
        return "https://www.youtube.com", "YouTube", "YouTube"

    # Re-check Boss channel on cleaned query
    if _is_boss_channel_query(cleaned):
        print(f"[YouTube] 👑 Boss channel matched (cleaned): '{cleaned}' -> resolving from {BOSS_CHANNEL_HANDLE}")
        return _resolve_boss_video(cleaned)

    print(f"[YouTube] 🔍 Searching YouTube for: '{cleaned}' (raw: '{raw}')")

    # Tier 1: InnerTube API (Fastest & most relevant, with token scoring)
    res = _search_innertube(cleaned)
    if res:
        return res

    # Tier 2: yt-dlp flat search (multi-result inspection)
    res = _search_ytdlp(cleaned)
    if res:
        return res

    # Tier 3: ytInitialData HTML search
    res = _search_ytinitialdata(cleaned)
    if res:
        return res

    # Fallback: Filtered search page URL
    fallback_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(cleaned)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    return fallback_url, f"Search results for: {cleaned}", ""


def _get_video_info(video_id: str) -> dict:
    """Retrieves title, channel, duration, and view count for a YouTube video."""
    info = {}

    # 1. Fast official oEmbed lookup for title & channel name
    if _REQUESTS_OK:
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
            r = requests.get(oembed_url, timeout=5)
            if r.status_code == 200:
                d = r.json()
                info["title"] = d.get("title")
                info["channel"] = d.get("author_name")
        except Exception:
            pass

    # 2. yt-dlp for view count, duration, and likes
    if _YTDLP_OK:
        try:
            opts = {"quiet": True, "skip_download": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                y = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if y:
                    if not info.get("title"):
                        info["title"] = y.get("title")
                    if not info.get("channel"):
                        info["channel"] = y.get("uploader") or y.get("channel")
                    views = y.get("view_count")
                    if views:
                        info["views"] = f"{int(views):,}"
                    dur = y.get("duration")
                    if dur:
                        info["duration"] = f"{int(dur) // 60}:{int(dur) % 60:02d}"
                    likes = y.get("like_count")
                    if likes:
                        info["likes"] = f"{int(likes):,}"
        except Exception:
            pass

    return info


def _ask_for_url(prompt_text: str = "YouTube video URL:") -> str | None:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring("J.A.R.V.I.S", prompt_text, parent=root)
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL dialog failed: {e}")
        return None


def _get_transcript(video_id: str) -> str | None:
    if not _TRANSCRIPT_OK:
        return None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None

        lang_priority = ["en", "hi", "tr", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]

        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass

        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript is None:
            return None

        fetched = transcript.fetch()
        return " ".join(entry["text"] for entry in fetched)

    except Exception as e:
        print(f"[YouTube] ⚠️ Transcript fetch failed: {e}")
        return None


def _summarize_with_gemini(transcript: str, video_url: str) -> str:
    from google.genai import types
    from core import gemini

    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    response = gemini.call(
        f"Please summarize this YouTube video transcript:\n\n{truncated}",
        tier=gemini.SMART,
        timeout_ms=60_000,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are JARVIS, an AI assistant. "
                "Summarize YouTube video transcripts clearly and concisely. "
                "Structure: 1-sentence overview, then 3-5 key points. "
                "Be direct. Address the user as 'sir'. "
                "Match the language of the transcript."
            )
        ),
    )
    if response is None:
        return "I couldn't reach Gemini to summarise that transcript, sir."
    return (response.text or "").strip()


def _save_summary(content: str, video_url: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"youtube_summary_{ts}.txt"
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename

    header = (
        f"JARVIS — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    filepath.write_text(header + content, encoding="utf-8")

    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] ⚠️ Could not open text editor: {e}")

    return str(filepath)


def _scrape_trending(region: str = "US", max_results: int = 8) -> list[dict]:
    """Fetches currently trending videos using YouTube's search endpoint."""
    query = f"trending {region}" if region else "trending videos"
    results = []

    # Try InnerTube search
    if _REQUESTS_OK:
        try:
            url = "https://www.youtube.com/youtubei/v1/search"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": HEADERS["User-Agent"],
            }
            payload = {
                "context": {
                    "client": {
                        "clientName": "WEB",
                        "clientVersion": "2.20240401.01.00",
                        "hl": "en",
                        "gl": region.upper() if region else "US",
                    }
                },
                "query": query,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=8)
            if r.status_code == 200:
                data = r.json()
                sections = (
                    data.get("contents", {})
                    .get("twoColumnSearchResultsRenderer", {})
                    .get("primaryContents", {})
                    .get("sectionListRenderer", {})
                    .get("contents", [])
                )
                seen_ids = set()
                for sec in sections:
                    for item in sec.get("itemSectionRenderer", {}).get("contents", []):
                        if "videoRenderer" in item:
                            vr = item["videoRenderer"]
                            vid = vr.get("videoId")
                            if vid and vid not in seen_ids:
                                seen_ids.add(vid)
                                title = vr.get("title", {}).get("runs", [{}])[0].get("text", "")
                                channel = vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "")
                                results.append({
                                    "rank": len(results) + 1,
                                    "title": title,
                                    "channel": channel or "Unknown",
                                    "url": f"https://www.youtube.com/watch?v={vid}",
                                })
                                if len(results) >= max_results:
                                    return results
        except Exception as e:
            print(f"[YouTube] ⚠️ InnerTube trending failed: {e}")

    return results


def _handle_play(parameters: dict, player) -> str:
    # Check parameters flexibly
    query = (
        parameters.get("query")
        or parameters.get("url")
        or parameters.get("video")
        or parameters.get("title")
        or parameters.get("search")
        or ""
    ).strip()

    # If user explicitly asked to "open youtube" without a specific query
    if not query or query.lower() in ("youtube", "open youtube", "open yt"):
        print("[YouTube] ▶️ Opening YouTube homepage")
        if player and hasattr(player, "write_log"):
            player.write_log("[YouTube] Opening YouTube homepage")
        _open_url("https://www.youtube.com")
        return "Opened YouTube in your browser, sir."

    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Searching: {query}")

    # Resolve exact video
    video_url, title, channel = _resolve_youtube_video(query)

    print(f"[YouTube] ▶️ Opening: '{title}' ({video_url}) by {channel or 'Unknown'}")
    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Playing: {title}")

    _open_url(video_url)

    if channel:
        return f"Playing '{title}' by {channel} on YouTube, sir."
    return f"Playing '{title}' on YouTube, sir."


def _handle_summarize(parameters: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"

    url = (parameters.get("url") or parameters.get("query") or "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url:
        return "No URL provided, sir. Summary cancelled."
    if not _is_valid_youtube_url(url) and not _extract_video_id(url):
        return "That doesn't appear to be a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID from that URL, sir."

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Summarizing: {canonical_url}")
    if speak:
        speak("Fetching the transcript now, sir. One moment.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return "I couldn't retrieve a transcript for that video, sir. It may not have subtitles or captions enabled."

    if speak:
        speak("Transcript retrieved. Generating summary now.")

    try:
        summary = _summarize_with_gemini(transcript, canonical_url)
    except Exception as e:
        return f"Summary generation failed, sir: {e}"

    if speak:
        speak(summary)

    if parameters.get("save", False):
        saved_path = _save_summary(summary, canonical_url)
        return f"Summary complete and saved to Desktop: {saved_path}"

    return summary


def _handle_get_info(parameters: dict, player, speak) -> str:
    url = (parameters.get("url") or parameters.get("query") or "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url:
        return "Please provide a valid YouTube URL, sir."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID, sir."

    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Getting info: {url}")

    info = _get_video_info(video_id)
    if not info:
        return "Could not retrieve video information, sir."

    lines = [
        f"{key.capitalize()}: {info[key]}"
        for key in ("title", "channel", "views", "duration", "likes")
        if key in info and info[key]
    ]
    result = "\n".join(lines)

    if speak:
        title_txt = info.get("title", "this video")
        speak(f"Here is the video info for {title_txt}, sir.")

    return result or "No detailed info could be retrieved for this video."


def _handle_trending(parameters: dict, player, speak) -> str:
    region = (parameters.get("region") or "US").upper()

    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Trending: {region}")

    trending = _scrape_trending(region=region, max_results=8)
    if not trending:
        return f"Could not fetch trending videos for region {region}, sir."

    lines = [f"Top trending videos ({region}):"]
    lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
    result = "\n".join(lines)

    if speak:
        top3 = trending[:3]
        spoken = "Here are the top trending videos, sir. " + ". ".join(
            f"Number {v['rank']}: {v['title']} by {v['channel']}" for v in top3
        )
        speak(spoken)

    return result


_ACTION_MAP = {
    # Play / Watch aliases
    "play": _handle_play,
    "open": _handle_play,
    "watch": _handle_play,
    "search": _handle_play,
    "stream": _handle_play,
    "start": _handle_play,
    "listen": _handle_play,
    # Summary aliases
    "summarize": _handle_summarize,
    "summary": _handle_summarize,
    "transcript": _handle_summarize,
    "transcribe": _handle_summarize,
    # Info aliases
    "get_info": _handle_get_info,
    "info": _handle_get_info,
    "details": _handle_get_info,
    "metadata": _handle_get_info,
    # Trending aliases
    "trending": _handle_trending,
    "trends": _handle_trending,
    "popular": _handle_trending,
}


def youtube_video(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player and hasattr(player, "write_log"):
        player.write_log(f"[YouTube] Action: {action}")
    print(f"[YouTube] ▶️  Action: {action}  Params: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        handler = _handle_play

    try:
        if handler == _handle_play:
            return handler(params, player) or "Done."
        return handler(params, player, speak) or "Done."
    except Exception as e:
        print(f"[YouTube] ❌ Error in {action}: {e}")
        return f"YouTube {action} failed, sir: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "youtube_video",
    "description": (
        "Controls YouTube and plays YouTube videos, music, songs, channel uploads, and playlists in the web browser with audio. "
        "Use for ALL requests to play music, play songs, or watch YouTube videos: "
        "'play the recent video of divyanshu_sovereign_agent', 'my mood is sad so play song to heal', "
        "'play shape of you', 'play chill beats', 'youtube pe gaana chalao', 'play some music', 'open youtube', "
        "or summarize a video, get info, or check trending videos. "
        "CRITICAL: Always pass the search query, song name, or channel name as PLAIN TEXT in query. "
        "NEVER hallucinate, invent, or guess a YouTube URL."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "play | open | summarize | get_info | trending (default: play)",
                "enum": ["play", "open", "watch", "summarize", "get_info", "trending"],
            },
            "query": {
                "type": "STRING",
                "description": (
                    "The video title, song title, creator channel (e.g. 'divyanshu_sovereign_agent', 'mkbhd'), "
                    "or search keywords to play. Pass plain text. NEVER invent a fake youtube.com URL."
                ),
            },
            "save": {
                "type": "BOOLEAN",
                "description": "Save summary to text file on Desktop (summarize only).",
            },
            "region": {
                "type": "STRING",
                "description": "Country code for trending e.g. US, IN, GB (default: US).",
            },
        },
        "required": [],
    },
    "handler": youtube_video,
}

