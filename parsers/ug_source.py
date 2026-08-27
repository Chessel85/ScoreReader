# parsers/ug_source.py
"""Raw Ultimate Guitar chord-tab fetch + parse: the UG counterpart of
xml_source.py/midi_source.py/gp_source.py. UgReader and UgTimelineBuilder
both read this SAME parse so they can't independently re-fetch/re-walk the
page and drift (the bug class CLAUDE.md documents MusicXMLReader's two-pass
read once fell into).

UG serves a near-empty page shell to a plain machine fetch (confirmed during
discovery - Claude Code's own WebFetch tool got back only the page's <title>
tag), but a normal request with a desktop-browser User-Agent gets a full 200
response - no bot-block, no headless browser/JS execution needed. The page
embeds its entire React app state as one JSON blob in a
`<div class="js-store" data-content="...">` element (server-rendered
hydration data), which is what this module actually reads - not the visible,
rendered HTML.

Validated directly against a real page during discovery
(https://tabs.ultimate-guitar.com/tab/oasis/half-the-world-away-chords-46064):
every chord symbol found parses via music21.harmony.ChordSymbol, and the
chord-to-lyric character-column alignment in wiki_tab.content is exact.
"""
import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

# The saved-file format tag/version (parsers/ug_reader.py's UgFileReader,
# main_window.py's Save Ultimate Guitar Import As...). A future format
# change bumps FORMAT_VERSION and read_ug_source_file rejects an older/
# newer file with a clear message rather than a confusing crash - the same
# reasoning packaging/version_info.txt's versioning already uses elsewhere
# in this repo.
FORMAT_TAG = "recall_score_ug_import"
FORMAT_VERSION = 1

# A real desktop-browser UA - confirmed necessary during discovery (UG's
# response body was ~193KB with this header vs. a near-empty shell without
# one). Chosen to look like an ordinary Chrome/Windows visitor, nothing more.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_JS_STORE_RE = re.compile(r'class="js-store" data-content="(.*?)"></div>', re.S)

# S2: the strum-code tables and both decodes now live in
# models/strum_codes.py (a pure lookup table, like models/gm_instruments.py),
# so models/ need not import from parsers/ just to read them. Import them
# from there, not from here.


@dataclass
class UgSource:
    song_name: str
    artist_name: str
    tonality: str
    tuning: str
    difficulty: str
    # Raw tab_view.wiki_tab.content markup: [Section]/[tab]...[/tab]/
    # [ch]...[/ch]. Parsed by ug_timeline_builder.py, not here - this module
    # only fetches and validates, mirroring gp_source.py's raw-parse-only
    # scope.
    content: str
    bpm: Optional[int]
    is_triplet: bool
    tab_id: int
    source_url: str
    # Raw tab_view.strummings[0].measures[] codes, unresolved - see
    # strumming_pattern_text/strum_directions below for the two ways this
    # gets interpreted. Empty for a tab with no strumming block, same
    # "absence isn't an error" convention as tonality/tuning above when UG
    # doesn't supply one.
    strum_codes: List[int] = field(default_factory=list)


def validate_url_shape(url: str) -> None:
    """Cheap, synchronous check - confirms this is even shaped like a UG tab
    page before any network call. Shared with
    widgets/ultimate_guitar_import_dialog.py, which runs this same check on
    Accept before ever starting the async fetch. The real validation (does
    the page actually have tab data, is it a Chords-type tab) can only
    happen after fetching - see read_ug_source below."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("That doesn't look like a web address.")
    host = parsed.netloc.lower()
    if not (host == "ultimate-guitar.com" or host.endswith(".ultimate-guitar.com")):
        raise ValueError("That doesn't look like an Ultimate Guitar page.")
    if not parsed.path.startswith("/tab/"):
        raise ValueError(
            "That doesn't look like an Ultimate Guitar tab page "
            "(expected a page under /tab/...)."
        )


def read_ug_source(url: str) -> UgSource:
    validate_url_shape(url)

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw_html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"Ultimate Guitar returned an error ({e.code}) for that URL.") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach Ultimate Guitar: {e.reason}") from e

    match = _JS_STORE_RE.search(raw_html)
    if match is None:
        raise ValueError(
            "Could not find tab data on that page - it may not be a real "
            "Ultimate Guitar tab page."
        )

    try:
        data = json.loads(html.unescape(match.group(1)))
        page_data = data["store"]["page"]["data"]
        tab = page_data["tab"]
        tab_view = page_data["tab_view"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ValueError(f"Could not parse Ultimate Guitar page data: {e}") from e

    tab_type = tab.get("type")
    if tab_type != "Chords":
        raise ValueError(
            f"This page is a '{tab_type}' tab; only Chords tabs are supported."
        )

    song_name = (tab.get("song_name") or "").strip()
    artist_name = (tab.get("artist_name") or "").strip()
    if not song_name or not artist_name:
        raise ValueError("This page doesn't look like a real song entry (missing title/artist).")

    wiki_tab = tab_view.get("wiki_tab") or {}
    content = wiki_tab.get("content") or ""
    if not content.strip():
        raise ValueError("This tab page has no chord/lyric content to import.")

    meta = tab_view.get("meta") or {}
    tonality = (meta.get("tonality") or "").strip()
    tuning_info = meta.get("tuning") or {}
    tuning = (tuning_info.get("value") or tuning_info.get("name") or "").strip()
    difficulty = (tab.get("difficulty") or meta.get("difficulty") or "").strip()

    bpm: Optional[int] = None
    is_triplet = False
    strum_codes: List[int] = []
    strummings = tab_view.get("strummings") or []
    if strummings:
        first = strummings[0] or {}
        bpm_val = first.get("bpm")
        if isinstance(bpm_val, (int, float)) and bpm_val > 0:
            bpm = int(round(bpm_val))
        is_triplet = bool(first.get("is_triplet"))
        for entry in first.get("measures") or []:
            code = (entry or {}).get("measure")
            if isinstance(code, int):
                strum_codes.append(code)

    tab_id_val = tab.get("id")
    tab_id = int(tab_id_val) if isinstance(tab_id_val, (int, float)) else 0

    return UgSource(
        song_name=song_name,
        artist_name=artist_name,
        tonality=tonality,
        tuning=tuning,
        difficulty=difficulty,
        content=content,
        bpm=bpm,
        is_triplet=is_triplet,
        tab_id=tab_id,
        source_url=url,
        strum_codes=strum_codes,
    )


def write_ug_source(source: UgSource, file_path: str) -> None:
    """Save the source data a UG import was built from - not the derived,
    bar-numbered timeline (UgTimelineBuilder re-derives that fresh from
    this on every load, exactly like every other format in this app is
    re-parsed from its own file rather than a cached derived form)."""
    payload = {"format": FORMAT_TAG, "version": FORMAT_VERSION}
    payload.update(asdict(source))
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_ug_source_file(file_path: str) -> UgSource:
    """Loads a previously-saved .ug file - the local-file counterpart of
    read_ug_source's network fetch. Both feed the exact same downstream
    build (parsers/ug_reader.py's shared _build_music_data), so a saved-
    and-reopened import looks identical to the original live one."""
    with open(file_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if payload.get("format") != FORMAT_TAG:
        raise ValueError(f"'{file_path}' is not a Recall Score Ultimate Guitar import file.")
    if payload.get("version") != FORMAT_VERSION:
        raise ValueError(
            f"'{file_path}' was saved with a different format version "
            f"({payload.get('version')!r}) than this app supports ({FORMAT_VERSION})."
        )

    try:
        return UgSource(
            song_name=payload["song_name"],
            artist_name=payload["artist_name"],
            tonality=payload["tonality"],
            tuning=payload["tuning"],
            difficulty=payload["difficulty"],
            content=payload["content"],
            bpm=payload["bpm"],
            is_triplet=payload["is_triplet"],
            tab_id=payload["tab_id"],
            source_url=payload["source_url"],
            strum_codes=payload.get("strum_codes", []),
        )
    except KeyError as e:
        raise ValueError(f"'{file_path}' is missing expected data ({e}).") from e
