from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import unquote_plus, urlsplit, urlunsplit

MAX_TITLE_LENGTH = 500
MAX_SUMMARY_LENGTH = 2_000
MAX_PUBLISHER_LENGTH = 200
MAX_CATEGORY_LENGTH = 100
MAX_TAG_LENGTH = 100
MAX_TAGS = 30

_JAPANESE_CHARACTER = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid", "yclid"})


def contains_japanese(text: str) -> bool:
    return _JAPANESE_CHARACTER.search(text) is not None


def normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def truncate_text(value: str, limit: int) -> str:
    normalized = normalize_whitespace(value)
    return normalized[:limit]


def normalize_http_url(raw_url: str) -> tuple[str, str]:
    """Validate a display URL and build a conservative duplicate key.

    The display URL is preserved except for surrounding whitespace. The duplicate
    key removes fragments and established tracking parameters, but does not alter
    path spelling or reorder the remaining query parameters.
    """

    display_url = raw_url.strip()
    if not display_url or len(display_url) > 4_096:
        raise ValueError("記事URLが空か長すぎます")
    parsed = urlsplit(display_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("記事URLはhttpまたはhttpsで指定してください")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("記事URLのポートが不正です") from exc
    hostname = parsed.hostname.lower().rstrip(".")
    if not hostname:
        raise ValueError("記事URLのホストが不正です")
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    port_suffix = "" if port is None or default_port else f":{port}"
    user_info = ""
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("認証情報を含む記事URLは扱えません")
    host_for_url = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{user_info}{host_for_url}{port_suffix}"
    path = parsed.path or "/"
    query_parts: list[str] = []
    for part in parsed.query.split("&") if parsed.query else ():
        encoded_key = part.partition("=")[0]
        key = unquote_plus(encoded_key).casefold()
        if key.startswith("utm_") or key in _TRACKING_PARAMETERS:
            continue
        query_parts.append(part)
    query = "&".join(query_parts)
    duplicate_key = urlunsplit((scheme, netloc, path, query, ""))
    return display_url, duplicate_key


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("日時にはタイムゾーンが必要です")
    return value.astimezone(UTC)


def clean_tags(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = truncate_text(value, MAX_TAG_LENGTH)
        folded = cleaned.casefold()
        if not cleaned or folded in seen:
            continue
        seen.add(folded)
        result.append(cleaned)
        if len(result) == MAX_TAGS:
            break
    return tuple(result)
