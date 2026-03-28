from __future__ import annotations

import struct


def serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


class Embedder:
    _instance: Embedder | None = None

    def __init__(self) -> None:
        self._model = None

    @classmethod
    def get(cls) -> Embedder:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, text: str) -> list[float]:
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def _load_model(self):
        if self._model is None:
            import logging
            import os
            import warnings

            os.environ["TOKENIZERS_PARALLELISM"] = "false"
            os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
            warnings.filterwarnings("ignore")
            logging.disable(logging.WARNING)

            import sys
            _stderr = sys.stderr
            sys.stderr = open(os.devnull, "w")
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer("all-mpnet-base-v2", device="cpu")
            finally:
                sys.stderr.close()
                sys.stderr = _stderr
                logging.disable(logging.NOTSET)
        return self._model
