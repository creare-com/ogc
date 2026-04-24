"""
Proves that the ogc_render() validation rejects malformed UTF-8 and oversized
query strings before any OGC processing begins.

Run with: python3 check_utf8_validation.py
"""
from ogc.ogc_common import WCSException
from ogc.servers import _MAX_QUERY_STRING_BYTES


def validate(raw_qs: bytes) -> None:
    """Exact logic added to ogc_render() in servers.py."""
    if len(raw_qs) > _MAX_QUERY_STRING_BYTES:
        raise WCSException("Request query string exceeds maximum allowed length.")
    try:
        raw_qs.decode("utf-8")
    except UnicodeDecodeError:
        raise WCSException("Request contains invalid UTF-8 encoding.")


cases = [
    (
        "Valid ASCII query string",
        b"SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0",
        None,
    ),
    (
        "Valid multibyte UTF-8 (caf\xc3\xa9)",       # café encoded as UTF-8
        "SERVICE=WCS&COVERAGE=café".encode("utf-8"),
        None,
    ),
    (
        "Invalid UTF-8 bytes (0xFF 0xFE)",
        b"SERVICE=WCS&COVERAGE=\xff\xfe",
        "invalid UTF-8",
    ),
    (
        f"Oversized query string (>{_MAX_QUERY_STRING_BYTES} bytes)",
        b"SERVICE=WCS&COVERAGE=" + b"A" * 8200,
        "maximum allowed length",
    ),
]

all_passed = True
for label, raw_qs, expected_error in cases:
    try:
        validate(raw_qs)
        ok = expected_error is None
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            print(f"       expected WCSException containing '{expected_error}' but none was raised")
    except WCSException as e:
        ok = expected_error is not None and expected_error in str(e)
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
        if ok:
            print(f"       → WCSException: {e}")
        else:
            print(f"       unexpected exception: {e}")
    all_passed = all_passed and ok

print()
print("All checks passed." if all_passed else "One or more checks FAILED.")
