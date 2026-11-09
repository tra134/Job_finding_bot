import pytest
import requests

from finder.http_client import (USER_AGENT, BlockedError, FetchError, HttpClient,
                                RobotsDisallowed)


class FakeResp:
    def __init__(self, status=200, text="", ctype="text/html"):
        self.status_code = status
        self.text = text
        self.headers = {"Content-Type": ctype}


class FakeSession:
    """Maps URL -> response (or list of responses/exceptions, consumed in order)."""

    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.calls = []

    def request(self, method, url, timeout=None, **kw):
        self.calls.append((method, url))
        item = self.routes.get(url, FakeResp(404))
        if isinstance(item, list):
            item = item.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get(self, url, timeout=None, **kw):
        return self.request("GET", url, timeout=timeout, **kw)


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make(routes):
    clock = Clock()
    sess = FakeSession(routes)
    return HttpClient(sess, sleep=clock.sleep, clock=clock.time), sess, clock


ROBOTS = "https://a.test/robots.txt"


def test_user_agent_is_exact():
    client, sess, _ = make({})
    assert sess.headers["User-Agent"] == USER_AGENT
    assert USER_AGENT == "DaNangInternFinder/1.0 (personal job search; low volume)"


def test_robots_disallow_path_blocks_request():
    client, sess, _ = make({
        ROBOTS: FakeResp(200, "User-agent: *\nDisallow: /private\n"),
        "https://a.test/private/x": FakeResp(200, "secret"),
    })
    with pytest.raises(RobotsDisallowed):
        client.get("https://a.test/private/x")
    assert ("GET", "https://a.test/private/x") not in sess.calls


def test_robots_allowed_path_fetches():
    client, _, _ = make({
        ROBOTS: FakeResp(200, "User-agent: *\nDisallow: /private\n"),
        "https://a.test/ok": FakeResp(200, "hello"),
    })
    assert client.get("https://a.test/ok").text == "hello"


@pytest.mark.parametrize("code", [401, 403])
def test_robots_401_403_means_disallowed(code):
    client, sess, _ = make({ROBOTS: FakeResp(code), "https://a.test/ok": FakeResp(200)})
    with pytest.raises(RobotsDisallowed):
        client.get("https://a.test/ok")
    assert ("GET", "https://a.test/ok") not in sess.calls


def test_robots_404_means_allowed():
    client, _, _ = make({ROBOTS: FakeResp(404), "https://a.test/ok": FakeResp(200, "hi")})
    assert client.get("https://a.test/ok").text == "hi"


def test_throttle_two_seconds_between_requests_same_host():
    client, _, clock = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": FakeResp(200),
        "https://a.test/2": FakeResp(200),
    })
    client.get("https://a.test/1")
    client.get("https://a.test/2")
    # robots fetch, page 1, page 2: each must be >= 2s after the previous
    assert len(clock.sleeps) == 2
    assert all(s >= 2.0 - 1e-9 for s in clock.sleeps)


def test_crawl_delay_respected():
    client, _, clock = make({
        ROBOTS: FakeResp(200, "User-agent: *\nCrawl-delay: 5\n"),
        "https://a.test/1": FakeResp(200),
        "https://a.test/2": FakeResp(200),
    })
    client.get("https://a.test/1")
    client.get("https://a.test/2")
    assert max(clock.sleeps) >= 5.0 - 1e-9


@pytest.mark.parametrize("code", [401, 403, 429, 451])
def test_block_status_stops_host_for_run(code):
    client, sess, _ = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": FakeResp(code),
        "https://a.test/2": FakeResp(200),
    })
    with pytest.raises(BlockedError):
        client.get("https://a.test/1")
    with pytest.raises(BlockedError):
        client.get("https://a.test/2")
    assert ("GET", "https://a.test/2") not in sess.calls
    assert "a.test" in client.blocked


def test_block_does_not_affect_other_host():
    client, _, _ = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": FakeResp(403),
        "https://b.test/robots.txt": FakeResp(404),
        "https://b.test/1": FakeResp(200, "ok"),
    })
    with pytest.raises(BlockedError):
        client.get("https://a.test/1")
    assert client.get("https://b.test/1").text == "ok"


def test_captcha_page_is_block():
    client, _, _ = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": FakeResp(200, "<html><div class='g-recaptcha'></div></html>"),
    })
    with pytest.raises(BlockedError):
        client.get("https://a.test/1")
    assert "a.test" in client.blocked


def test_retry_once_on_5xx_then_succeed():
    client, sess, _ = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": [FakeResp(503), FakeResp(200, "ok")],
    })
    assert client.get("https://a.test/1").text == "ok"
    assert sess.calls.count(("GET", "https://a.test/1")) == 2


def test_retry_only_once_on_timeout():
    client, sess, _ = make({
        ROBOTS: FakeResp(404),
        "https://a.test/1": [requests.Timeout(), requests.Timeout(), FakeResp(200)],
    })
    with pytest.raises(FetchError):
        client.get("https://a.test/1")
    assert sess.calls.count(("GET", "https://a.test/1")) == 2


def test_no_retry_on_404():
    client, sess, _ = make({ROBOTS: FakeResp(404), "https://a.test/1": FakeResp(404)})
    with pytest.raises(FetchError):
        client.get("https://a.test/1")
    assert sess.calls.count(("GET", "https://a.test/1")) == 1


def test_non_http_url_rejected():
    client, _, _ = make({})
    with pytest.raises(FetchError):
        client.get("file:///etc/passwd")
