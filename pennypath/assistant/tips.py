"""
tips.py  —  Search the curated personal-finance Q&A in data/financial_tips.json.

Ranking blends two TF-IDF cosine similarities:
  • question-only, word 1–2-grams, stop words kept — so phrasing like
    "how much should my emergency fund be" matches that exact question;
  • question + answer, stop words removed — so content words in the answer count.
Also serves as the chatbot's offline fallback when Ollama isn't running. There,
a small finance-keyword check decides whether to answer at all, because TF-IDF
similarity alone can't separate "best way to save for college" from
"best way to learn guitar".
"""
import json
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from pennypath.paths import TIPS_JSON

TIPS_FILE = TIPS_JSON

# Word prefixes that mark a question as personal-finance related (offline gate only).
_FINANCE_TERMS = re.compile(
    r"\b(budget|sav|spend|expens|debt|credit|loan|invest|fund|stock|bond|etf|crypto|bitcoin|"
    r"ira|roth|401k|401\(k\)|retire|pension|social security|mortgage|rent|house|home|tax|"
    r"insur|income|salary|wage|paycheck|money|cash|pay|interest|apr|bank|account|afford|"
    r"bill|fee|financ|wealth|net worth|emergency|portfolio|dividend|inflation|price|cost|"
    r"car|college|tuition|student|frugal|cheap|grocer|subscription|side hustle|raise|"
    r"buy|purchas|shop|impulse|lease)",
    re.IGNORECASE,
)


def is_finance_query(text: str) -> bool:
    return bool(_FINANCE_TERMS.search(text or ""))


class TipLibrary:
    QUESTION_WEIGHT = 0.6

    def __init__(self, path: str = TIPS_FILE):
        with open(path, encoding="utf-8") as f:
            self.tips: list[dict] = json.load(f)
        questions = [t["question"] for t in self.tips]
        docs = [f"{t['question']} {t['question']} {t['answer']}" for t in self.tips]
        self._q_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit(questions)
        self._q_mat = self._q_vec.transform(questions)
        self._d_vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2),
                                      sublinear_tf=True).fit(docs)
        self._d_mat = self._d_vec.transform(docs)

    def _scores(self, query: str):
        q = linear_kernel(self._q_vec.transform([query]), self._q_mat).ravel()
        d = linear_kernel(self._d_vec.transform([query]), self._d_mat).ravel()
        return self.QUESTION_WEIGHT * q + (1 - self.QUESTION_WEIGHT) * d

    def search(self, query: str, k: int = 5, min_score: float = 0.1) -> list[dict]:
        """Return up to k tips most similar to `query`, each with a `score` in [0, 1]."""
        query = (query or "").strip()
        if not query:
            return []
        scores = self._scores(query)
        best = scores.argsort()[::-1][:k]
        return [{**self.tips[i], "score": round(float(scores[i]), 3)}
                for i in best if scores[i] >= min_score]

    def best_answer(self, query: str, min_score: float = 0.15) -> dict | None:
        """Single best tip for a chat question, or None if it isn't a finance question."""
        if not is_finance_query(query):
            return None
        hits = self.search(query, k=1, min_score=min_score)
        return hits[0] if hits else None


_library: TipLibrary | None = None


def library() -> TipLibrary:
    """Shared, lazily built instance."""
    global _library
    if _library is None:
        _library = TipLibrary()
    return _library


def tips_menu():
    """CLI: search tips until the user enters a blank line."""
    lib = library()
    print("\n\033[32mFINANCIAL TIPS\033[0m  — ask a question (blank line to go back)")
    while True:
        query = input("\nSearch tips: ").strip()
        if not query:
            return
        hits = lib.search(query, k=3)
        if not hits:
            print("\033[33mNo matching tips. Try different words, e.g. 'emergency fund'.\033[0m")
            continue
        for hit in hits:
            print(f"\n\033[36m● {hit['question'].capitalize()}?\033[0m")
            print(f"  {hit['answer']}")
