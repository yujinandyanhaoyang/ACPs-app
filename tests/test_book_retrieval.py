from pathlib import Path

from scripts.build_books_min_dataset import build_dataset
from services.book_retrieval import (
    detect_query_language,
    load_books,
    retrieve_books_by_query,
    retrieve_books_by_query_with_diagnostics,
    _tokenize_multilingual,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "books_min_sample.jsonl"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "books_min.jsonl"


def test_build_books_min_dataset_generates_output():
    count = build_dataset(RAW_PATH, OUT_PATH)
    assert count >= 24
    assert OUT_PATH.exists()


def test_load_books_returns_non_empty_records():
    build_dataset(RAW_PATH, OUT_PATH)
    books = load_books(OUT_PATH)
    assert books
    assert {"book_id", "title", "author", "description", "genres"}.issubset(books[0].keys())


def test_retrieve_books_by_query_returns_relevant_candidates():
    build_dataset(RAW_PATH, OUT_PATH)
    books = load_books(OUT_PATH)

    sci = retrieve_books_by_query("science fiction space", books, top_k=5)
    hist = retrieve_books_by_query("history civilization", books, top_k=5)

    assert sci
    assert hist
    assert any("science_fiction" in row.get("genres", []) for row in sci)
    assert any("history" in row.get("genres", []) for row in hist)


def test_load_books_prefers_goodreads_default_or_fallback():
    books = load_books()
    assert books
    assert {"book_id", "title", "author", "description", "genres"}.issubset(books[0].keys())


def test_load_books_respects_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom_books.jsonl"
    custom.write_text(
        '{"book_id": "custom_001", "title": "Custom", "author": "A", "description": "B", "genres": ["x"]}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("BOOK_RETRIEVAL_DATASET_PATH", str(custom))
    books = load_books()
    assert len(books) == 1
    assert books[0]["book_id"] == "custom_001"


def test_detect_query_language_for_chinese_and_english():
    zh = detect_query_language("我想看一些陈忠实的乡土文学小说")
    en = detect_query_language("recommend historical fiction books")
    mixed = detect_query_language("推荐 some classic novels")

    assert zh["language"] == "zh"
    assert en["language"] == "en"
    assert mixed["language"] in {"zh", "mixed"}


def test_multilingual_tokenizer_returns_meaningful_chinese_tokens():
    tokens = _tokenize_multilingual("我想看一些陈忠实的乡土文学小说")
    assert len(tokens) >= 5
    assert any("乡土" in tok or "文学" in tok for tok in tokens)


def test_chinese_tokenization_gate_coverage():
    samples = [
        "我想看一些陈忠实的乡土文学小说",
        "推荐中国基层治理发展报告相关书籍",
        "我喜欢温暖治愈的儿童童话",
        "推荐悬疑恐怖推理小说",
        "想看中国近代史与社会变迁类作品",
        "我想找女性成长主题的现实主义小说",
        "推荐讲乡村教育与基层治理的纪实作品",
        "想看科技创新与产业政策相关报告",
        "我想读民国时期家族叙事文学",
        "推荐适合中学生阅读的科普书",
    ]
    passed = 0
    for query in samples:
        if len(_tokenize_multilingual(query, lang_hint="zh")) >= 5:
            passed += 1
    ratio = passed / len(samples)
    assert ratio >= 0.9


def test_language_detection_accuracy_gate():
    labeled = [
        ("我想看中国乡土文学", "zh"),
        ("推荐基层治理报告", "zh"),
        ("儿童快乐童话故事", "zh"),
        ("历史与社会发展书籍", "zh"),
        ("悬疑恐怖小说推荐", "zh"),
        ("recommend science fiction books", "en"),
        ("need books on governance policy", "en"),
        ("happy fairy tales for kids", "en"),
        ("historical literature and family saga", "en"),
        ("thriller and suspense novels", "en"),
        ("推荐 some classic novels", "mixed"),
        ("中国 policy report", "mixed"),
    ]

    correct = 0
    for query, expected in labeled:
        predicted = detect_query_language(query)["language"]
        if expected == "mixed":
            if predicted in {"mixed", "zh"}:
                correct += 1
        elif predicted == expected:
            correct += 1

    accuracy = correct / len(labeled)
    assert accuracy >= 0.95


def test_retrieve_books_by_query_prefers_language_when_available():
    books = [
        {
            "book_id": "zh_001",
            "title": "乡土中国",
            "author": "费孝通",
            "description": "中国乡土社会结构与治理分析",
            "genres": ["社会", "治理"],
            "language": "zh",
        },
        {
            "book_id": "en_001",
            "title": "Fantasy World",
            "author": "A Writer",
            "description": "Magic academy and dragons",
            "genres": ["fantasy"],
            "language": "en",
        },
    ]
    result = retrieve_books_by_query("中国基层治理发展报告", books=books, top_k=1)
    assert result
    assert result[0]["book_id"] == "zh_001"


def test_dual_corpus_soft_mode_uses_fallback_when_primary_weak():
    en_books = [
        {
            "book_id": "en_horror_1",
            "title": "Dark Suspense Night",
            "author": "A",
            "description": "horror suspense thriller novel with mystery",
            "genres": ["horror", "thriller"],
            "language": "en",
        }
    ]
    zh_books = [
        {
            "book_id": "zh_other_1",
            "title": "中国乡土观察",
            "author": "B",
            "description": "乡土社会研究",
            "genres": ["社会"],
            "language": "zh",
        }
    ]

    result, diag = retrieve_books_by_query_with_diagnostics(
        query="I like horror suspense novels",
        top_k=3,
        route_mode="soft",
        min_primary_hits=2,
        books_en=en_books,
        books_zh=zh_books,
    )

    assert result
    assert diag["routing_mode"] == "soft"
    assert diag["primary_corpus"] == "en"
    assert diag["fallback_used"] is True
    assert "fusion_component_avgs" in diag


def test_dual_corpus_strict_mode_blocks_secondary_fallback():
    en_books = [
        {
            "book_id": "en_only_1",
            "title": "History of Rome",
            "author": "A",
            "description": "ancient empire history",
            "genres": ["history"],
            "language": "en",
        }
    ]
    zh_books = [
        {
            "book_id": "zh_horror_1",
            "title": "恐怖悬疑故事",
            "author": "B",
            "description": "悬疑 恐怖 推理",
            "genres": ["悬疑", "恐怖"],
            "language": "zh",
        }
    ]

    result, diag = retrieve_books_by_query_with_diagnostics(
        query="I like horror suspense novels",
        top_k=3,
        route_mode="strict",
        min_primary_hits=3,
        books_en=en_books,
        books_zh=zh_books,
    )

    assert diag["routing_mode"] == "strict"
    assert diag["primary_corpus"] == "en"
    assert diag["fallback_used"] is False
    if result:
        assert all(str(item.get("language") or "").lower().startswith("en") for item in result)


def test_opposite_intent_chinese_queries_have_low_overlap():
    books_zh = [
        {
            "book_id": "zh_horror_1",
            "title": "黑夜悬疑档案",
            "author": "A",
            "description": "恐怖 悬疑 推理 黑暗 氛围",
            "genres": ["悬疑", "恐怖"],
            "language": "zh",
            "canonical_work_id": "cw_horror_1",
        },
        {
            "book_id": "zh_horror_2",
            "title": "午夜凶案",
            "author": "B",
            "description": "惊悚 侦探 小说",
            "genres": ["悬疑", "惊悚"],
            "language": "zh",
            "canonical_work_id": "cw_horror_2",
        },
        {
            "book_id": "zh_fairy_1",
            "title": "阳光童话屋",
            "author": "C",
            "description": "快乐 儿童 童话 治愈 温暖",
            "genres": ["儿童", "童话"],
            "language": "zh",
            "canonical_work_id": "cw_fairy_1",
        },
        {
            "book_id": "zh_fairy_2",
            "title": "彩虹故事集",
            "author": "D",
            "description": "欢乐 成长 寓言",
            "genres": ["儿童", "寓言"],
            "language": "zh",
            "canonical_work_id": "cw_fairy_2",
        },
    ]

    horror_result, _ = retrieve_books_by_query_with_diagnostics(
        query="我喜欢恐怖悬疑小说",
        top_k=3,
        route_mode="strict",
        books_en=[],
        books_zh=books_zh,
    )
    fairy_result, _ = retrieve_books_by_query_with_diagnostics(
        query="我喜欢快乐温暖的儿童童话",
        top_k=3,
        route_mode="strict",
        books_en=[],
        books_zh=books_zh,
    )

    horror_ids = {str(row.get("book_id")) for row in horror_result}
    fairy_ids = {str(row.get("book_id")) for row in fairy_result}
    union_ids = horror_ids | fairy_ids
    overlap = horror_ids & fairy_ids
    jaccard = (len(overlap) / len(union_ids)) if union_ids else 0.0
    assert jaccard <= 0.5


def test_dedup_in_topk_by_canonical_work_id():
    books = [
        {
            "book_id": "zh_edition_1",
            "title": "三体",
            "author": "刘慈欣",
            "description": "科幻 文明 危机",
            "genres": ["科幻"],
            "language": "zh",
            "canonical_work_id": "cw_three_body",
        },
        {
            "book_id": "en_edition_1",
            "title": "The Three-Body Problem",
            "author": "Liu Cixin",
            "description": "science fiction civilization crisis",
            "genres": ["science_fiction"],
            "language": "en",
            "canonical_work_id": "cw_three_body",
        },
        {
            "book_id": "other_1",
            "title": "Foundation",
            "author": "Isaac Asimov",
            "description": "science fiction empire future",
            "genres": ["science_fiction"],
            "language": "en",
            "canonical_work_id": "cw_foundation",
        },
    ]

    result = retrieve_books_by_query("recommend science fiction civilization books", books=books, top_k=3)
    canonical = [str(row.get("canonical_work_id") or "") for row in result if str(row.get("canonical_work_id") or "")]
    assert len(canonical) == len(set(canonical))
