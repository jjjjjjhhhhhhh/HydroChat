import types
import pytest
from apps.hydrochat.http_client import HttpClient, HttpError, metrics

class DummySession:
    def __init__(self, responses):
        self._responses = responses
        self.calls = 0
    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        resp = self._responses[self.calls]
        self.calls += 1
        return resp

class DummyResponse:
    def __init__(self, status_code=200, text='OK', json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}
    def json(self):
        return self._json


def test_retry_then_success(monkeypatch):
    # First returns 502 then 200
    r1 = DummyResponse(status_code=502, text='Bad Gateway')
    r2 = DummyResponse(status_code=200, text='OK', json_data={'id':1})
    client = HttpClient(session=DummySession([r1, r2]))
    before_retries = metrics['retries']
    resp = client.request('GET', '/api/patients/')
    assert resp.status_code == 200
    assert metrics['retries'] == before_retries + 1


def test_non_retry_error():
    r1 = DummyResponse(status_code=400, text='Bad Request')
    client = HttpClient(session=DummySession([r1]))
    with pytest.raises(HttpError) as exc:
        client.request('POST', '/api/patients/', json={'first_name':'A','last_name':'B','nric':'S1234567A'})
    assert 'HTTP 400' in str(exc.value)


def test_masking_in_log(monkeypatch, caplog):
    r1 = DummyResponse(status_code=200, text='OK')
    client = HttpClient(session=DummySession([r1]))
    with caplog.at_level('INFO'):
        client.request('POST', '/api/patients/', json={'nric':'S1234567A'})
    combined = '\n'.join(m.message for m in caplog.records)
    assert 'S******7A' in combined and 'S1234567A' not in combined
