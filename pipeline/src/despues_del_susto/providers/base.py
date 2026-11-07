"""HTTP plumbing shared by the metadata providers."""

import time

import requests


class ProviderError(RuntimeError):
    """A provider call failed in a way the caller cannot fix by retrying."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    params: dict | None = None,
    data: str | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
    retries: int = 3,
) -> object:
    """Request JSON, retrying rate limits and server errors."""
    waits = (1, 2, 4)
    for attempt in range(retries + 1):
        try:
            response = session.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if attempt >= retries:
                raise ProviderError(f"request failed: {exc}") from exc
            time.sleep(waits[min(attempt, len(waits) - 1)])
            continue

        if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            retry_after = response.headers.get("Retry-After", "")
            wait = (
                float(retry_after)
                if retry_after.replace(".", "", 1).isdigit()
                else waits[min(attempt, len(waits) - 1)]
            )
            time.sleep(wait)
            continue

        if response.status_code >= 400:
            raise ProviderError(
                f"{response.status_code} from {url}: {response.text[:200]}",
                status_code=response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                f"invalid JSON from {url}", status_code=response.status_code
            ) from exc

    raise ProviderError("request failed after retries")
