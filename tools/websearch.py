from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

MAX_RESULTS = 8 
TIMEOUT = 15

FETCH_TIMEOUT = 15
MAX_PAGE_CHARS = 4000

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Try backends in order so a transient failure does not abort the search.
BACKENDS = ["duckduckgo", "bing", "google"]

DEFAULT_LOCATION = "Barangay Highway Hills, Mandaluyong City"


def web_search(query):
    # Return compact results so web content does not dominate the context.
    last_error = None

    for backend in BACKENDS:
        try:
            with DDGS(timeout=TIMEOUT) as ddgs:
                raw_results = list(ddgs.text(
                    query,
                    max_results=MAX_RESULTS,
                    backend=backend,
                ))

            if raw_results:
                results = [
                    {
                        "title": r.get("title", "unknown"),
                        "snippet": r.get("body", "")[:800],
                        "url": r.get("href", "unknown"),
                    }
                    for r in raw_results
                ]
                return {"query": query, "backend_used": backend, "results": results}

        except Exception as e:
            last_error = str(e)
            continue

    return {
        "query": query,
        "error": f"All search backends failed. Last error: {last_error}",
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