"""Polite HTTP client: robots.txt, throttling, block detection, single retry."""
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

USER_AGENT = "DaNangInternFinder/1.0 (personal job search; low volume)"
MIN_INTERVAL = 2.0
BLOCK_STATUSES = {401, 403, 429, 451}
CAPTCHA_MARKERS = ("captcha", "g-recaptcha", "cf-challenge", "hcaptcha")
TIMEOUT = 20


class FetchError(Exception):
    """Base class for client errors."""


class RobotsDisallowed(FetchError):
    pass


class BlockedError(FetchError):
    """Host answered 401/403/429/451 or showed a CAPTCHA; stop using it this run."""


class HttpClient:
    def __init__(self, session=None, sleep=time.sleep, clock=time.monotonic):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._sleep = sleep
        self._clock = clock
        self._last_request = {}   # host -> time of last request
        self._robots = {}         # host -> (parser | None for allow-all | False for deny-all)
        self.blocked = {}         # host -> reason

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _origin(url):
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.netloc:
            raise FetchError("only http(s) URLs are allowed")
        return p.scheme, p.netloc

    def _throttle(self, host, extra_delay=0.0):
        wait = max(MIN_INTERVAL, extra_delay)
        last = self._last_request.get(host)
        if last is not None:
            remaining = wait - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _raw_get(self, host, url):
        """One throttled request, with a single retry on timeout/5xx."""
        for attempt in (0, 1):
            self._throttle(host)
            try:
                resp = self.session.get(url, timeout=TIMEOUT)
            except requests.Timeout:
                if attempt == 0:
                    continue
                raise FetchError(f"timeout fetching {host}")
            except requests.RequestException as exc:
                raise FetchError(f"request failed for {host}: {type(exc).__name__}")
            if resp.status_code >= 500 and attempt == 0:
                continue
            return resp

    def _load_robots(self, scheme, host):
        if host in self._robots:
            return self._robots[host]
        resp = self._raw_get(host, f"{scheme}://{host}/robots.txt")
        code = resp.status_code
        if code in (401, 403):
            parser = False                       # treat as disallowed
        elif code == 404 or code == 410:
            parser = None                        # no robots file: allowed
        elif code >= 400:
            parser = False                       # unclear: be conservative
        else:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(resp.text.splitlines())
        self._robots[host] = parser
        return parser

    def _check_robots(self, url):
        scheme, host = self._origin(url)
        parser = self._load_robots(scheme, host)
        if parser is False:
            raise RobotsDisallowed(f"robots.txt disallows {host}")
        if parser is not None and not parser.can_fetch(USER_AGENT, url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        delay = parser.crawl_delay(USER_AGENT) if parser else None
        return host, float(delay or 0)

    def _looks_like_captcha(self, resp):
        ctype = resp.headers.get("Content-Type", "")
        if "html" not in ctype:
            return False
        head = resp.text[:20000].lower()
        return any(m in head for m in CAPTCHA_MARKERS)

    # -- public ------------------------------------------------------------
    def request(self, method, url, **kwargs):
        scheme, host = self._origin(url)
        if host in self.blocked:
            raise BlockedError(f"{host} blocked earlier this run: {self.blocked[host]}")
        host, crawl_delay = self._check_robots(url)
        for attempt in (0, 1):
            self._throttle(host, crawl_delay)
            try:
                resp = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
            except requests.Timeout:
                if attempt == 0:
                    continue
                raise FetchError(f"timeout fetching {host}")
            except requests.RequestException as exc:
                raise FetchError(f"request failed for {host}: {type(exc).__name__}")
            if resp.status_code >= 500 and attempt == 0:
                continue
            break
        if resp.status_code in BLOCK_STATUSES:
            self.blocked[host] = f"HTTP {resp.status_code}"
            raise BlockedError(f"{host} returned HTTP {resp.status_code}")
        if self._looks_like_captcha(resp):
            self.blocked[host] = "CAPTCHA page"
            raise BlockedError(f"{host} showed a CAPTCHA page")
        if resp.status_code >= 400:
            raise FetchError(f"{host} returned HTTP {resp.status_code}")
        return resp

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post_json(self, url, payload, **kwargs):
        return self.request("POST", url, json=payload, **kwargs)
