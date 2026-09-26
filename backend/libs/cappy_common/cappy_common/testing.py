"""Test helpers: a throwaway token issuer, so unit tests exercise real
signature verification with no identity provider and no network."""

from __future__ import annotations

import json
import time
import uuid
from functools import cached_property

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from .auth import TokenVerifier

TEST_ISSUER = "https://cognito-idp.test.local/test_pool"
TEST_CLIENT = "test-web-client"


class TestIssuer:
    """Mints Cognito-shaped access tokens signed with a key only it holds."""

    __test__ = False  # not a pytest test class

    def __init__(self, issuer: str = TEST_ISSUER, client_id: str = TEST_CLIENT, kid: str = "test-key") -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @cached_property
    def jwks(self) -> dict:
        public = json.loads(RSAAlgorithm.to_jwk(self._key.public_key()))
        return {"keys": [{**public, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def verifier(self) -> TokenVerifier:
        return TokenVerifier(issuer=self.issuer, jwks_url="", client_ids=[self.client_id], jwks=self.jwks)

    def token(self, sub: str, *, ttl: int = 3600, **overrides) -> str:
        now = int(time.time())
        claims = {
            "sub": sub,
            "username": sub,
            "iss": self.issuer,
            "client_id": self.client_id,
            "token_use": "access",
            "scope": "aws.cognito.signin.user.admin",
            "iat": now,
            "exp": now + ttl,
            "jti": uuid.uuid4().hex,
            **overrides,
        }
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": self.kid})

    def headers(self, sub: str, **overrides) -> dict:
        return {"Authorization": f"Bearer {self.token(sub, **overrides)}"}
