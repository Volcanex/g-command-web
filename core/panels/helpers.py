import math
import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Europe/London")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def plain(value):
    text = "" if value is None else str(value)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}([-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"`+([^`]*)`+", r"\1", text)
    for pattern in (r"\*\*\*([\s\S]*?)\*\*\*", r"\*\*([\s\S]*?)\*\*", r"\*(?=\S)([\s\S]*?\S)\*"):
        text = re.sub(pattern, r"\1", text)
    for pattern in (r"(^|\W)___([\s\S]*?)___(?!\w)", r"(^|\W)__([\s\S]*?)__(?!\w)",
                    r"(^|\W)_(?=\S)([\s\S]*?\S)_(?!\w)"):
        text = re.sub(pattern, r"\1\2", text, flags=re.ASCII)
    text = re.sub(r"~~([\s\S]*?)~~", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"[*`]", "", text)).strip()


def rounded(value):
    return math.floor(float(value) + 0.5)


def fixed(value, digits):
    return format(Decimal.from_float(float(value)).quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP), f".{digits}f")


def parsed(value):
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc if len(str(value)) == 10 else TZ)
    return date.astimezone(TZ)


def day(value):
    date = parsed(value)
    return f"{WEEKDAYS[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"


def rel(value, now):
    if not value:
        return ""
    try:
        seconds = rounded(now.timestamp() - parsed(value).timestamp())
    except (ValueError, TypeError, OverflowError):
        return ""
    future = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        text = f"{seconds}s"
    elif seconds < 3600:
        text = f"{rounded(seconds / 60)}m"
    elif seconds < 86400:
        text = f"{rounded(seconds / 3600)}h"
    else:
        text = f"{rounded(seconds / 86400)}d"
    return "in " + text if future else text + " ago"


def london(value, with_day=False):
    date = parsed(value)
    clock = date.strftime("%H:%M")
    if with_day is True:
        return day(value) + ", " + clock
    if with_day:
        return WEEKDAYS[date.weekday()] + " " + clock
    return clock


def span(seconds):
    seconds = max(0, seconds)
    days = int(seconds // 86400)
    hours = int(seconds % 86400 // 3600)
    minutes = int(seconds % 3600 // 60)
    return f"{days}d {hours}h" if days else f"{hours}h {minutes:02d}m"


def sort_text(value):
    text = "undefined" if value is None else str(value)
    normal = unicodedata.normalize("NFD", text)
    base = "".join(c for c in normal if not unicodedata.combining(c))
    return base.casefold(), normal.casefold(), text.swapcase()


def chip(text, tone="plain", badge=False, icon=None, tip=None):
    result = {"text": plain(text), "tone": tone}
    if badge:
        result["badge"] = True
    if icon is not None:
        result["icon"] = icon
    if tip is not None:
        result["tip"] = plain(tip)
    return result


def note(item):
    return "/note/" + plain(item.get("permalink"))


def row_id(item):
    return str(item.get("slug") or item.get("permalink") or item.get("id") or item.get("title") or "")


def encoded(value):
    return quote(str(value), safe="~!*'()")
