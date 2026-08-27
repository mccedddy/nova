from unittest.mock import patch

from tools import websearch


def _results(count, snippet_length=100):
    return [
        {
            "title": f"Result {index}",
            "snippet": "x" * snippet_length,
            "url": f"https://example.com/{index}",
        }
        for index in range(count)
    ]


def test_sufficient_first_tier_results_do_not_escalate():
    results = _results(3)

    with patch.object(websearch, "_search_backend", return_value=results) as search:
        result = websearch.web_search("python")

    search.assert_called_once_with("python", "duckduckgo")
    assert result["tier"] == 1
    assert result["escalated"] is False
    assert result["results"] == results
    assert "first_tier_results" not in result


def test_low_quality_first_tier_results_escalate_automatically():
    weak = _results(6, snippet_length=50)
    strong = _results(3, snippet_length=100)

    with patch.object(websearch, "_search_backend", return_value=weak), patch.object(
        websearch, "_ollama_web_search", return_value={"results": strong}
    ) as ollama_search:
        result = websearch.web_search("current release status")

    ollama_search.assert_called_once_with("current release status")
    assert result["backend_used"] == "ollama_web_search"
    assert result["escalated"] is True


def test_conflicting_vulnerability_totals_escalate():
    conflicting = [
        {"title": "A", "snippet": "Analysis reports 398 CVEs fixed this month.", "url": "https://a.example"},
        {"title": "B", "snippet": "Another analysis reports 415 CVEs fixed this month.", "url": "https://b.example"},
        {"title": "C", "snippet": "A third analysis reports 421 vulnerabilities fixed this month.", "url": "https://c.example"},
    ]
    ollama_results = _results(3)

    with patch.object(websearch, "_search_backend", return_value=conflicting), patch.object(
        websearch, "_ollama_web_search", return_value={"results": ollama_results}
    ) as ollama_search:
        result = websearch.web_search("Windows vulnerabilities")

    ollama_search.assert_called_once_with("Windows vulnerabilities")
    assert result["backend_used"] == "ollama_web_search"
    assert result["escalated"] is True


def test_spaced_vulnerability_totals_from_headlines_escalate():
    conflicting = [
        {"title": "A", "snippet": "The update fixes 236 Windows vulnerabilities in this release.", "url": "https://a.example"},
        {"title": "B", "snippet": "The update addresses 440 Exact-Date CVEs across products.", "url": "https://b.example"},
        {"title": "C", "snippet": "Researchers counted 421 CVEs in the August security release.", "url": "https://c.example"},
    ]

    with patch.object(websearch, "_search_backend", return_value=conflicting), patch.object(
        websearch, "_ollama_web_search", return_value={"results": _results(3)}
    ):
        result = websearch.web_search("Windows update vulnerabilities")

    assert result["backend_used"] == "ollama_web_search"
    assert result["escalated"] is True


def test_weak_first_tier_results_escalate_to_second_tier():
    weak = _results(1, snippet_length=10)
    strong = _results(3)

    def fake_search(query, backend):
        return weak

    with patch.object(websearch, "_search_backend", side_effect=fake_search), patch.object(
        websearch, "_ollama_web_search", return_value={"results": strong}
    ) as ollama_search:
        result = websearch.web_search("obscure question")

    assert result["tier"] == 2
    assert result["escalated"] is True
    assert result["backend_used"] == "ollama_web_search"
    assert result["results"] == strong
    assert result["first_tier_results"] == weak
    ollama_search.assert_called_once_with("obscure question")


def test_failed_second_tier_returns_limited_first_tier_results():
    weak = _results(1, snippet_length=10)

    with patch.object(websearch, "_search_backend", return_value=weak), patch.object(
        websearch,
        "_ollama_web_search",
        return_value={"results": [], "error": "OLLAMA_API_KEY is not set"},
    ):
        result = websearch.web_search("limited question")

    assert result["tier"] == 1
    assert result["escalated"] is False
    assert result["backend_used"] == "first_tier_fallback"
    assert result["warning"]
    assert result["results"] == weak


def test_ollama_web_search_normalizes_results_and_uses_api_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{"title": "Title", "url": "https://example.com", "content": "Content"}]}

    with patch.object(websearch.requests, "post", return_value=FakeResponse()) as post:
        result = websearch._ollama_web_search("query")

    post.assert_called_once_with(
        websearch.OLLAMA_WEB_SEARCH_URL,
        headers={"Authorization": "Bearer test-key"},
        json={"query": "query", "max_results": websearch.MAX_RESULTS},
        timeout=websearch.TIMEOUT,
    )
    assert result == {
        "results": [{"title": "Title", "snippet": "Content", "url": "https://example.com"}]
    }


def test_ollama_provider_skips_ddgs(monkeypatch):
    monkeypatch.setenv("NOVA_SEARCH_PROVIDER", "ollama")
    results = _results(3)

    with patch.object(websearch, "_search_backend") as ddgs_search, patch.object(
        websearch, "_ollama_web_search", return_value={"results": results}
    ) as ollama_search:
        result = websearch.web_search("forced query")

    ddgs_search.assert_not_called()
    ollama_search.assert_called_once_with("forced query")
    assert result["backend_used"] == "ollama_web_search"
    assert result["escalated"] is True


def test_backend_failure_continues_to_next_backend():
    strong = _results(3)

    def fake_search(query, backend):
        if backend == "duckduckgo":
            raise RuntimeError("temporary failure")
        return strong

    with patch.object(websearch, "_search_backend", side_effect=fake_search) as search:
        result = websearch.web_search("fallback question")

    assert result["backend_used"] == "bing"
    assert result["tier"] == 1
    assert result["escalated"] is False
    assert search.call_args_list == [
        (("fallback question", "duckduckgo"),),
        (("fallback question", "bing"),),
    ]
