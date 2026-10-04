from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HttpResponse:
    requested_url: str
    response_url: str
    status_code: int
    content_type: str
    body: bytes


class HttpClient(Protocol):
    def get(self, url: str, *, accept: str = "application/json") -> HttpResponse: ...


class UrllibHttpClient:
    def __init__(self, *, timeout: float = 20, user_agent: str = "LotteryIntelligencePlatform/0.1") -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if not user_agent.strip():
            raise ValueError("user_agent cannot be empty")
        self._timeout = timeout
        self._user_agent = user_agent

    def get(self, url: str, *, accept: str = "application/json") -> HttpResponse:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URL must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("credentials must not be embedded in source URLs")
        request = Request(url, headers={"User-Agent": self._user_agent, "Accept": accept})
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return HttpResponse(
                    requested_url=url,
                    response_url=response.geturl(),
                    status_code=response.status,
                    content_type=response.headers.get("Content-Type", "application/octet-stream"),
                    body=response.read(),
                )
        except HTTPError as response:
            return HttpResponse(
                requested_url=url,
                response_url=response.geturl(),
                status_code=response.code,
                content_type=response.headers.get("Content-Type", "application/octet-stream"),
                body=response.read(),
            )
