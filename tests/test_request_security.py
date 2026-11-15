import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app


def make_request(headers):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/activity",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "query_string": b"",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )


def test_local_request_rejects_foreign_origin():
    request = make_request({"host": "127.0.0.1:8000", "origin": "https://evil.example"})
    with pytest.raises(HTTPException) as error:
        app._check_local_request(request)
    assert error.value.status_code == 403


def test_local_request_accepts_browser_same_origin_get_without_origin():
    request = make_request({"host": "127.0.0.1:8000", "sec-fetch-site": "same-origin"})
    app._check_local_request(request)
