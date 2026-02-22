"""
Keyword extraction using TF-IDF, frequency analysis, n-grams, and word cloud.
"""

import os
import re
from collections import Counter
from io import BytesIO

from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer

try:
    from wordcloud import WordCloud
    HAS_WORDCLOUD = True
except ImportError:
    HAS_WORDCLOUD = False


# Common stopwords for social media (English + Thai)
_STOP_WORDS = {
    # English
    "the", "a", "an", "is", "it", "to", "in", "for", "of", "and", "or",
    "but", "not", "this", "that", "with", "on", "at", "from", "by", "as",
    "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "they",
    "them", "his", "her", "its", "their", "what", "which", "who", "whom",
    "so", "if", "then", "than", "too", "very", "can", "just", "don",
    "now", "also", "about", "up", "out", "no", "yes", "all", "more",
    "some", "any", "each", "how", "when", "where", "why", "here", "there",
    "im", "ive", "dont", "cant", "wont", "thats", "its", "hes", "shes",
    "theyre", "youre", "were", "didnt", "doesnt", "isnt", "wasnt",
    "like", "get", "got", "one", "think", "know", "go", "going",
    "really", "much", "well", "even", "still", "thing", "way",
    "lol", "lmao", "omg", "gonna", "wanna", "gotta", "yeah",
    # Thai common stopwords
    "ที่", "ของ", "และ", "ใน", "มี", "ไม่", "ได้", "เป็น", "จะ", "ว่า",
    "กับ", "ก็", "ให้", "แล้ว", "ไป", "มา", "คือ", "นี้", "จาก", "แต่",
    "อยู่", "ถ้า", "กัน", "นะ", "ค่ะ", "ครับ", "นั้น", "หรือ", "แค่",
    "เลย", "ด้วย", "ยัง", "ทำ", "อะไร", "อัน", "ตอน", "ทุก", "เรา",
    "คน", "จริง", "ๆ", "แบบ", "แล้ว", "มัน", "ขอ", "เอา", "อยาก",
    "ต้อง", "เมื่อ", "หา", "ยัง", "สิ", "นะคะ", "ค่า", "จ้า",
}


# ---------------------------------------------------------------------------
# Thai font discovery for WordCloud
# ---------------------------------------------------------------------------

_THAI_FONT_PATH = None


def _find_thai_font() -> str | None:
    """Find a Thai-compatible font for WordCloud rendering."""
    global _THAI_FONT_PATH
    if _THAI_FONT_PATH is not None:
        return _THAI_FONT_PATH if _THAI_FONT_PATH else None

    candidates = []

    # 1. Try pythainlp bundled font
    try:
        from pythainlp import thai_font
        p = thai_font()
        if p and os.path.isfile(p):
            _THAI_FONT_PATH = p
            return _THAI_FONT_PATH
    except Exception:
        pass

    # 2. Common system font paths (Linux / Streamlit Cloud)
    linux_fonts = [
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/tlwg/TlwgTypo.ttf",
        "/usr/share/fonts/truetype/tlwg/Sawasdee.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    candidates.extend(linux_fonts)

    # 3. macOS system fonts
    mac_fonts = [
        "/System/Library/Fonts/Thonburi.ttc",
        "/System/Library/Fonts/Supplemental/Ayuthaya.ttf",
        "/System/Library/Fonts/Supplemental/Krungthep.ttf",
        "/Library/Fonts/NotoSansThai-Regular.ttf",
    ]
    candidates.extend(mac_fonts)

    for path in candidates:
        if os.path.isfile(path):
            _THAI_FONT_PATH = path
            return _THAI_FONT_PATH

    _THAI_FONT_PATH = ""  # cache negative result
    return None


def _has_thai(text: str) -> bool:
    """Check if text contains Thai characters."""
    return bool(re.search(r'[\u0E00-\u0E7F]', text))


def _tokenize_thai(text: str) -> str:
    """Segment Thai text into space-separated tokens using pythainlp."""
    try:
        from pythainlp.tokenize import word_tokenize
        tokens = word_tokenize(text, engine="newmm")
        return " ".join(t.strip() for t in tokens if t.strip())
    except ImportError:
        return text


def _clean_text(text: str) -> str:
    """Basic text cleaning for keyword extraction."""
    text = text.lower()
    text = re.sub(r'https?://\S+', '', text)  # Remove URLs
    text = re.sub(r'@\w+', '', text)  # Remove mentions
    text = re.sub(r'#(\w+)', r'\1', text)  # Keep hashtag text
    text = re.sub(r'[^\w\s\u0E00-\u0E7F]', ' ', text)  # Remove punctuation (keep Thai)
    text = re.sub(r'\s+', ' ', text).strip()
    # Tokenize Thai text so vectorizers can work with it
    if _has_thai(text):
        text = _tokenize_thai(text)
    return text


def analyze_keywords(comments: list[dict], top_n: int = 30) -> dict:
    """Extract keywords using TF-IDF and frequency analysis.

    Returns:
        {
            "tfidf_keywords": [(word, score), ...],
            "frequency_keywords": [(word, count), ...],
            "bigrams": [(phrase, count), ...],
            "trigrams": [(phrase, count), ...],
            "wordcloud_bytes": bytes or None,
        }
    """
    if not comments:
        return {}

    texts = [_clean_text(c.get("text", "")) for c in comments]
    texts = [t for t in texts if len(t) > 2]

    if len(texts) < 3:
        return {}

    # TF-IDF keywords
    tfidf_keywords = []
    try:
        tfidf = TfidfVectorizer(
            max_features=top_n * 2,
            stop_words=list(_STOP_WORDS),
            min_df=2,
            max_df=0.8,
            token_pattern=r'\S{2,}',
        )
        tfidf_matrix = tfidf.fit_transform(texts)
        feature_names = tfidf.get_feature_names_out()
        scores = tfidf_matrix.sum(axis=0).A1
        tfidf_keywords = sorted(
            zip(feature_names, scores), key=lambda x: x[1], reverse=True
        )[:top_n]
    except Exception:
        pass

    # Frequency keywords
    freq_keywords = []
    try:
        all_words = []
        for t in texts:
            words = t.split()
            all_words.extend(w for w in words if w not in _STOP_WORDS and len(w) > 2)
        freq_keywords = Counter(all_words).most_common(top_n)
    except Exception:
        pass

    # N-grams
    bigrams = _extract_ngrams(texts, 2, top_n=15)
    trigrams = _extract_ngrams(texts, 3, top_n=10)

    # Word cloud
    wordcloud_bytes = None
    if HAS_WORDCLOUD and freq_keywords:
        try:
            freq_dict = dict(freq_keywords[:100])
            wc_kwargs = dict(
                width=800,
                height=400,
                background_color="#0B0F1A",
                color_func=lambda *a, **k: "#3B82F6",
                max_words=80,
                prefer_horizontal=0.7,
            )
            thai_font = _find_thai_font()
            if thai_font:
                wc_kwargs["font_path"] = thai_font
            wc = WordCloud(**wc_kwargs)
            wc.generate_from_frequencies(freq_dict)
            buf = BytesIO()
            wc.to_image().save(buf, format="PNG")
            wordcloud_bytes = buf.getvalue()
        except Exception:
            pass

    return {
        "tfidf_keywords": tfidf_keywords,
        "frequency_keywords": freq_keywords,
        "bigrams": bigrams,
        "trigrams": trigrams,
        "wordcloud_bytes": wordcloud_bytes,
    }


def _extract_ngrams(texts: list[str], n: int, top_n: int = 15) -> list[tuple]:
    """Extract top n-grams from texts."""
    try:
        vec = CountVectorizer(
            ngram_range=(n, n),
            stop_words=list(_STOP_WORDS),
            min_df=2,
            max_df=0.8,
            token_pattern=r'\S{2,}',
        )
        matrix = vec.fit_transform(texts)
        feature_names = vec.get_feature_names_out()
        counts = matrix.sum(axis=0).A1
        return sorted(
            zip(feature_names, counts), key=lambda x: x[1], reverse=True
        )[:top_n]
    except Exception:
        return []
