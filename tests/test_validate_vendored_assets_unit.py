from __future__ import annotations

import urllib.request

import pytest

from scripts import validate_vendored_assets


@pytest.mark.parametrize(
    "url",
    [
        "http://registry.npmjs.org/package",
        "file:///etc/passwd",
        "//registry.npmjs.org/package",
        "https:///package",
    ],
)
def test_require_https_url_rejects_non_https_or_non_absolute_urls(url: str) -> None:
    with pytest.raises(ValueError, match="absolute HTTPS URL"):
        validate_vendored_assets._require_https_url(url)


def test_require_https_url_rejects_embedded_credentials() -> None:
    with pytest.raises(ValueError, match="must not contain credentials"):
        validate_vendored_assets._require_https_url(
            "https://username:password@registry.npmjs.org/package"
        )


def test_require_https_url_accepts_registry_and_osv_urls() -> None:
    urls = [
        "https://registry.npmjs.org/@fontsource-variable%2Finter",
        "https://api.osv.dev/v1/query",
    ]

    assert [validate_vendored_assets._require_https_url(url) for url in urls] == urls


def test_https_redirect_handler_rejects_protocol_downgrades() -> None:
    request = urllib.request.Request("https://registry.npmjs.org/package")

    with pytest.raises(ValueError, match="absolute HTTPS URL"):
        validate_vendored_assets._HttpsRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://registry.npmjs.org/package",
        )
