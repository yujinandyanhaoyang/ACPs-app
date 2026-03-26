import hashlib
import math
import os
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from services.data_paths import get_processed_data_path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CF_ITEM_FACTORS_PATH = get_processed_data_path("cf_item_factors.npy")
_DEFAULT_CF_BOOK_INDEX_PATH = get_processed_data_path("cf_book_id_index.json")
_CF_ITEM_VECTORS_CACHE: Dict[str, List[float]] | None = None
_SENTENCE_MODEL_CACHE: Dict[str, Any] = {}
_DEFAULT_OFFLINE_EMBED_MODEL = "all-MiniLM-L6-v2"
_LOCAL_EMBED_MODEL_ENV = "BOOK_CONTENT_EMBED_MODEL_PATH"
_LOGGER = logging.getLogger("services.model_backends")


def hash_embedding(text: str, dim: int = 12) -> List[float]:
	normalized = (text or "").strip().lower()
	if not normalized:
		return [0.0] * max(dim, 4)

	digest = hashlib.sha256(normalized.encode("utf-8")).digest()
	values: List[float] = []
	while len(values) < dim:
		for byte_value in digest:
			values.append(round(byte_value / 255.0, 6))
			if len(values) >= dim:
				break
		digest = hashlib.sha256(digest).digest()
	return values


def _to_float(value: Any, default: float = 0.0) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return default


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
	size = min(len(left), len(right))
	if size <= 0:
		return 0.0
	dot = sum(left[index] * right[index] for index in range(size))
	left_norm = math.sqrt(sum(left[index] ** 2 for index in range(size)))
	right_norm = math.sqrt(sum(right[index] ** 2 for index in range(size)))
	if left_norm == 0.0 or right_norm == 0.0:
		return 0.0
	return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _normalize_scores(raw_scores: Dict[str, float]) -> Dict[str, float]:
	if not raw_scores:
		return {}
	values = list(raw_scores.values())
	minimum = min(values)
	maximum = max(values)
	span = maximum - minimum
	if span <= 0:
		return {key: 0.5 for key in raw_scores}
	return {key: round((value - minimum) / span, 6) for key, value in raw_scores.items()}


def _resolve_cf_artifact_paths() -> Tuple[Path, Path]:
	item_path = Path(os.getenv("CF_ITEM_FACTORS_PATH") or _DEFAULT_CF_ITEM_FACTORS_PATH)
	index_path = Path(os.getenv("CF_BOOK_INDEX_PATH") or _DEFAULT_CF_BOOK_INDEX_PATH)
	return item_path, index_path


def load_cf_item_vectors(force_reload: bool = False) -> Dict[str, List[float]]:
	global _CF_ITEM_VECTORS_CACHE
	if _CF_ITEM_VECTORS_CACHE is not None and not force_reload:
		return _CF_ITEM_VECTORS_CACHE

	item_path, index_path = _resolve_cf_artifact_paths()
	if not item_path.exists() or not index_path.exists():
		_CF_ITEM_VECTORS_CACHE = {}
		return _CF_ITEM_VECTORS_CACHE

	try:
		import numpy as np

		with index_path.open("r", encoding="utf-8") as f:
			book_to_idx = json.load(f)
		if not isinstance(book_to_idx, dict):
			_CF_ITEM_VECTORS_CACHE = {}
			return _CF_ITEM_VECTORS_CACHE

		item_factors = np.load(item_path, allow_pickle=False)
		if len(getattr(item_factors, "shape", ())) != 2:
			_CF_ITEM_VECTORS_CACHE = {}
			return _CF_ITEM_VECTORS_CACHE

		row_count = int(item_factors.shape[0])
		vectors: Dict[str, List[float]] = {}
		for book_id, idx in book_to_idx.items():
			try:
				row_idx = int(idx)
			except (TypeError, ValueError):
				continue
			if row_idx < 0 or row_idx >= row_count:
				continue
			vectors[str(book_id)] = [round(_to_float(v), 6) for v in item_factors[row_idx].tolist()]

		_CF_ITEM_VECTORS_CACHE = vectors
		return _CF_ITEM_VECTORS_CACHE
	except Exception:
		_CF_ITEM_VECTORS_CACHE = {}
		return _CF_ITEM_VECTORS_CACHE


def _resolve_embedding_model_name(model_name: str) -> str:
        configured_path = str(os.getenv(_LOCAL_EMBED_MODEL_ENV) or "").strip()
        if configured_path:
                local_path = Path(configured_path).expanduser()
                if local_path.exists():
                        return str(local_path)
                _LOGGER.info(
                        "event=local_embed_model_missing path=%s fallback=remote-hf",
                        configured_path,
                )
        return str(model_name or "").strip() or _DEFAULT_OFFLINE_EMBED_MODEL


def _resolve_sentence_transformer(model_name: str):
	cached = _SENTENCE_MODEL_CACHE.get(model_name)
	if cached is not None:
		return cached
	try:
		from sentence_transformers import SentenceTransformer

		model = SentenceTransformer(model_name)
		_SENTENCE_MODEL_CACHE[model_name] = model
		return model
	except Exception as exc:
		_LOGGER.warning(
			"event=sentence_transformer_load_failed model=%s fallback=hash-fallback error=%s",
			model_name,
			exc,
		)
		return None


def generate_text_embeddings(
	texts: Iterable[str],
	model_name: str,
	fallback_dim: int = 12,
) -> Tuple[List[List[float]], Dict[str, Any]]:
	text_list = [str(text or "") for text in texts]
	if not text_list:
		return [], {"backend": "none", "model": None, "vector_dim": 0}

	effective_model = _resolve_embedding_model_name(model_name)
	model = _resolve_sentence_transformer(effective_model)
	if model is not None:
		vectors = model.encode(text_list, normalize_embeddings=True)
		vectors_as_list: List[List[float]] = []
		for row in vectors:
			vectors_as_list.append([round(_to_float(item), 6) for item in row.tolist()])
		dim = len(vectors_as_list[0]) if vectors_as_list else 0
		return vectors_as_list, {"backend": "sentence-transformers", "model": effective_model, "vector_dim": dim}

	fallback_vectors = [hash_embedding(text, dim=max(8, fallback_dim)) for text in text_list]
	dim = len(fallback_vectors[0]) if fallback_vectors else 0
	return fallback_vectors, {"backend": "hash-fallback", "model": "sha256", "vector_dim": dim}


async def _resolve_dashscope_embeddings(
	texts: List[str],
	model_name: str,
	base_url: str,
	api_key: str,
) -> Tuple[List[List[float]], Dict[str, Any]]:
	try:
		import openai  # type: ignore
		client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
		response = await client.embeddings.create(model=model_name, input=texts)
		embeddings: List[List[float]] = []
		for row in response.data or []:
			vector = getattr(row, "embedding", None)
			if isinstance(vector, list):
				embeddings.append([round(_to_float(item), 6) for item in vector])
		dim = len(embeddings[0]) if embeddings else 0
		return embeddings, {"backend": "dashscope", "model": model_name, "vector_dim": dim}
	except Exception:
		return [], {"backend": "dashscope", "model": model_name, "vector_dim": 0}


async def generate_text_embeddings_async(
	texts: Iterable[str],
	model_name: str,
	fallback_dim: int = 12,
) -> Tuple[List[List[float]], Dict[str, Any]]:
	text_list = [str(text or "") for text in texts]
	if not text_list:
		return [], {"backend": "none", "model": None, "vector_dim": 0}

	api_key = os.getenv("OPENAI_API_KEY") or ""
	base_url = os.getenv("OPENAI_BASE_URL") or ""
	if api_key and base_url:
		vectors, meta = await _resolve_dashscope_embeddings(text_list, model_name, base_url, api_key)
		if vectors:
			return vectors, meta

	effective_model = str(model_name or "").strip()
	if not (api_key and base_url):
		remote_like_model = (
			effective_model.startswith("text-embedding")
			or effective_model.startswith("qwen")
		)
		if remote_like_model:
			_LOGGER.info(
				"event=offline_model_switch from_model=%s to_model=%s reason=offline_no_api",
				effective_model,
				_DEFAULT_OFFLINE_EMBED_MODEL,
			)
			effective_model = _DEFAULT_OFFLINE_EMBED_MODEL

	return generate_text_embeddings(text_list, model_name=effective_model, fallback_dim=fallback_dim)


def _token_features(book: Dict[str, Any]) -> List[str]:
	features: List[str] = []
	for key in ["genres", "themes", "tags"]:
		values = book.get(key) or []
		if not isinstance(values, list):
			continue
		for value in values:
			token = str(value or "").strip().lower()
			if token:
				features.append(token)
	difficulty = str(book.get("difficulty") or "").strip().lower()
	if difficulty:
		features.append(f"difficulty:{difficulty}")
	return features


def _book_identifier(book: Dict[str, Any], default_value: str) -> str:
	return str(book.get("book_id") or book.get("id") or book.get("title") or default_value)


def _estimate_overlap_raw_scores(
	history_books: List[Dict[str, Any]],
	indexed_candidates: List[Dict[str, Any]],
	n_components: int,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
	if not indexed_candidates:
		return {}, {"backend": "none", "n_components": 0}

	corpus = history_books + indexed_candidates
	vocabulary: Dict[str, int] = {}
	for book in corpus:
		for token in _token_features(book):
			if token not in vocabulary:
				vocabulary[token] = len(vocabulary)

	if not vocabulary:
		fallback_scores: Dict[str, float] = {}
		for index, candidate in enumerate(indexed_candidates):
			fallback_scores[candidate["book_id"]] = round(0.5 + (index * 0.01), 6)
		return fallback_scores, {"backend": "overlap-fallback", "n_components": 0}

	matrix: List[List[float]] = []
	for book in corpus:
		row = [0.0] * len(vocabulary)
		feature_counts = defaultdict(float)
		for token in _token_features(book):
			feature_counts[token] += 1.0
		for token, count in feature_counts.items():
			row[vocabulary[token]] = count
		matrix.append(row)

	latent_vectors: List[List[float]]
	backend = "overlap-fallback"
	used_components = 0
	try:
		from sklearn.decomposition import TruncatedSVD

		max_components = min(max(2, n_components), max(2, len(vocabulary) - 1), max(2, len(matrix) - 1))
		svd = TruncatedSVD(n_components=max_components, random_state=42)
		transformed = svd.fit_transform(matrix)
		latent_vectors = [row.tolist() for row in transformed]
		backend = "sklearn-truncated-svd"
		used_components = max_components
	except Exception:
		latent_vectors = matrix

	history_count = len(history_books)
	history_vectors = latent_vectors[:history_count] if history_count > 0 else []
	candidate_vectors = latent_vectors[history_count:]

	if history_vectors:
		weighted_user_vector = [0.0] * len(history_vectors[0])
		total_weight = 0.0
		for index, vector in enumerate(history_vectors):
			rating = _to_float(history_books[index].get("rating"), 3.0)
			weight = max(0.1, rating / 5.0)
			total_weight += weight
			for dim_index, value in enumerate(vector):
				weighted_user_vector[dim_index] += value * weight
		if total_weight > 0:
			weighted_user_vector = [value / total_weight for value in weighted_user_vector]
	else:
		weighted_user_vector = [0.5] * len(candidate_vectors[0]) if candidate_vectors else [0.5]

	raw_scores: Dict[str, float] = {}
	for index, candidate in enumerate(indexed_candidates):
		vector = candidate_vectors[index] if index < len(candidate_vectors) else [0.0]
		raw_scores[candidate["book_id"]] = _cosine_similarity(vector, weighted_user_vector)

	return raw_scores, {
		"backend": backend,
		"n_components": used_components,
	}


def estimate_collaborative_scores_with_svd(
	history: List[Dict[str, Any]],
	candidates: List[Dict[str, Any]],
	n_components: int = 8,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
	if not candidates:
		return {}, {"backend": "none", "n_components": 0}

	history_books: List[Dict[str, Any]] = []
	for index, row in enumerate(history):
		if not isinstance(row, dict):
			continue
		history_books.append(
			{
				"book_id": _book_identifier(row, f"history_{index}"),
				"genres": row.get("genres") or [],
				"themes": row.get("themes") or [],
				"difficulty": row.get("difficulty"),
				"rating": _to_float(row.get("rating"), 3.0),
			}
		)

	indexed_candidates: List[Dict[str, Any]] = []
	for index, row in enumerate(candidates):
		if not isinstance(row, dict):
			continue
		indexed_candidates.append(
			{
				**row,
				"book_id": _book_identifier(row, f"candidate_{index}"),
			}
		)

	pretrained_vectors = load_cf_item_vectors()
	raw_scores: Dict[str, float] = {}
	covered_candidate_ids: set[str] = set()
	used_components = 0

	if pretrained_vectors:
		history_vectors: List[Tuple[List[float], float]] = []
		for hrow in history_books:
			vector = pretrained_vectors.get(str(hrow.get("book_id") or ""))
			if not vector:
				continue
			rating = _to_float(hrow.get("rating"), 3.0)
			history_vectors.append((vector, max(0.1, rating / 5.0)))

		if history_vectors:
			vector_dim = len(history_vectors[0][0])
			weighted_user_vector = [0.0] * vector_dim
			total_weight = 0.0
			for vector, weight in history_vectors:
				total_weight += weight
				for dim_index, value in enumerate(vector[:vector_dim]):
					weighted_user_vector[dim_index] += _to_float(value) * weight
			if total_weight > 0:
				weighted_user_vector = [value / total_weight for value in weighted_user_vector]

			for candidate in indexed_candidates:
				candidate_id = candidate["book_id"]
				candidate_vector = pretrained_vectors.get(candidate_id)
				if not candidate_vector:
					continue
				raw_scores[candidate_id] = _cosine_similarity(candidate_vector, weighted_user_vector)
				covered_candidate_ids.add(candidate_id)
			used_components = vector_dim

	missing_candidates = [c for c in indexed_candidates if c["book_id"] not in covered_candidate_ids]
	if missing_candidates:
		fallback_scores, fallback_meta = _estimate_overlap_raw_scores(history_books, missing_candidates, n_components)
		raw_scores.update(fallback_scores)
		if covered_candidate_ids:
			backend = "pretrained-svd+overlap-fallback"
		else:
			backend = str(fallback_meta.get("backend") or "overlap-fallback")
		used_components = max(used_components, int(fallback_meta.get("n_components") or 0))
	else:
		backend = "pretrained-svd" if covered_candidate_ids else "none"

	if not raw_scores:
		fallback_scores, fallback_meta = _estimate_overlap_raw_scores(history_books, indexed_candidates, n_components)
		raw_scores = fallback_scores
		backend = str(fallback_meta.get("backend") or "overlap-fallback")
		used_components = int(fallback_meta.get("n_components") or 0)

	return _normalize_scores(raw_scores), {
		"backend": backend,
		"n_components": used_components,
		"history_items": len(history_books),
		"candidate_items": len(indexed_candidates),
		"pretrained_candidate_coverage": round(len(covered_candidate_ids) / max(1, len(indexed_candidates)), 4),
	}
