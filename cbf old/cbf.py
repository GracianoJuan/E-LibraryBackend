import json
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import MinMaxScaler


class BaseCBF(ABC):
    REQUIRED_OUTPUT_COLUMNS = [
        "book_id",
        "title",
        "authors",
        "genre",
        "subjects",
        "similarity_score",
    ]

    def __init__(self, name: str):
        self.name = name
        self.df: Optional[pd.DataFrame] = None
        self.title_to_index: Dict[str, int] = {}
        self.similarity_matrix: Optional[np.ndarray] = None

    def _prepare_df(self, df: pd.DataFrame) -> pd.DataFrame:
        prepared = df.copy()
        for col in ["book_id", "title", "authors", "genre", "subjects", "description", "text_features"]:
            if col not in prepared.columns:
                prepared[col] = ""

        # for col in ["pages", "ratings_avg", "publish_year", "ratings_count", "want_to_read_count", "edition_count"]:
        for col in ["pages""publish_year"]:
            if col not in prepared.columns:
                prepared[col] = 0
            prepared[col] = pd.to_numeric(prepared[col], errors="coerce").fillna(0)

        prepared["title"] = prepared["title"].astype(str).str.strip()
        prepared["subjects"] = prepared["subjects"].astype(str).fillna("")
        prepared["genre"] = prepared["genre"].astype(str).fillna("")
        prepared["description"] = prepared["description"].astype(str).fillna("")

        if "text_features" not in prepared.columns or prepared["text_features"].astype(str).str.len().eq(0).all():
            prepared["text_features"] = (
                prepared["subjects"].fillna("")
                + " "
                + prepared["genre"].fillna("")
                + " "
                + prepared["description"].fillna("")
            ).str.strip()

        prepared = prepared.reset_index(drop=True)
        return prepared

    def _build_title_index(self) -> None:
        if self.df is None:
            self.title_to_index = {}
            return
        self.title_to_index = {}
        for idx, title in enumerate(self.df["title"].tolist()):
            key = str(title).strip().lower()
            if key and key not in self.title_to_index:
                self.title_to_index[key] = idx

    def _resolve_title_index(self, title: str) -> int:
        key = title.strip().lower()
        if key in self.title_to_index:
            return self.title_to_index[key]

        candidates = [k for k in self.title_to_index.keys() if key in k]
        if candidates:
            return self.title_to_index[candidates[0]]

        raise ValueError(f"Title not found: {title}")

    def get_recommendations(self, title: str, top_n: int = 5) -> pd.DataFrame:
        if self.df is None or self.similarity_matrix is None:
            raise RuntimeError("Model has not been fitted or loaded")

        idx = self._resolve_title_index(title)
        scores = self.similarity_matrix[idx].copy()
        scores[idx] = -1.0

        top_indices = np.argsort(scores)[::-1][:top_n]
        recs = self.df.loc[top_indices, ["book_id", "title", "authors", "genre", "subjects"]].copy()
        recs["similarity_score"] = scores[top_indices]
        return recs[self.REQUIRED_OUTPUT_COLUMNS].reset_index(drop=True)

    def get_similarity_score(self, title_a: str, title_b: str) -> float:
        if self.similarity_matrix is None:
            raise RuntimeError("Model has not been fitted or loaded")
        idx_a = self._resolve_title_index(title_a)
        idx_b = self._resolve_title_index(title_b)
        return float(self.similarity_matrix[idx_a, idx_b])

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> None:
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        pass


class TFIDFCosine(BaseCBF):
    def __init__(self):
        super().__init__(name="tfidf")
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.scaler: Optional[MinMaxScaler] = None

    def fit(self, df: pd.DataFrame) -> None:
        self.df = self._prepare_df(df)
        self._build_title_index()

        text_data = self.df["text_features"].fillna("").astype(str)
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            stop_words="english",
        )
        text_matrix = self.vectorizer.fit_transform(text_data)

        # num_cols = ["pages", "ratings_avg", "publish_year"]
        num_cols = ["pages"]
        self.scaler = MinMaxScaler()
        numeric_dense = self.scaler.fit_transform(self.df[num_cols])
        numeric_matrix = sparse.csr_matrix(numeric_dense * 0.2)

        features = sparse.hstack([text_matrix, numeric_matrix], format="csr")
        self.similarity_matrix = cosine_similarity(features)

    def save(self, path: str) -> None:
        if self.similarity_matrix is None:
            raise RuntimeError("No similarity matrix to save")
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        np.save(target / "tfidf_similarity.npy", self.similarity_matrix)

    def load(self, path: str) -> None:
        target = Path(path)
        self.similarity_matrix = np.load(target / "tfidf_similarity.npy")


class Word2VecCBF(BaseCBF):
    def __init__(self):
        super().__init__(name="word2vec")
        self.word2vec_model = None
        self.book_vectors: Optional[np.ndarray] = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", text.lower())
        return [tok for tok in cleaned.split() if tok]

    def _mean_vector(self, tokens: List[str], vector_size: int) -> np.ndarray:
        if not tokens or self.word2vec_model is None:
            return np.zeros(vector_size, dtype=np.float32)
        vectors = [self.word2vec_model.wv[token] for token in tokens if token in self.word2vec_model.wv]
        if not vectors:
            return np.zeros(vector_size, dtype=np.float32)
        return np.mean(vectors, axis=0)

    def fit(self, df: pd.DataFrame) -> None:
        try:
            from gensim.models import Word2Vec
        except ImportError as exc:
            raise ImportError("gensim is required for Word2VecCBF. Install with: pip install gensim") from exc

        self.df = self._prepare_df(df)
        self._build_title_index()

        tokenized = [self._tokenize(text) for text in self.df["text_features"].fillna("").astype(str)]

        self.word2vec_model = Word2Vec(
            sentences=tokenized,
            vector_size=100,
            window=5,
            min_count=1,
            workers=4,
            epochs=10,
        )

        self.book_vectors = np.vstack([self._mean_vector(tokens, 100) for tokens in tokenized])
        self.similarity_matrix = cosine_similarity(self.book_vectors)

    def save(self, path: str) -> None:
        if self.similarity_matrix is None or self.book_vectors is None or self.word2vec_model is None:
            raise RuntimeError("No trained Word2Vec artifacts to save")
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)

        self.word2vec_model.save(str(target / "word2vec.model"))
        np.save(target / "word2vec_vectors.npy", self.book_vectors)
        np.save(target / "word2vec_similarity.npy", self.similarity_matrix)

    def load(self, path: str) -> None:
        try:
            from gensim.models import Word2Vec
        except ImportError as exc:
            raise ImportError("gensim is required for Word2VecCBF. Install with: pip install gensim") from exc

        target = Path(path)
        self.word2vec_model = Word2Vec.load(str(target / "word2vec.model"))
        self.book_vectors = np.load(target / "word2vec_vectors.npy")
        self.similarity_matrix = np.load(target / "word2vec_similarity.npy")


class SentenceEmbeddingCBF(BaseCBF):
    def __init__(self):
        super().__init__(name="sentence")
        self.model_name = "all-MiniLM-L6-v2"
        self.embeddings: Optional[np.ndarray] = None

    def fit(self, df: pd.DataFrame) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for SentenceEmbeddingCBF. Install with: pip install sentence-transformers"
            ) from exc

        self.df = self._prepare_df(df)
        self._build_title_index()

        encoder = SentenceTransformer(self.model_name)
        texts = self.df["text_features"].fillna("").astype(str).tolist()
        self.embeddings = encoder.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        self.similarity_matrix = cosine_similarity(self.embeddings)

    def save(self, path: str) -> None:
        if self.embeddings is None or self.similarity_matrix is None:
            raise RuntimeError("No sentence embedding artifacts to save")
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)

        np.save(target / "sentence_embeddings.npy", self.embeddings)
        np.save(target / "sentence_similarity.npy", self.similarity_matrix)

    def load(self, path: str) -> None:
        target = Path(path)
        self.embeddings = np.load(target / "sentence_embeddings.npy")
        self.similarity_matrix = np.load(target / "sentence_similarity.npy")


def load_all_cbf(data_path: str = "books_processed.csv") -> Dict[str, BaseCBF]:
    data_file = Path(data_path)
    if not data_file.exists():
        raise FileNotFoundError(f"Data file not found: {data_file}")

    df = pd.read_csv(data_file)
    artifacts_dir = data_file.parent

    models: Dict[str, BaseCBF] = {
        "tfidf": TFIDFCosine(),
        "word2vec": Word2VecCBF(),
        "sentence": SentenceEmbeddingCBF(),
    }

    for model in models.values():
        model.df = model._prepare_df(df)
        model._build_title_index()

    tfidf_path = artifacts_dir / "tfidf_similarity.npy"
    if tfidf_path.exists():
        models["tfidf"].load(str(artifacts_dir))
    else:
        models["tfidf"].fit(df)
        models["tfidf"].save(str(artifacts_dir))

    w2v_required = [
        artifacts_dir / "word2vec.model",
        artifacts_dir / "word2vec_vectors.npy",
        artifacts_dir / "word2vec_similarity.npy",
    ]
    if all(path.exists() for path in w2v_required):
        models["word2vec"].load(str(artifacts_dir))
    else:
        models["word2vec"].fit(df)
        models["word2vec"].save(str(artifacts_dir))

    sentence_required = [
        artifacts_dir / "sentence_embeddings.npy",
        artifacts_dir / "sentence_similarity.npy",
    ]
    if all(path.exists() for path in sentence_required):
        models["sentence"].load(str(artifacts_dir))
    else:
        models["sentence"].fit(df)
        models["sentence"].save(str(artifacts_dir))

    return models


def save_fit_times(path: str, fit_times: Dict[str, float]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(fit_times, f, indent=2)


def load_fit_times(path: str) -> Dict[str, float]:
    target = Path(path)
    if not target.exists():
        return {}
    with target.open("r", encoding="utf-8") as f:
        return json.load(f)
