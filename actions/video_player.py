"""
Play a video where the avatar normally is.

The HUD already had a surface for this — the live camera takes the centre of
the screen and gives it back — so a video is the same idea with a different
source, and it shares the same stack rather than inventing a second one. That
means the avatar, the camera and a video can never be on screen together.

WHAT IT ACCEPTS
    a local file        C:\\Users\\me\\clip.mp4, ~/Videos/holiday.mkv
    a direct media URL  https://example.com/trailer.mp4
    a YouTube link      https://youtube.com/watch?v=...
    a YouTube search    "play the new Dune trailer"

    The first two are handed straight to Qt. The last two have to be resolved
    to something playable first, which is what yt-dlp does; without it, this
    says so and offers to open the video in the browser instead of failing.

SOUND IS OFF UNTIL ASKED FOR
    A soundtrack talking over the assistant is the one way this feature could
    make JARVIS worse rather than better, and the microphone is open while it
    plays. So it starts muted, and the user turns sound on — from the button in
    the video header, or by saying so. Closing it works both ways too.
"""
from __future__ import annotations

import re
import threading
import webbrowser
from pathlib import Path

_YT = re.compile(r"(youtube\.com/|youtu\.be/)", re.I)

# Which open request is the current one. Opening happens on a thread now, so
# "stop" can arrive while a video is still being resolved — and without this the
# stop would find nothing playing, say so, and then the video would appear
# anyway a second later. Bumping the number abandons whatever is in flight.
_open_lock = threading.Lock()
_open_seq = 0


def _begin_open() -> int:
    global _open_seq
    with _open_lock:
        _open_seq += 1
        return _open_seq


def _still_wanted(token: int) -> bool:
    with _open_lock:
        return token == _open_seq


def _is_url(text: str) -> bool:
    return text.lower().startswith(("http://", "https://", "file://"))


def _local_path(text: str) -> str:
    """The text as an existing file on disk, or ''."""
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    try:
        p = Path(raw).expanduser()
        if p.exists() and p.is_file():
            return str(p)
    except Exception:
        pass
    return ""


def _resolve_youtube(url_or_query: str) -> tuple[str, str, str, str]:
    """(video_url, audio_url, title, error). Needs yt-dlp; says so when absent.

    TWO urls, because YouTube no longer offers one.
    The first version of this asked for a format carrying both picture and
    sound and got "Requested format is not available". That was not a bad
    selector, it was a wrong assumption: checked against three videos —
    including the oldest upload on the site — every one offered ZERO combined
    formats. Picture and sound are separate streams now, and both are returned
    so the player can run them together.

    `audio_url` comes back empty when only a combined or video-only stream
    exists, which is the normal case for everything that is not YouTube.
    """
    try:
        import yt_dlp
    except Exception:
        return "", "", "", ("yt-dlp is not installed, so a YouTube video "
                            "cannot be played inside the HUD. "
                            "Run: pip install yt-dlp")

    raw = (url_or_query or "").strip()

    try:
        from actions.youtube_video import clean_youtube_query, _extract_video_id, _resolve_youtube_video
        vid = _extract_video_id(raw)
        # If it is not a direct working video ID or URL, resolve it via our smart resolver first
        if not vid:
            resolved_url, r_title, r_chan = _resolve_youtube_video(raw)
            if resolved_url and "watch?v=" in resolved_url:
                raw = resolved_url
                vid = _extract_video_id(raw)
    except Exception:
        vid = None

    query = raw if _YT.search(raw) else (f"https://www.youtube.com/watch?v={vid}" if vid else f"ytsearch1:{raw}")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "playlist_items": "1",
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"],
            }
        },
    }
    info = None
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
    except Exception:
        # Fall back without player_client restrictions if SABR throttled
        try:
            fallback_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "playlist_items": "1",
            }
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception as e:
            return "", "", "", f"the video could not be resolved: {e}"

    if info and info.get("entries"):
        info = info["entries"][0]
    if not info:
        return "", "", "", "nothing was found for that."


    formats = [f for f in (info.get("formats") or [])
               if str(f.get("protocol") or "").startswith("http") and f.get("url")]

    def has(f, key):
        return f.get(key) not in (None, "none")

    def is_av1(f):
        vc = str(f.get("vcodec") or "").lower()
        return vc.startswith(("av01", "av1"))

    def is_h264(f):
        vc = str(f.get("vcodec") or "").lower()
        return (vc.startswith(("avc1", "avc", "h264", "h.264", "x264"))
                or "avc" in vc or "h264" in vc)

    def is_30fps(f):
        fps = f.get("fps")
        return fps is None or fps <= 30

    def best(candidates):
        """Highest quality — but the ORIGINAL language before quality.

        YouTube auto-dubs a lot of videos now, and it offers every dub as its
        own audio stream at the SAME bitrate as the original: measured on one
        video, English original at 129.483 and Arabic, Bangla, German, Spanish,
        French, Hindi and Indonesian all at 129.482. Choosing on bitrate alone
        therefore came down to a thousandth of a kilobit, and a video would play
        in Arabic one time and English the next for no reason the user could
        see.

        YouTube marks the original track with language_preference 10 and every
        dub with -1, so that decides it first and bitrate only breaks ties
        within the same track. Video formats carry no language, so this is the
        same ordering for them with the first term always equal.
        """
        if not candidates:
            return None
        return max(candidates,
                   key=lambda f: (f.get("language_preference") or 0,
                                  f.get("height") or 0,
                                  f.get("tbr") or 0))

    # Combined first — if a video still has one, one player is simpler and
    # cannot drift. Prefer H.264, and strictly avoid AV1 (which fails with
    # "Your platform doesn't support hardware accelerated AV1 decoding /
    # Failed to get pixel format" in QtMultimedia).
    combined = best([f for f in formats if has(f, "vcodec") and has(f, "acodec")
                     and is_h264(f)])
    if not combined:
        combined = best([f for f in formats if has(f, "vcodec") and has(f, "acodec")
                         and not is_av1(f)])
    if combined:
        return combined["url"], "", info.get("title") or "", ""

    # 720p is the ceiling on purpose: the HUD panel is nowhere near 4K, and a
    # smaller stream starts sooner and drifts less.
    # Prioritise H.264 (avc1) <= 30 FPS in MP4 container — 60 FPS causes
    # "Late SEI is not implemented" errors in Qt's FFmpeg and heavy buffering.
    video = best([f for f in formats
                  if has(f, "vcodec") and not has(f, "acodec")
                  and is_h264(f) and is_30fps(f) and f.get("ext") == "mp4" and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and is_h264(f) and is_30fps(f) and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and is_h264(f) and f.get("ext") == "mp4" and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and is_h264(f) and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and is_h264(f)])
    if not video:
        # Fallback: non-AV1 video (e.g. VP9 / WebM) up to 720p
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and not is_av1(f) and is_30fps(f) and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and not is_av1(f) and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")
                      and not is_av1(f)])
    if not video:
        # Final fallback if only AV1 was offered
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")])

    audio = best([f for f in formats
                  if has(f, "acodec") and not has(f, "vcodec")
                  and f.get("ext") == "m4a"])
    if not audio:
        audio = best([f for f in formats
                      if has(f, "acodec") and not has(f, "vcodec")])

    if not video:
        return "", "", "", "no playable stream was offered for that video."
    if video:
        print(f"[Video] video stream: {video.get('format_id')} "
              f"({video.get('vcodec')}, {video.get('resolution') or video.get('height')}, {video.get('ext')})")
    if audio and audio.get("language"):
        print(f"[Video] audio track: {audio.get('language')} "
              f"({audio.get('format_note') or audio.get('format_id')})")
    return video["url"], (audio or {}).get("url", ""), info.get("title") or "", ""


def _search_page(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def video_player(parameters: dict = None, response=None, player=None,
                 session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "play").strip().lower()
    source = (params.get("source") or "").strip()

    if player is None:
        return "There is no display to play a video on."

    # ---- stop -------------------------------------------------------------
    if action in ("stop", "close", "hide"):
        # Cancel an open that has not finished yet, so a video the user has
        # already changed their mind about never reaches the screen.
        was_opening = not player.video_is_playing()
        _begin_open()
        player.stop_video()
        if was_opening:
            return "Stopped it before it opened."
        return "Closed the video."

    # ---- sound ------------------------------------------------------------
    if action in ("mute", "unmute", "sound_on", "sound_off"):
        if not player.video_is_playing():
            return "Nothing is playing."
        muted = action in ("mute", "sound_off")
        player.set_video_muted(muted)
        return "Muted the video." if muted else "Turned the video's sound on."

    # ---- play -------------------------------------------------------------
    if not source:
        return "What should I play?"

    local = _local_path(source)
    if local:
        player.show_video(local, Path(local).name, muted=True)
        return f"Playing {Path(local).name} on the display, muted."

    # A direct media URL can go straight to the player; a YouTube page cannot.
    if _is_url(source) and not _YT.search(source):
        player.show_video(source, source.rsplit("/", 1)[-1][:44], muted=True)
        return "Playing that on the display, muted."

    # Check whether to start muted or unmuted
    explicit_unmute = params.get("muted") is False or params.get("unmute") is True or params.get("sound") is True
    is_music_or_song = any(
        w in source.lower()
        for w in ("song", "music", "gana", "gaana", "track", "audio", "sound", "heal", "listen")
    )
    start_muted = not (explicit_unmute or is_music_or_song)

    # ANSWER FIRST, OPEN SECOND.
    threading.Thread(target=_play_youtube, args=(player, source, _begin_open(), start_muted),
                     daemon=True, name="video-open").start()
    return f"status=opening source={source}"


def _play_youtube(player, source: str, token: int, muted: bool = True) -> None:
    """The part that takes seconds. Speaks only if something goes wrong —
    silence means the video is on screen, which the user can see for
    themselves."""
    try:
        url, audio_url, title, err = _resolve_youtube(source)
    except Exception as e:                                  # noqa: BLE001
        url = audio_url = title = ""
        err = str(e)

    if not _still_wanted(token):
        return                       # the user closed it while it was resolving

    if url:
        try:
            player.show_video(url, title or source, muted=muted,
                              audio_source=audio_url)
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)

    # Resolution failed.
    print(f"[VideoPlayer] ⚠️ Could not play '{source}' on display: {err}")
    # Do NOT open broken / unavailable URLs in the browser!
    # Only fall back to search page if it was a search topic or recoverable
    if _YT.search(source):
        _say(player, "That video could not be played because it is unavailable or the link was invalid.")
    else:
        page = _search_page(source)
        opened = ""
        try:
            webbrowser.open(page)
            opened = " and it has been opened in the browser instead"
        except Exception:
            pass
        _say(player, f"'{source}' could not be played on the display{opened}.")


def _say(player, instruction: str) -> None:
    if player is not None and hasattr(player, "request_say"):
        try:
            player.request_say(instruction)
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "video_player",
    "description": (
        "Plays a video directly inside the assistant's own UI display/HUD (in place of the avatar face on screen) "
        "and controls playback (stop, mute, unmute). "
        "Use ONLY when the user specifically wants to watch or preview a video directly ON THE DISPLAY / SCREEN / HUD: "
        "'put that video on the screen', 'show the Dune trailer on display', 'play local clip holiday.mp4'. "
        "CRITICAL: Pass the video title, search keywords, creator channel, or local path as PLAIN TEXT in source. "
        "NEVER invent, guess, or hallucinate a YouTube URL. "
        "NOTE: For general music listening, playing songs, or watching in the browser, use 'youtube_video' instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "'play' (default), 'stop' to close it, 'unmute' to turn the sound on, 'mute' to silence it.",
                "enum": ["play", "stop", "mute", "unmute"],
            },
            "source": {
                "type": "STRING",
                "description": (
                    "The video title, description, creator channel, or local file path to play on the display. "
                    "Pass plain text search terms. NEVER invent a fake youtube.com URL."
                ),
            },
            "muted": {
                "type": "BOOLEAN",
                "description": "True to start muted (default for general clips), False if user asked for music/song/sound.",
            },
        },
        "required": ["action"],
    },
    "handler": video_player,
}

