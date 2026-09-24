from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from accounts.clients import CatalogClient
from accounts.main import build_app
from accounts.security import hash_password, verify_password
from accounts.settings import Settings
from cappy_common.errors import Invalid
from cappy_common.models import Owner


class FakeCatalog(CatalogClient):
    def __init__(self) -> None:
        self.owners: dict[str, Owner] = {}

    async def create_owner(self, owner: Owner) -> Owner:
        if owner.district == "Atlantis":
            raise Invalid("unknown district: Atlantis")
        self.owners[owner.id] = owner
        return owner

    async def owner_exists(self, owner_id: str) -> bool:
        return owner_id in self.owners


@pytest.fixture()
def catalog():
    return FakeCatalog()


@pytest.fixture()
def client(catalog):
    app = build_app(
        Settings(database_url="sqlite+aiosqlite://", cors_origins="", session_days=1),
        catalog=catalog,
    )
    with TestClient(app) as c:
        yield c


def _register(c, email="mara@example.com", password="correct horse", name="Mara Lindqvist", district="Kreuzberg"):
    return c.post(
        "/auth/register",
        json={"email": email, "password": password, "name": name, "kind": "person", "district": district},
    )


def test_passwords_hash_and_verify():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$") and verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert hash_password("correct horse") != h, "a fresh salt every time"
    assert not verify_password("x", "garbage")


def test_register_creates_owner_and_signs_in(client, catalog):
    r = _register(client, email="  Mara@Example.com ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"] and body["account"]["email"] == "mara@example.com"
    uid = body["account"]["id"]
    assert uid.startswith("u_") and uid in catalog.owners
    owner = catalog.owners[uid]
    assert owner.name == "Mara Lindqvist" and owner.initials == "ML" and owner.district == "Kreuzberg"
    assert owner.jobs_done == 0 and owner.verified is False

    me = client.get("/auth/session", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["id"] == uid and me.json()["email"] == "mara@example.com"

    assert client.get(f"/internal/accounts/{uid}").json()["email"] == "mara@example.com"
    assert client.get("/internal/accounts/o5").status_code == 404, "seeded owners have no account"


def test_register_validation(client):
    assert _register(client, email="not-an-email").status_code == 422
    assert _register(client, password="short").status_code == 422
    assert _register(client, district="Atlantis").status_code == 422, "the catalog's answer comes through"
    assert _register(client).status_code == 201
    r = _register(client, email="MARA@example.com")
    assert r.status_code == 409 and "sign in" in r.json()["error"]["message"]


def test_login_logout(client):
    _register(client)
    bad = client.post("/auth/login", json={"email": "mara@example.com", "password": "nope"})
    assert bad.status_code == 401
    unknown = client.post("/auth/login", json={"email": "who@example.com", "password": "correct horse"})
    assert unknown.status_code == 401 and unknown.json() == bad.json(), "one message for both"

    ok = client.post("/auth/login", json={"email": "Mara@Example.com", "password": "correct horse"})
    assert ok.status_code == 200
    token = ok.json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/session", headers=auth).status_code == 200

    assert client.post("/auth/logout", headers=auth).status_code == 204
    assert client.get("/auth/session", headers=auth).status_code == 401
    assert client.get("/auth/session").status_code == 401
    assert client.get("/auth/session", headers={"Authorization": "Bearer nonsense"}).status_code == 401


def test_demo_account_is_seeded_and_survives_reset():
    app = build_app(
        Settings(
            database_url="sqlite+aiosqlite://",
            cors_origins="",
            demo_account_owner_id="o1",
            demo_account_email="nadia@cappy.demo",
            demo_account_password="cappy-demo",
        ),
        catalog=FakeCatalog(),
    )
    with TestClient(app) as c:
        r = c.post("/auth/login", json={"email": "nadia@cappy.demo", "password": "cappy-demo"})
        assert r.status_code == 200 and r.json()["account"]["id"] == "o1"
        token = r.json()["token"]
        _register(c)
        assert c.post("/admin/reset").status_code == 204
        assert c.get("/auth/session", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        assert c.post("/auth/login", json={"email": "mara@example.com", "password": "correct horse"}).status_code == 401
        assert c.post("/auth/login", json={"email": "nadia@cappy.demo", "password": "cappy-demo"}).status_code == 200
