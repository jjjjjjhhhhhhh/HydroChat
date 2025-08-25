from __future__ import annotations
import logging
import time
from typing import Any, Dict, Optional
import requests
from requests import Response, Session
from .config import load_config
from .utils import mask_nric

logger = logging.getLogger(__name__)

# Metrics container (simple in‑memory counters per process)
metrics: Dict[str, int] = {
    'total_api_calls': 0,
    'retries': 0,
    'successful_ops': 0,
    'aborted_ops': 0,
}

_RETRY_STATUS = {502, 503, 504}
_BACKOFF_S = [0.5, 1.0]  # two retries max

class HttpError(Exception):
    def __init__(self, response: Response):
        self.response = response
        super().__init__(f"HTTP {response.status_code}: {response.text[:200]}")

class HttpClient:
    def __init__(self, session: Optional[Session] = None):
        self.session = session or requests.Session()
        self.config = load_config()

    def _build_url(self, path: str) -> str:
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return f"{self.config.base_url}{path if path.startswith('/') else '/' + path}"

    def request(self, method: str, path: str, *, json: Any | None = None, params: dict | None = None, headers: dict | None = None, timeout: float | None = None) -> Response:
        method_up = method.upper()
        url = self._build_url(path)
        timeout = timeout or self.config.timeout_s
        hdrs = headers.copy() if headers else {}
        if self.config.auth_token:
            hdrs.setdefault('Authorization', f"Bearer {self.config.auth_token}")
        attempt = 0
        max_attempts = 1 + len(_BACKOFF_S)  # 3 total attempts (initial + 2 retries)
        last_exc: Optional[Exception] = None
        response: Optional[Response] = None
        # Determine if method is retry eligible
        while attempt < max_attempts:
            attempt += 1
            metrics['total_api_calls'] += 1
            try:
                response = self.session.request(method_up, url, json=json, params=params, headers=hdrs, timeout=timeout)
                # Decide if we retry based on status
                if response.status_code in _RETRY_STATUS and attempt < max_attempts:
                    metrics['retries'] += 1
                    self._log('RETRY', method_up, url, attempt, f"retrying status {response.status_code}")
                    time.sleep(_BACKOFF_S[attempt - 1])  # attempt-1 indexes backoff
                    continue
                break  # success path or non-retryable status
            except (requests.ConnectionError, requests.Timeout) as exc:  # network level
                last_exc = exc
                # POST retry only if no response obtained (network failure) per spec
                if attempt < max_attempts and (method_up != 'POST' or response is None):
                    metrics['retries'] += 1
                    self._log('RETRY', method_up, url, attempt, f"network error: {exc}")
                    time.sleep(_BACKOFF_S[attempt - 1])
                    continue
                break
        # After loop evaluate outcome
        if response is None:
            metrics['aborted_ops'] += 1
            raise last_exc or RuntimeError('Request failed without response')
        if 200 <= response.status_code < 300:
            metrics['successful_ops'] += 1
            self._log('SUCCESS', method_up, url, attempt, self._summarize_body_for_log(json))
            return response
        # Non-success
        self._log('ERROR', method_up, url, attempt, f"status={response.status_code}")
        raise HttpError(response)

    def _summarize_body_for_log(self, body: Any | None) -> str:
        if body is None:
            return 'no-body'
        try:
            if isinstance(body, dict):
                redacted = {}
                for k, v in body.items():
                    if 'nric' in k.lower() and isinstance(v, str):
                        redacted[k] = mask_nric(v)
                    else:
                        redacted[k] = v
                return str(redacted)
            return str(body)[:200]
        except Exception:  # pragma: no cover
            return 'unloggable-body'

    def _log(self, category: str, method: str, url: str, attempt: int, msg: str):
        # Ensure we never leak full token
        safe_url = url
        logger.info('[🤖HydroChat][%s] %s %s attempt=%s %s', category, method, safe_url, attempt, msg)

# Convenience singleton
client = HttpClient()

__all__ = ['HttpClient', 'client', 'HttpError', 'metrics']
