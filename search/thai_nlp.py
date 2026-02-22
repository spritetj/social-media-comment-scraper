"""
Thai NLP utilities — word segmentation, transliteration, and stopwords.

Uses pythainlp as a hard dependency for accurate Thai language processing.
"""

import re

from pythainlp.tokenize import word_tokenize
from pythainlp.transliterate import romanize as _romanize_thai

# ---------------------------------------------------------------------------
# Extended Thai stopwords (grammar particles, pronouns, connectors)
# ---------------------------------------------------------------------------

THAI_STOPWORDS = {
    # Pronouns
    "ผม", "ฉัน", "เรา", "คุณ", "เขา", "มัน", "พวก", "ท่าน",
    # Grammar particles / connectors
    "ที่", "ของ", "ใน", "มี", "ได้", "ไม่", "จะ", "เป็น", "แล้ว", "ก็",
    "ว่า", "ให้", "กับ", "คือ", "กัน", "นี้", "แต่", "อยู่", "จาก", "หรือ",
    "ถึง", "อยู่ดีๆ", "ขึ้นมา", "เลย", "ยัง", "ต้อง", "ดี", "มาก",
    "หา", "ทำ", "ไป", "มา", "เอา", "ดู", "ตัว", "คน", "อะไร", "แบบ",
    "นะ", "ครับ", "ค่ะ", "นั้น", "อัน", "ซึ่ง", "โดย",
    # Question words (often not useful as search keywords)
    "ทำไม", "อย่างไร", "ยังไง", "เท่าไหร่", "ไหน",
    # Auxiliary verbs
    "จะ", "ควร", "อาจ", "น่า", "กำลัง", "เคย",
    # Misc high-frequency words
    "เรื่อง", "อัน", "ตรง", "ขึ้น", "ลง", "ออก", "เข้า",
    "แค่", "ก่อน", "หลัง", "ระหว่าง", "ตอน", "บ้าง", "ทุก",
}


# ---------------------------------------------------------------------------
# Word segmentation
# ---------------------------------------------------------------------------

def segment_thai(text: str) -> list[str]:
    """Segment Thai text into individual words using pythainlp.

    Returns a list of word tokens (whitespace and empty strings removed).
    """
    tokens = word_tokenize(text, engine="newmm")
    return [t.strip() for t in tokens if t.strip()]


# ---------------------------------------------------------------------------
# Meaningful word extraction
# ---------------------------------------------------------------------------

def extract_meaningful_thai_words(text: str) -> list[str]:
    """Extract semantically meaningful Thai words from text.

    Filters out stopwords, single-character tokens, whitespace,
    and pure punctuation. Returns unique words in order of appearance.
    """
    tokens = segment_thai(text)
    seen = set()
    meaningful = []
    for token in tokens:
        # Skip non-Thai tokens (handled separately as English)
        if not any("\u0E00" <= ch <= "\u0E7F" for ch in token):
            continue
        # Skip stopwords and very short tokens
        if token in THAI_STOPWORDS or len(token) <= 1:
            continue
        if token not in seen:
            seen.add(token)
            meaningful.append(token)
    return meaningful


# ---------------------------------------------------------------------------
# Transliteration: English → Thai script (syllable-based phonetic mapping)
# ---------------------------------------------------------------------------

# Consonant onset mappings (English → Thai initial consonant)
_ONSET_MAP = {
    # Clusters (longest first for greedy match)
    "str": "สตร", "shr": "ชร", "sch": "ช", "scr": "สคร",
    "spl": "สปล", "spr": "สปร",
    "sh": "ช", "ch": "ช", "th": "ท", "ph": "ฟ",
    "wh": "ว", "gh": "ก", "qu": "คว",
    "bl": "บล", "br": "บร", "cl": "คล", "cr": "คร",
    "dr": "ดร", "fl": "ฟล", "fr": "ฟร",
    "gl": "กล", "gr": "กร", "pl": "ปล", "pr": "ปร",
    "sl": "สล", "sm": "สม", "sn": "สน",
    "sp": "สป", "st": "สต", "sw": "สว",
    "tr": "ทร", "tw": "ทว", "ts": "ทซ",
    # Singles — ป for "p" (common Thai loanword convention)
    "b": "บ", "c": "ค", "d": "ด", "f": "ฟ", "g": "ก",
    "h": "ฮ", "j": "จ", "k": "ค", "l": "ล", "m": "ม",
    "n": "น", "p": "ป", "r": "ร", "s": "ซ", "t": "ท",
    "v": "ว", "w": "ว", "x": "ซ", "y": "ย", "z": "ซ",
}

# Vowel mappings — split by syllable type because Thai vowel length
# depends on whether the syllable is open (CV) or closed (CVC).
#
# Each entry: (prefix, suffix) — Thai vowels can go before, after,
# above, or around the consonant.
#
# Open syllable (no coda): vowels tend to be LONG
_VOWEL_OPEN = {
    "oo": ("", "ู"), "ee": ("", "ี"), "ea": ("", "ี"),
    "ou": ("เ", "า"), "ow": ("เ", "า"),
    "ai": ("ไ", ""), "ay": ("เ", ""),
    "ei": ("เ", ""), "ey": ("เ", ""),
    "oi": ("", "อย"), "oy": ("", "อย"),
    "ie": ("", "ี"), "oa": ("โ", ""),
    "au": ("", "อ"), "aw": ("", "อ"),
    # Single vowels — long forms for open syllables
    "a": ("", "า"), "e": ("เ", ""), "i": ("", "ิ"),
    "o": ("โ", ""), "u": ("", "ู"),
}

# Closed syllable (has coda): vowels tend to be SHORT
_VOWEL_CLOSED = {
    "oo": ("", "ู"), "ee": ("", "ี"), "ea": ("", "ี"),
    "ou": ("เ", "า"), "ow": ("เ", "า"),
    "ai": ("ไ", ""), "ay": ("เ", ""),
    "ei": ("เ", ""), "ey": ("เ", ""),
    "oi": ("", "อย"), "oy": ("", "อย"),
    "ie": ("", "ี"), "oa": ("โ", ""),
    "au": ("", "อ"), "aw": ("", "อ"),
    # Single vowels — short forms for closed syllables
    "a": ("", "ั"), "e": ("เ", "็"), "i": ("", "ิ"),
    "o": ("", "อ"), "u": ("", "ุ"),
}

# Final consonant (coda) mappings — uses Thai final-position forms
_CODA_MAP = {
    "tion": "ชั่น", "sion": "ชั่น",
    "ck": "ค", "ng": "ง", "nk": "งค์", "nt": "นท์",
    "nd": "นด์", "mp": "มป์", "lk": "ลค์", "nce": "นซ์",
    "b": "บ", "d": "ด", "f": "ฟ", "g": "ก",
    "k": "ค", "l": "ล", "m": "ม", "n": "น",
    "p": "ป", "r": "ร์", "s": "ส", "t": "ท",
    "x": "กซ์", "z": "ซ",
}

# Valid English syllable onsets (used to correctly split consonant clusters)
_VALID_ONSETS = {
    # Single consonants (all are valid onsets)
    "b", "c", "d", "f", "g", "h", "j", "k", "l", "m",
    "n", "p", "q", "r", "s", "t", "v", "w", "x", "y", "z",
    # Two-consonant clusters
    "bl", "br", "ch", "cl", "cr", "dr", "dw", "fl", "fr",
    "gh", "gl", "gr", "kl", "kn", "ph", "pl", "pr", "qu",
    "sc", "sh", "sk", "sl", "sm", "sn", "sp", "st", "sw",
    "th", "tr", "tw", "wh", "wr",
    # Three-consonant clusters
    "sch", "scr", "shr", "spl", "spr", "str", "squ",
}

# Regex: match (onset consonants)(vowel nucleus).
_CV_RE = re.compile(
    r"([bcdfghjklmnpqrstvwxyz]{0,3})"  # onset consonants
    r"([aeiouy]+)",                     # vowel nucleus
    re.IGNORECASE,
)


def _match_longest(text: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Match the longest key in mapping at the start of text."""
    for length in range(min(4, len(text)), 0, -1):
        chunk = text[:length].lower()
        if chunk in mapping:
            return mapping[chunk], length
    return "", 0


def _find_valid_onset(consonants: str) -> tuple[str, str]:
    """Split a consonant cluster into (coda_of_prev, valid_onset).

    Finds the longest valid English onset at the END of the cluster.
    Leading consonants that aren't part of the onset become coda.

    E.g., "nd" → ("n", "d"), "ms" → ("m", "s"), "str" → ("", "str"),
          "tfl" → ("t", "fl"), "b" → ("", "b")
    """
    if not consonants:
        return "", ""
    c = consonants.lower()
    # Try longest valid onset from the end
    for onset_len in range(min(3, len(c)), 0, -1):
        candidate = c[-onset_len:]
        if candidate in _VALID_ONSETS:
            coda_part = c[:-onset_len]
            return coda_part, candidate
    # No valid onset found — treat everything as coda
    return c, ""


def _phonetic_transliterate(word: str) -> str:
    """Convert an English word to Thai script via syllable-based phonetic mapping.

    Key design choices:
    - Validates onset clusters against real English phonotactics
    - Open syllables (CV) use long vowels, closed (CVC) use short vowels
    - p → ป (unaspirated, standard Thai loanword convention)
    """
    w = word.lower().strip()
    if not w:
        return ""

    # --- Pass 1: find raw CV chunks via regex ---
    raw_chunks: list[tuple[str, str]] = []
    last_end = 0

    for m in _CV_RE.finditer(w):
        raw_chunks.append((m.group(1), m.group(2), m.start(), m.end()))
        last_end = m.end()

    trailing = w[last_end:]

    # --- Pass 2: validate onsets and distribute consonants properly ---
    # Between two vowel chunks, consonants must be split into:
    # coda of previous syllable + valid onset of next syllable
    syllables: list[tuple[str, str, str]] = []  # (onset, vowel, coda)

    for idx, (raw_onset, vowel, start, end) in enumerate(raw_chunks):
        if idx == 0:
            # First syllable: any leading consonants are the onset
            # (even if not a standard cluster — it's word-initial)
            onset = raw_onset
            coda_for_prev = ""
        else:
            # Split inter-vocalic consonants: prev coda + valid onset
            coda_for_prev, onset = _find_valid_onset(raw_onset)

        # Attach coda_for_prev to the previous syllable
        if coda_for_prev and syllables:
            prev = syllables[-1]
            syllables[-1] = (prev[0], prev[1], prev[2] + coda_for_prev)

        syllables.append((onset, vowel, ""))

    # Attach trailing consonants as coda of last syllable
    if trailing and syllables:
        prev = syllables[-1]
        syllables[-1] = (prev[0], prev[1], prev[2] + trailing)

    # --- Pass 3: convert each syllable to Thai ---
    parts: list[str] = []
    for onset_str, vowel_str, coda_str in syllables:
        has_coda = bool(coda_str)

        # Map onset consonant(s)
        thai_onset = ""
        if onset_str:
            i = 0
            while i < len(onset_str):
                mapped, length = _match_longest(onset_str[i:], _ONSET_MAP)
                if mapped:
                    thai_onset += mapped
                    i += length
                else:
                    i += 1
        else:
            thai_onset = "อ"

        # Map vowel — open vs closed syllable determines vowel length
        vowel_map = _VOWEL_CLOSED if has_coda else _VOWEL_OPEN
        v_prefix, v_suffix = "", ""
        for vlen in range(min(3, len(vowel_str)), 0, -1):
            vchunk = vowel_str[:vlen].lower()
            if vchunk in vowel_map:
                v_prefix, v_suffix = vowel_map[vchunk]
                remainder = vowel_str[vlen:]
                for rv in remainder:
                    rp, rs = vowel_map.get(rv, ("", rv))
                    v_prefix += rp
                    v_suffix += rs
                break

        # Map coda consonant(s)
        thai_coda = ""
        if coda_str:
            i = 0
            while i < len(coda_str):
                mapped, length = _match_longest(coda_str[i:], _CODA_MAP)
                if mapped:
                    thai_coda += mapped
                    i += length
                else:
                    i += 1

        parts.append(v_prefix + thai_onset + v_suffix + thai_coda)

    return "".join(parts)


def get_thai_transliterations(english_word: str) -> list[str]:
    """Convert an English word to possible Thai transliterations.

    Uses a phonetic mapping table to produce Thai-script approximations
    of English brand/entity names. E.g., "starbucks" → ["ซทาร์บอุคซ์"].

    Also tries pythainlp's transliterate engines if available.

    Returns a list of Thai transliterations (may be empty if the word
    is too short or contains no transliterable characters).
    """
    if not english_word or not english_word.strip():
        return []

    word = english_word.strip()
    # Skip very short words (single char)
    if len(word) < 2:
        return []

    results: list[str] = []

    # Try pythainlp engines first (they need optional deps)
    for engine in ("tltk", "ipa", "icu"):
        try:
            from pythainlp.transliterate import transliterate as _transliterate

            thai = _transliterate(word, engine=engine)
            if (
                thai
                and thai != word
                and any("\u0E00" <= ch <= "\u0E7F" for ch in thai)
                and thai not in results
            ):
                results.append(thai)
        except Exception:
            pass

    # Phonetic mapping fallback
    phonetic = _phonetic_transliterate(word)
    if phonetic and phonetic not in results:
        results.append(phonetic)

    return results


# ---------------------------------------------------------------------------
# Romanization: Thai → English script
# ---------------------------------------------------------------------------

def romanize_thai(thai_text: str) -> str:
    """Convert Thai text to romanized English (RTGS system).

    E.g., "กระแส" → "kraasae"
    """
    try:
        return _romanize_thai(thai_text, engine="royin")
    except Exception:
        return thai_text
