import os
import logging
import requests
import urllib.parse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def scrape_duckduckgo(query: str, max_results: int = 5) -> list[dict]:
    """
    Scrapes DuckDuckGo HTML search results for a given query.
    No API key required.
    """
    logger.info(f"Scraping DuckDuckGo HTML search results for: '{query}'")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    encoded_query = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    try:
        response = requests.get(url, headers=headers, timeout=6)
        if response.status_code != 200:
            logger.warning(f"DuckDuckGo HTML returned status code {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        
        # DuckDuckGo HTML layout uses 'result__body' class wrapper for each search result
        elements = soup.find_all("div", class_="result__body")
        for el in elements:
            if len(results) >= max_results:
                break
                
            title_el = el.find("a", class_="result__a")
            snippet_el = el.find("a", class_="result__snippet")
            
            if title_el:
                title = title_el.get_text(strip=True)
                raw_url = title_el.get("href", "")
                
                # Extract URL from DuckDuckGo redirect structure if present:
                # e.g., //duckduckgo.com/l/?uddg=https%3A%2F%2F...
                final_url = raw_url
                if "uddg=" in raw_url:
                    try:
                        parsed = urllib.parse.urlparse(raw_url)
                        query_params = urllib.parse.parse_qs(parsed.query)
                        if "uddg" in query_params:
                            final_url = query_params["uddg"][0]
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse redirect URL: {raw_url}, error: {parse_err}")
                
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                
                # Don't add empty results or internal duckduckgo links
                if title and final_url and not final_url.startswith("//duckduckgo.com"):
                    results.append({
                        "title": title,
                        "url": final_url,
                        "snippet": snippet
                    })
                    
        return results
    except Exception as e:
        logger.error(f"DuckDuckGo scraping search failed: {e}")
        return []

def google_custom_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Queries Google Custom Search API if credentials are provided in env.
    """
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cx_id = os.getenv("GOOGLE_SEARCH_CX_ID")
    
    if not api_key or not cx_id:
        return []
        
    logger.info(f"Querying Google Custom Search API for: '{query}'")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx_id,
        "q": query,
        "num": max_results
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            results = []
            for item in items:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", "")
                })
            return results
        else:
            logger.warning(f"Google Search API failed with status {response.status_code}: {response.text}")
            return []
    except Exception as e:
        logger.error(f"Google Custom Search API query error: {e}")
        return []

def search_internet(query: str, max_results: int = 5) -> list[dict]:
    """
    Gateway function for internet searches.
    Attempts Google API first (if config exists), then falls back to DuckDuckGo scraping.
    """
    # 1. Try Google Custom Search API
    results = google_custom_search(query, max_results)
    if results:
        return results
        
    # 2. Fallback to DuckDuckGo HTML scraping
    return scrape_duckduckgo(query, max_results)
