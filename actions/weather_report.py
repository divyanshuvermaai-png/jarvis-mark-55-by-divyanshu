import json
import urllib.request
import webbrowser
from urllib.parse import quote_plus


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    params = parameters or {}
    city = (params.get("city") or "Jaipur").strip()
    when = (params.get("when") or params.get("time") or "today").strip()

    if not city:
        city = "Jaipur"

    weather_text = _fetch_live_weather(city, when)
    if weather_text:
        _log(weather_text, player)
        if session_memory:
            try:
                session_memory.set_last_search(query=f"weather in {city}", response=weather_text)
            except Exception:
                pass
        return weather_text

    # Fallback to browser search if live API unreachable
    search_query = f"weather in {city} {when}"
    url = f"https://www.google.com/search?q={quote_plus(search_query)}"
    try:
        webbrowser.open(url)
        msg = f"Showing live weather for {city} on your screen, sir."
    except Exception as e:
        msg = f"Could not fetch weather for {city}: {e}"

    _log(msg, player)
    return msg


def _fetch_live_weather(city: str, when: str = "today") -> str | None:
    """Fetch live weather metrics from wttr.in without opening browser."""
    try:
        url = f"https://wttr.in/{quote_plus(city)}?format=j1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.88.1"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        curr = data.get("current_condition", [{}])[0]
        temp_c = curr.get("temp_C", "?")
        feels_c = curr.get("FeelsLikeC", temp_c)
        humidity = curr.get("humidity", "?")
        wind_kmph = curr.get("windspeedKmph", "?")
        descs = curr.get("weatherDesc", [{}])
        condition = descs[0].get("value", "Clear") if descs else "Clear"

        # Check if tomorrow was requested
        forecast_str = ""
        if "tomorrow" in when.lower():
            weather_days = data.get("weather", [])
            if len(weather_days) > 1:
                tmrw = weather_days[1]
                t_max = tmrw.get("maxtempC", "?")
                t_min = tmrw.get("mintempC", "?")
                hourly = tmrw.get("hourly", [{}])
                t_desc = hourly[len(hourly) // 2].get("weatherDesc", [{}])[0].get("value", "Clear")
                forecast_str = f" Tomorrow: {t_desc}, max {t_max}°C, min {t_min}°C."

        return (
            f"Currently in {city}: {condition}, {temp_c}°C (feels like {feels_c}°C), "
            f"humidity {humidity}%, wind {wind_kmph} km/h.{forecast_str}"
        )
    except Exception as e:
        print(f"[Weather] ⚠️ Live fetch failed for {city}: {e}")

    # Shorter fallback format
    try:
        url_text = f"https://wttr.in/{quote_plus(city)}?format=3"
        req = urllib.request.Request(url_text, headers={"User-Agent": "curl/7.88.1"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            raw = resp.read().decode("utf-8").strip()
            if raw:
                return f"Weather report: {raw}"
    except Exception:
        pass

    return None


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"JARVIS: {message}")
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "weather_report",
    "description": (
        "Fetches and speaks real-time weather reports (temperature, conditions, humidity, wind) for any city. "
        "If city is not specified by the user, defaults to Boss's location (Jaipur). "
        "Always call this tool for weather questions — NEVER guess or hallucinate the weather."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": "City name (e.g. 'Jaipur', 'Delhi', 'Mumbai', 'London', 'Bandikui'). Defaults to 'Jaipur' if omitted.",
            },
            "when": {
                "type": "STRING",
                "description": "'today' (default) or 'tomorrow'",
            },
        },
        "required": [],
    },
    "handler": weather_action,
}
