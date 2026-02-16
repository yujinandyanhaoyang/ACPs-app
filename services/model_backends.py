import hashlib
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple


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


def _resolve_sentence_transformer(model_name: str):
	try:
		from sentence_transformers import SentenceTransformer

		return SentenceTransformer(model_name)
	except Exception:
		return None


def generate_text_embeddings(
	texts: Iterable[str],
	model_name: str,
	fallback_dim: int = 12,
) -> Tuple[List[List[float]], Dict[str, Any]]:
	text_list = [str(text or "") for text in texts]
	if not text_list:
		return [], {"backend": "none", "model": None, "vector_dim": 0}

	model = _resolve_sentence_transformer(model_name)
	if model is not None:
		vectors = model.encode(text_list, normalize_embeddings=True)
		vectors_as_list: List[List[float]] = []
		for row in vectors:
			vectors_as_list.append([round(_to_float(item), 6) for item in row.tolist()])
		dim = len(vectors_as_list[0]) if vectors_as_list else 0
		return vectors_as_list, {"backend": "sentence-transformers", "model": model_name, "vector_dim": dim}

	fallback_vectors = [hash_embedding(text, dim=max(8, fallback_dim)) for text in text_list]
	dim = len(fallback_vectors[0]) if fallback_vectors else 0
	return fallback_vectors, {"backend": "hash-fallback", "model": "sha256", "vector_dim": dim}


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
		return _normalize_scores(fallback_scores), {"backend": "overlap-fallback", "n_components": 0}

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

	return _normalize_scores(raw_scores), {
		"backend": backend,
		"n_components": used_components,
		"history_items": len(history_books),
		"candidate_items": len(indexed_candidates),
	}
