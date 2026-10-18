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


def clean_youtube_query(query: str) -> str:
    """
    Strips conversational noise, polite filler, platform labels, and action keywords
    from user prompts so YouTube's search engine receives clean, accurate intent.
    E.g.:
      'play shape of you on youtube' -> 'shape of you'
      'can you please play despacito' -> 'despacito'
      'play some chill lofi beats on yt' -> 'chill lofi beats'
      'youtube pe tauba tauba chalao' -> 'tauba tauba'
      'play a song' -> 'top global hit music'
    """
    raw = (query or "").strip()
    if not raw:
        return ""

    if _is_valid_youtube_url(raw) or _extract_video_id(raw):
        return raw

    # Normalize quotes & backticks
    cleaned = re.sub(r'[\'\"“”‘’`]', "", raw).strip()

    # Strip conversational prefixes
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

    # Strip redundant trailing words like 'full video', 'video song', 'video'
    cleaned = re.sub(r"\s+(?:full\s+)?video(?:\s+song)?$", "", cleaned, flags=re.I).strip()

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
    Direct JSON response bypassing HTML scraping, advertisements, and irrelevant shelves.
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

        for sec in sections:
            for item in sec.get("itemSectionRenderer", {}).get("contents", []):
                # Ensure we only pick genuine video results (skip adSlotRenderer, shelfRenderer, etc.)
                if "videoRenderer" in item:
                    vr = item["videoRenderer"]
                    vid = vr.get("videoId")
                    if vid and len(vid) == 11:
                        # Extract title
                        title = ""
                        runs = vr.get("title", {}).get("runs", [])
                        if runs:
                            title = runs[0].get("text", "")
                        elif "simpleText" in vr.get("title", {}):
                            title = vr["title"]["simpleText"]

                        # Extract channel
                        channel = ""
                        owner_runs = vr.get("ownerText", {}).get("runs", [])
                        if owner_runs:
                            channel = owner_runs[0].get("text", "")
                        elif "shortBylineText" in vr:
                            byline_runs = vr["shortBylineText"].get("runs", [])
                            if byline_runs:
                                channel = byline_runs[0].get("text", "")

                        video_url = f"https://www.youtube.com/watch?v={vid}"
                        return video_url, title or query, channel

    except Exception as e:
        print(f"[YouTube] ⚠️ InnerTube search failed: {e}")

    return None


def _search_ytdlp(query: str) -> tuple[str, str, str] | None:
    """
    Tier 2 Resolver: Uses yt-dlp flat search (fast metadata extraction without downloading).
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
            "playlist_items": "1",
            "extract_flat": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if res and res.get("entries"):
                e = res["entries"][0]
                vid = e.get("id")
                if vid and len(vid) == 11:
                    title = e.get("title") or query
                    channel = e.get("uploader") or e.get("channel") or ""
                    return f"https://www.youtube.com/watch?v={vid}", title, channel
    except Exception as e:
        print(f"[YouTube] ⚠️ yt-dlp search failed: {e}")

    return None


def _search_ytinitialdata(query: str) -> tuple[str, str, str] | None:
    """
    Tier 3 Resolver: Parses ytInitialData from YouTube's desktop HTML.
    Specifically parses the JSON structure instead of raw naive regex,
    avoiding adSlotRenderer and short previews.
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

    # Case 2: Clean the search query
    cleaned = clean_youtube_query(raw)
    if not cleaned:
        return "https://www.youtube.com", "YouTube", "YouTube"

    print(f"[YouTube] 🔍 Searching YouTube for: '{cleaned}' (raw: '{raw}')")

    # Tier 1: InnerTube API (Fastest & most relevant)
    res = _search_innertube(cleaned)
    if res:
        return res

    # Tier 2: yt-dlp flat search (Official InnerTube extractors)
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
        "Controls YouTube and plays YouTube videos or music in the web browser. "
        "Use whenever the user wants to play, watch, or listen to something on YouTube: "
        "'play shape of you on youtube', 'play some music', 'open youtube and play starboy', "
        "'youtube pe gaana chalao', 'open youtube', or wants to summarize a video transcript, "
        "get video info, or check trending videos."
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
                    "The video title, song title, artist, search keywords, or YouTube URL "
                    "to play/search for. Pass what the user requested."
                ),
            },
            "url": {
                "type": "STRING",
                "description": "Direct YouTube URL (optional, for play, summarize, or get_info).",
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
