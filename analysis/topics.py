"""
Topic modeling using LDA (Latent Dirichlet Allocation) via scikit-learn.
"""

import re

from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer

# Import shared stopwords and text helpers from keywords module
from analysis.keywords import _STOP_WORDS, _has_thai, _tokenize_thai


def _clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'#(\w+)', r'\1', text)
    text = re.sub(r'[^\w\s\u0E00-\u0E7F]', ' ', text)  # Keep Thai chars
    text = re.sub(r'\s+', ' ', text).strip()
    if _has_thai(text):
        text = _tokenize_thai(text)
    return text


def analyze_topics(comments: list[dict], n_topics: int = 5, n_words: int = 8) -> dict:
    """Discover topics using LDA.

    Returns:
        {
            "topics": [
                {
                    "id": int,
                    "keywords": [str, ...],
                    "weight": float,
                    "representative_comments": [str, ...],
                },
                ...
            ],
            "n_topics": int,
        }
    """
    if not comments:
        return {}

    texts = [_clean_text(c.get("text", "")) for c in comments]
    texts = [t for t in texts if len(t) > 10]

    if len(texts) < 20:
        return {"topics": [], "n_topics": 0, "reason": "Need at least 20 comments for topic modeling"}

    # Adjust number of topics based on corpus size
    n_topics = min(n_topics, max(2, len(texts) // 10))

    try:
        vectorizer = CountVectorizer(
            stop_words=list(_STOP_WORDS),
            min_df=3,
            max_df=0.85,
            max_features=1000,
            token_pattern=r'\S{2,}',
        )
        doc_term_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()

        if doc_term_matrix.shape[1] < n_topics:
            return {"topics": [], "n_topics": 0, "reason": "Not enough unique terms"}

        lda = LatentDirichletAllocation(
            n_components=n_topics,
            max_iter=20,
            learning_method="online",
            random_state=42,
        )
        doc_topics = lda.fit_transform(doc_term_matrix)

        topics = []
        for idx, topic_dist in enumerate(lda.components_):
            top_word_indices = topic_dist.argsort()[-n_words:][::-1]
            keywords = [feature_names[i] for i in top_word_indices]
            weight = topic_dist.sum()

            # Find representative comments for this topic
            topic_scores = doc_topics[:, idx]
            top_doc_indices = topic_scores.argsort()[-3:][::-1]
            representative = []
            for di in top_doc_indices:
                if di < len(comments):
                    representative.append(comments[di].get("text", "")[:200])

            topics.append({
                "id": idx + 1,
                "keywords": keywords,
                "weight": round(float(weight), 2),
                "representative_comments": representative,
            })

        # Sort by weight
        topics.sort(key=lambda t: t["weight"], reverse=True)

        return {
            "topics": topics,
            "n_topics": len(topics),
        }

    except Exception as e:
        return {"topics": [], "n_topics": 0, "reason": str(e)}
