# src/utils_http.py
import os
import time
import urllib.robotparser as robotparser
from urllib.parse import urlparse
import requests
from dotenv import load_dotenv

load_dotenv()

UA = os.getenv("HTTP_UA", "Mozilla/5.0 (compatible; Capstone/1.0)")
SLEEP = float(os.getenv("RATE_SLEEP", "1.0"))   # seconds between requests
TIMEOUT = int(os.getenv("TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

def session():
    """Return a configured requests.Session with headers set."""
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    return s

def can_fetch(url: str) -> bool:
    """Respect robots.txt for a given URL's host."""
    parsed = urlparse(url)
    robots = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = robotparser.RobotFileParser()
    try:
        rp.set_url(robots)
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        # If robots.txt cannot be read, default to True (be gentle with rate limiting)
        return True

def polite_get(s: requests.Session, url: str, **kw) -> requests.Response:
    """GET with retry + simple rate limiting."""
    for _ in range(MAX_RETRIES):
        time.sleep(SLEEP)
        r = s.get(url, timeout=TIMEOUT, **kw)
        if r.status_code == 200:
            return r
    r.raise_for_status()

def take_limit(items, limit: int | None):
    """Return first N items if limit is set, else all."""
    if limit is None:
        return items
    return items[:max(0, int(limit))]
