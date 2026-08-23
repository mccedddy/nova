from ddgs import DDGS

MAX_RESULTS = 8 
TIMEOUT = 15

# try these backends in order -- if one fails (rate limited, network
# hiccup, backend changed something), fall back to the next rather than
# failing the whole search
BACKENDS = ["duckduckgo", "bing", "google"]


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
                        "title": r.get("title", "unknown"),
                        "snippet": r.get("body", "")[:800],  # trim long snippets
                        "url": r.get("href", "unknown"),
                    }
                    for r in raw_results
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