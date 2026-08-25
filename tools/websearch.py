from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

MAX_RESULTS = 8
TIMEOUT = 15

FETCH_TIMEOUT = 15
MAX_PAGE_CHARS = 4000  # trimmed to keep context usage reasonable

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

# try these backends in order -- if one fails (rate limited, network
# hiccup, backend changed something), fall back to the next rather than
# failing the whole search
BACKENDS = ["duckduckgo", "bing", "google"]

DEFAULT_LOCATION = "Barangay Highway Hills, Mandaluyong City"  # fallback if geolocation fails


def web_search(query):
    # real web search, used when the model doesn't recognize something
    # (unfamiliar process/file/error) instead of guessing from training
    # data. Returns summarized (title, snippet, url) tuples, not full
    # page dumps, to avoid blowing the context window.
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
                        "title": result.get("title", "unknown"),
                        "snippet": result.get("body", "")[:800],
                        "url": result.get("href", "unknown"),
                    }
                    for result in raw_results
                ]
                return {"query": query, "backend_used": backend, "results": results}

        except Exception as e:
            last_error = str(e)
            continue  # try the next backend

    return {
        "query": query,
        "error": f"All search backends failed. Last error: {last_error}",
        "results": [],
    }

def fetch_page(url, max_chars=8000):
    # fetches a specific page and extracts its main readable text --
    # use this AFTER web_search when a snippet isn't enough detail and
    # you need the actual article content, not just a preview.
    # max_chars defaults to 8000 (~2000-2600 tokens) to keep context usage
    # reasonable -- raise it only when genuinely needed (e.g. comparing
    # multiple long sources), since large fetches eat context fast.
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

    # hard ceiling regardless of what's requested -- protects against a
    # runaway argument value blowing past the context window entirely
    max_chars = min(max_chars, 20000)

    truncated = len(text) > max_chars
    text = text[:max_chars]

    return {
        "url": url,
        "content": text,
        "truncated": truncated,
    }

def get_approximate_location():
    # uses a free IP-geolocation service to estimate city-level location --
    # not GPS-precise, and this is the one tool in NOVA that sends anything
    # (your public IP, implicitly) to an external service, unlike every
    # other tool which only reads local system state. Falls back to a
    # hardcoded default if the service is unreachable or fails.
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
        pass  # fall through to default below

    return {"location": DEFAULT_LOCATION, "source": "default_fallback"}