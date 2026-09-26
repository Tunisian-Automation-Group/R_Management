"""The gateway's start-up certificate loads as a server certificate (P-11)."""

from __future__ import annotations

import ssl
import stat

from cappy_common.selfsigned import make


def test_a_fresh_key_and_certificate_a_tls_server_accepts(tmp_path):
    key, cert = make(str(tmp_path / "tls"))
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)  # raises if they do not belong together
    assert stat.S_IMODE(key.stat().st_mode) == 0o600, "the key is readable by the task's user only"
