from ddgs import DDGS
import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathlib import Path


load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

MAX_RESULTS = 6
TIMEOUT = 15

FETCH_TIMEOUT = 15
MAX_PAGE_CHARS = 4000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Try backends in order so a transient failure does not abort the search.
BACKENDS = ["duckduckgo", "bing", "google"]
OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"

DEFAULT_LOCATION = "Barangay Highway Hills, Mandaluyong City"


def _search_backend(query, backend):
    with DDGS(timeout=TIMEOUT) as ddgs:
        raw_results = list(ddgs.text(
            query,
            max_results=MAX_RESULTS,
            backend=backend,
        ))

    return [
        {
            "title": r.get("title", "unknown"),
            "snippet": r.get("body", "")[:800],
            "url": r.get("href", "unknown"),
        }
        for r in raw_results
    ]


def _results_are_sufficient(results):
    if len(results) < 3:
        return False

    unique_urls = {
        result.get("url") for result in results if result.get("url") not in {None, "unknown"}
    }
    usable_snippets = [result.get("snippet", "").strip() for result in results]
    sufficiently_detailed = sum(len(snippet) >= 80 for snippet in usable_snippets)
    if len(unique_urls) < 3 or sufficiently_detailed < 3:
        return False

    vulnerability_totals = set()
    for snippet in usable_snippets:
        vulnerability_totals.update(
            int(value)
            for value in re.findall(
                r"\b(\d{2,4})\s+(?:[A-Za-z-]+\s+){0,3}(?:CVEs?|vulnerabilities|flaws)\b",
                snippet,
                re.IGNORECASE,
            )
        )

    return len(vulnerability_totals) <= 1


def _ollama_web_search(query):
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        return {
            "results": [],
            "error": "OLLAMA_API_KEY is not set; Ollama web search was not attempted.",
        }

    response = requests.post(
        OLLAMA_WEB_SEARCH_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "max_results": MAX_RESULTS},
        timeout=TIMEOUT,
    )
    if response.status_code == 401:
        raise requests.HTTPError(
            "Ollama web-search authentication failed (401). Generate a new key at "
            "https://ollama.com/settings/keys and update .env."
        )
    response.raise_for_status()
    payload = response.json()
    results = [
        {
            "title": item.get("title", "unknown"),
            "snippet": item.get("content", "")[:800],
            "url": item.get("url", "unknown"),
        }
        for item in payload.get("results", [])
    ]
    return {"results": results}


def _ollama_response(query):
    try:
        ollama_result = _ollama_web_search(query)
        results = ollama_result["results"]
        if results:
            response = {
                "query": query,
                "backend_used": "ollama_web_search",
                "tier": 2,
                "escalated": True,
                "results": results,
            }
            if not _results_are_sufficient(results):
                response["warning"] = "Search results were limited."
            return response
        return {
            "query": query,
            "backend_used": "ollama_web_search",
            "tier": 2,
            "escalated": True,
            "error": ollama_result.get("error", "Ollama web search returned no results."),
            "results": [],
        }
    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        return {
            "query": query,
            "backend_used": "ollama_web_search",
            "tier": 2,
            "escalated": True,
            "error": f"Ollama web search failed: {e}",
            "results": [],
        }


def web_search(query):
    # Return compact results so web content does not dominate the context.
    provider = os.environ.get("NOVA_SEARCH_PROVIDER", "auto").lower()
    if provider == "ollama":
        return _ollama_response(query)

    last_error = None
    weakest_results = []

    for backend in BACKENDS:
        try:
            results = _search_backend(query, backend)
            if not results:
                continue
            if _results_are_sufficient(results):
                return {
                    "query": query,
                    "backend_used": backend,
                    "tier": 1,
                    "escalated": False,
                    "results": results,
                }
            if len(results) > len(weakest_results):
                weakest_results = results

        except Exception as e:
            last_error = str(e)
            continue

    ollama_result = _ollama_response(query)
    if ollama_result["results"]:
        ollama_result["first_tier_results"] = weakest_results
        return ollama_result
    last_error = ollama_result.get("error")

    if weakest_results:
        return {
            "query": query,
            "backend_used": "first_tier_fallback",
            "tier": 1,
            "escalated": False,
            "results": weakest_results,
            "warning": "Search results were limited or had weak snippets.",
        }

    return {
        "query": query,
        "error": f"All search backends failed. Last error: {last_error}",
        "tier": 2,
        "escalated": True,
        "results": [],
    }

def fetch_page(url, max_chars=8000):
    # Fetch a specific page when a search snippet lacks enough detail.
    try:
        response = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"url": url, "error": f"Failed to fetch page: {e}"}

    try:
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())

    except Exception as e:
        return {"url": url, "error": f"Failed to parse page content: {e}"}

    # Enforce a hard ceiling on content returned to the model.
    max_chars = min(max_chars, 20000)

    truncated = len(text) > max_chars
    text = text[:max_chars]

    return {
        "url": url,
        "content": text,
        "truncated": truncated,
    }

def get_approximate_location():
    # This is the only tool that sends the public IP to an external service.
    try:
        response = requests.get("http://ip-api.com/json/", timeout=8)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "success":
            city = data.get("city", "")
            region = data.get("regionName", "")
            country = data.get("country", "")
            location = ", ".join(part for part in [city, region, country] if part)
            return {"location": location or DEFAULT_LOCATION, "source": "ip_geolocation"}

    except (requests.exceptions.RequestException, ValueError):
        pass

    return {"location": DEFAULT_LOCATION, "source": "default_fallback"}