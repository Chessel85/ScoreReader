# parsers/ug_source.py
"""Raw Ultimate Guitar tab fetch + parse (Chords pages and ASCII-tablature
Tab pages): the UG counterpart of
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

from models.strum_pattern import StrumPattern

# The saved-file format tag/version (parsers/ug_reader.py's UgFileReader,
# main_window.py's Save Ultimate Guitar Import As...). A future format
# change bumps FORMAT_VERSION and read_ug_source_file rejects an older/
# newer file with a clear message rather than a confusing crash - the same
# reasoning packaging/version_info.txt's versioning already uses elsewhere
# in this repo.
FORMAT_TAG = "recall_score_ug_import"
# v2 (2026-08-30): stores the FULL strummings list as `strum_patterns`
# (was one flat `strum_codes` list + top-level `bpm`/`is_triplet`) plus
# `capo`. read_ug_source_file still accepts a v1 file and migrates it.
# v3 (2026-08-31): adds `tab_type` ("Chords" / "Tab"). A v1/v2 payload has
# no such key and is read as "Chords".
FORMAT_VERSION = 3
_SUPPORTED_VERSIONS = (1, 2, 3)

# A real desktop-browser UA - confirmed necessary during discovery (UG's
# response body was ~193KB with this header vs. a near-empty shell without
# one). Chosen to look like an ordinary Chrome/Windows visitor, nothing more.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_JS_STORE_RE = re.compile(r'class="js-store" data-content="(.*?)"></div>', re.S)

# The strum-code decode table lives in models/strum_codes.py; one parsed
# pattern is models/strum_pattern.StrumPattern.


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
    tab_id: int
    source_url: str
    # The FULL tab_view.strummings list (6 of the 18 example tabs carry
    # 2-3 patterns), each with its own name/bpm/denominator/is_triplet.
    # Empty for a tab with no strumming block - "absence isn't an error",
    # same convention as tonality/tuning. The score tempo is
    # strum_patterns[0].bpm when present (see parsers/ug_reader.py).
    strum_patterns: List[StrumPattern] = field(default_factory=list)
    # tab_view.meta.capo - the fret a capo is placed at, or None. Reported
    # in Region 1 as e.g. "2nd fret".
    capo: Optional[int] = None
    # tab.type - "Chords" or "Tab". Informational: ug_timeline_builder.py
    # decides tab-vs-chord per [tab] block from `content`, not from this;
    # it drives a Region 1 "Source" credit and is round-tripped by the .ug
    # save format (v3+).
    tab_type: str = "Chords"


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

    # UG's own `tab.type` vocabulary: "Chords" for a chord/lyric page,
    # "Tab"/"Tabs" for an ASCII-tablature page (both spellings seen in the
    # wild), plus "Pro"/"Bass Tabs"/"Ukulele Chords"/"Guitar Pro"/... which
    # use notation models this import doesn't handle. Normalise the ASCII
    # variants to "Tab" so the stored value and Region 1 "Source" credit are
    # consistent regardless of which spelling the page used.
    raw_tab_type = tab.get("type")
    tab_type = "Tab" if raw_tab_type in ("Tab", "Tabs") else raw_tab_type
    if tab_type not in ("Chords", "Tab"):
        raise ValueError(
            f"This page is a '{raw_tab_type}' tab; only Chords and Tab pages are supported."
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

    capo_val = meta.get("capo")
    capo = int(capo_val) if isinstance(capo_val, (int, float)) and capo_val else None

    strum_patterns = _parse_strummings(tab_view.get("strummings") or [])

    tab_id_val = tab.get("id")
    tab_id = int(tab_id_val) if isinstance(tab_id_val, (int, float)) else 0

    return UgSource(
        song_name=song_name,
        artist_name=artist_name,
        tonality=tonality,
        tuning=tuning,
        difficulty=difficulty,
        content=content,
        tab_id=tab_id,
        source_url=url,
        strum_patterns=strum_patterns,
        capo=capo,
        tab_type=tab_type,
    )


def _parse_strummings(strummings: list) -> List[StrumPattern]:
    """Every entry of tab_view.strummings (not just [0]), each a
    {part, denuminator, bpm, is_triplet, measures[]} object. `measures` is
    misnamed - it is the flat list of slot codes."""
    patterns: List[StrumPattern] = []
    for entry in strummings:
        entry = entry or {}
        bpm_val = entry.get("bpm")
        bpm = int(round(bpm_val)) if isinstance(bpm_val, (int, float)) and bpm_val > 0 else None
        denom_val = entry.get("denuminator")
        denominator = int(denom_val) if isinstance(denom_val, (int, float)) and denom_val else None
        codes = [
            (slot or {}).get("measure")
            for slot in entry.get("measures") or []
            if isinstance((slot or {}).get("measure"), int)
        ]
        patterns.append(
            StrumPattern(
                name=(entry.get("part") or "").strip(),
                bpm=bpm,
                denominator=denominator,
                is_triplet=bool(entry.get("is_triplet")),
                codes=codes,
            )
        )
    return patterns


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
    version = payload.get("version")
    if version not in _SUPPORTED_VERSIONS:
        raise ValueError(
            f"'{file_path}' was saved with a format version ({version!r}) this "
            f"app does not support (expected one of {_SUPPORTED_VERSIONS})."
        )

    try:
        if version == 1:
            # v1 stored one flat code list + top-level bpm/is_triplet and no
            # denominator. Migrate to a single unnamed pattern; the dialog
            # degrades to "slot N" labels for it (denominator is honestly
            # unknown, not guessed).
            codes = payload.get("strum_codes") or []
            strum_patterns = (
                [
                    StrumPattern(
                        name="",
                        bpm=payload.get("bpm"),
                        denominator=None,
                        is_triplet=bool(payload.get("is_triplet")),
                        codes=codes,
                    )
                ]
                if (codes or payload.get("bpm"))
                else []
            )
            capo = None
        else:
            strum_patterns = [
                StrumPattern(
                    name=p.get("name", ""),
                    bpm=p.get("bpm"),
                    denominator=p.get("denominator"),
                    is_triplet=bool(p.get("is_triplet")),
                    codes=p.get("codes") or [],
                )
                for p in payload.get("strum_patterns") or []
            ]
            capo = payload.get("capo")

        return UgSource(
            song_name=payload["song_name"],
            artist_name=payload["artist_name"],
            tonality=payload["tonality"],
            tuning=payload["tuning"],
            difficulty=payload["difficulty"],
            content=payload["content"],
            tab_id=payload["tab_id"],
            source_url=payload["source_url"],
            strum_patterns=strum_patterns,
            capo=capo,
            tab_type=payload.get("tab_type", "Chords"),
        )
    except KeyError as e:
        raise ValueError(f"'{file_path}' is missing expected data ({e}).") from e
