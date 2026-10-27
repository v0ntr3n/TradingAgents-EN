# -*- coding: utf-8 -*-
"""Deliverable file download signature link.

Background: Deliverable download routing (/api/assistant/deliverables/{filename}) originally relied on
JWT Request header/Session Cookie authentication. But the download link in LLM s reply is <a> label,
Direct browser navigation**Does not carry Authorization header** (The front-end JWT is stored in localStorage,
Only XHR/fetch will bring it), after the user clicks 401"Not logged in or your login has expired". 

The fix uses presigned URL mode (same idea as S3 pre-signed download):
- When the tool generates files, it uses the server-side JWT_SECRET derived key pair file name .+Expiration time 
  HMAC-SHA256 Sign, put ?exp=&sig= Attach to download link;
- Download route verification signature: valid and not expired → Release (browser directly clicks on the scene);
  Invalid/missing → Fall back to the original login authentication (the behavior in the direct API call scenario remains unchanged).

The signing key is derived from settings.JWT_SECRET (plus field separators to avoid confusion with JWT usage),
No new configuration items are added; the leakage surface is consistent with JWT and does not introduce additional risks.
"""

import hashlib
import hmac
import time

# Signature validity period: Excel export is an immediate consumption scenario, 24h is enough to review historical sessions and re-download
_SIGNATURE_TTL_HOURS = 24

# Domain Separation: Ensure that the signing key derived from the same key is different from the JWT signing key
_DOMAIN_SEP = b":deliverable-download-v1"


def _signing_key() -> bytes:
    from app.core.config import settings

    return f"{settings.JWT_SECRET}".encode("utf-8") + _DOMAIN_SEP


def _compute_sig(filename: str, exp: int) -> str:
    msg = f"{filename}:{exp}".encode("utf-8")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()[:32]


def sign_deliverable_query(filename: str, ttl_hours: int = _SIGNATURE_TTL_HOURS) -> str:
    """Generate a signature query string for the deliverable file name (exp + sig) , Attached after the download link."""
    exp = int(time.time()) + int(ttl_hours) * 3600
    sig = _compute_sig(filename, exp)
    return f"exp={exp}&sig={sig}"


def verify_deliverable_signature(filename: str, exp, sig) -> bool:
    """Verify signature query parameters: Missing/expired/unmatched are always False."""
    if exp is None or not sig:
        return False
    try:
        exp_int = int(exp)
    except (TypeError, ValueError):
        return False
    if exp_int < int(time.time()):
        return False
    expected = _compute_sig(filename, exp_int)
    return hmac.compare_digest(expected, str(sig))
