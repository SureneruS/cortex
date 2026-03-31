from __future__ import annotations

import struct
from pathlib import Path

MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
ONNX_FILENAME = "onnx/model.onnx"
ONNX_QINT8_ARM64 = "onnx/model_qint8_arm64.onnx"


def serialize_f32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _find_onnx_model() -> tuple[Path, Path] | None:
    """Find cached ONNX model and tokenizer. Returns (onnx_path, tokenizer_path) or None."""
    hub_cache = Path.home() / ".cache/huggingface/hub"
    model_dir = hub_cache / f"models--{MODEL_NAME.replace('/', '--')}"
    if not model_dir.exists():
        return None
    snapshots = model_dir / "snapshots"
    if not snapshots.exists():
        return None
    for snapshot in sorted(snapshots.iterdir(), reverse=True):
        tokenizer_path = snapshot / "tokenizer.json"
        if not tokenizer_path.exists():
            continue
        for onnx_name in (ONNX_QINT8_ARM64, ONNX_FILENAME):
            onnx_path = snapshot / onnx_name
            if onnx_path.exists():
                return onnx_path, tokenizer_path
    return None


class _OnnxBackend:
    """Direct ONNX inference — bypasses sentence-transformers/torch import."""

    def __init__(self, onnx_path: Path, tokenizer_path: Path) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        self._tokenizer.enable_truncation(max_length=384)

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(onnx_path), opts, providers=["CPUExecutionProvider"]
        )
        self._input_names = [i.name for i in self._session.get_inputs()]

    def encode(self, texts: list[str], **_kwargs) -> list[list[float]]:
        import numpy as np

        encoded = self._tokenizer.encode_batch(texts)
        max_len = max(len(e.ids) for e in encoded)

        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
        for i, e in enumerate(encoded):
            input_ids[i, : len(e.ids)] = e.ids
            attention_mask[i, : len(e.ids)] = e.attention_mask

        inputs: dict = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self._input_names:
            inputs["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, inputs)
        token_embeddings = outputs[0]

        # Mean pooling + L2 normalization
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counted = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
        mean_pooled = summed / counted
        norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        normalized = mean_pooled / norms
        return normalized.tolist()


class Embedder:
    _instance: Embedder | None = None

    def __init__(self) -> None:
        self._backend: _OnnxBackend | object | None = None

    @classmethod
    def get(cls) -> Embedder:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def encode(self, text: str) -> list[float]:
        return self.encode_batch([text])[0]

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        backend = self._load_backend()
        if isinstance(backend, _OnnxBackend):
            return backend.encode(texts)
        embeddings = backend.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def _load_backend(self) -> _OnnxBackend | object:
        if self._backend is not None:
            return self._backend

        # Fast path: direct ONNX (~200ms cold start)
        cached = _find_onnx_model()
        if cached is not None:
            try:
                self._backend = _OnnxBackend(*cached)
                return self._backend
            except Exception:
                pass

        # Slow fallback: sentence-transformers + PyTorch
        self._backend = self._load_sentence_transformer()
        return self._backend

    @staticmethod
    def _load_sentence_transformer() -> object:
        import logging
        import os
        import sys
        import warnings

        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        warnings.filterwarnings("ignore")
        logging.disable(logging.WARNING)

        _stderr = sys.stderr
        sys.stderr = open(os.devnull, "w")
        try:
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer("all-mpnet-base-v2", device="cpu")
        finally:
            sys.stderr.close()
            sys.stderr = _stderr
            logging.disable(logging.NOTSET)
