"""API integration tests with the dev-bypass-auth path.

These tests cover:
  - health endpoints
  - wallet CRUD
  - duplicate wallet creation
  - IDOR protection (cross-user access returns 404)
  - transactions / holdings / snapshots
  - alert CRUD + kinds
  - AI explain happy path
  - pagination bounds
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_liveness(client):
    r = await client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "crypto-intelligence-platform"


@pytest.mark.asyncio
async def test_create_wallet_and_list(authed_client):
    addr = "0x" + "ab" * 20
    r = await authed_client.post(
        "/api/v1/wallets",
        json={"chain": "ethereum", "address": addr, "label": "main"},
    )
    assert r.status_code == 201, r.text
    wallet = r.json()
    assert wallet["chain"] == "ethereum"
    assert wallet["label"] == "main"
    assert wallet["address"] == wallet["address"].upper() or wallet["address"].startswith("0x")
    wid = wallet["id"]

    # List
    r = await authed_client.get("/api/v1/wallets")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["total"] >= 1
    assert any(w["id"] == wid for w in data["items"])


@pytest.mark.asyncio
async def test_duplicate_wallet_creation_rejected(authed_client):
    addr = "0x" + "cd" * 20
    r = await authed_client.post(
        "/api/v1/wallets",
        json={"chain": "ethereum", "address": addr, "label": None},
    )
    assert r.status_code == 201
    r2 = await authed_client.post(
        "/api/v1/wallets",
        json={"chain": "ethereum", "address": addr, "label": None},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_invalid_address_rejected(authed_client):
    r = await authed_client.post(
        "/api/v1/wallets",
        json={"chain": "ethereum", "address": "not-an-address"},
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_unsupported_chain_rejected(authed_client):
    r = await authed_client.post(
        "/api/v1/wallets",
        json={"chain": "solana", "address": "0x" + "ab" * 20},
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_wallet_transactions_endpoint(authed_client):
    addr = "0x" + "12" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    assert r.status_code == 201
    wid = r.json()["id"]
    r2 = await authed_client.get(f"/api/v1/wallets/{wid}/transactions")
    assert r2.status_code == 200
    data = r2.json()
    assert "items" in data and "meta" in data


@pytest.mark.asyncio
async def test_take_snapshot(authed_client):
    addr = "0x" + "34" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.post(f"/api/v1/wallets/{wid}/snapshot")
    assert r2.status_code == 201, r2.text
    snap = r2.json()
    assert "native_amount" in snap


@pytest.mark.asyncio
async def test_alert_create_and_list(authed_client):
    addr = "0x" + "56" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.post(
        "/api/v1/alerts",
        json={"wallet_id": wid, "kind": "incoming_above", "threshold_amount": 0.5},
    )
    assert r2.status_code == 201
    aid = r2.json()["id"]
    r3 = await authed_client.get("/api/v1/alerts")
    assert r3.status_code == 200
    assert any(a["id"] == aid for a in r3.json()["items"])


@pytest.mark.asyncio
async def test_alert_invalid_kind_rejected(authed_client):
    addr = "0x" + "78" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.post(
        "/api/v1/alerts",
        json={"wallet_id": wid, "kind": "bogus_kind"},
    )
    assert r2.status_code in (400, 422)


@pytest.mark.asyncio
async def test_alert_kinds_endpoint(authed_client):
    r = await authed_client.get("/api/v1/alerts/kinds")
    assert r.status_code == 200
    kinds = r.json()
    assert "incoming_above" in kinds
    assert "outgoing_above" in kinds


@pytest.mark.asyncio
async def test_ai_explain_wallet(authed_client):
    addr = "0x" + "9a" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.post("/api/v1/ai/explain", json={"wallet_id": wid})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert "explanation" in data
    assert "model" in data
    assert isinstance(data["is_cached"], bool)


@pytest.mark.asyncio
async def test_ai_explain_requires_target(authed_client):
    r = await authed_client.post("/api/v1/ai/explain", json={})
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_pagination_bounds(authed_client):
    # page=0 should be rejected
    r = await authed_client.get("/api/v1/wallets?page=0")
    assert r.status_code == 422
    # page_size=0 should be rejected
    r = await authed_client.get("/api/v1/wallets?page_size=0")
    assert r.status_code == 422
    # page_size=1000 should be rejected (>100)
    r = await authed_client.get("/api/v1/wallets?page_size=1000")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unauth_request_rejected(client):
    r = await client.get("/api/v1/wallets")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_idor_wallet_returns_404_for_other_user(db_session):
    """A wallet owned by user A must NOT be accessible by user B.

    The service returns NotFoundError (404) — never 403 — to avoid leaking
    the wallet's existence.
    """

    import pytest as _pytest

    from apps.api.app.models.user import User
    from apps.api.app.models.wallet import Wallet
    from apps.api.app.services.wallets import get_owned_wallet

    user_a = User(telegram_id=100_001, telegram_username="a")
    user_b = User(telegram_id=100_002, telegram_username="b")
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    wallet = Wallet(
        user_id=user_a.id,
        chain="ethereum",
        address="0x" + "ee" * 20,
        native_symbol="ETH",
    )
    db_session.add(wallet)
    await db_session.flush()

    # Owner can access
    fetched = await get_owned_wallet(db_session, user_id=user_a.id, wallet_id=wallet.id)
    assert fetched.id == wallet.id

    # Other user gets 404 (not 403, not 200)
    with _pytest.raises(Exception) as exc:
        await get_owned_wallet(db_session, user_id=user_b.id, wallet_id=wallet.id)
    # NotFoundError has status_code 404
    from apps.api.app.core.errors import NotFoundError

    assert isinstance(exc.value, NotFoundError)


@pytest.mark.asyncio
async def test_wallet_holdings(authed_client):
    addr = "0x" + "01" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.get(f"/api/v1/wallets/{wid}/holdings")
    assert r2.status_code == 200
    assert isinstance(r2.json(), list)


@pytest.mark.asyncio
async def test_delete_wallet(authed_client):
    addr = "0x" + "02" * 20
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": addr, "label": None}
    )
    wid = r.json()["id"]
    r2 = await authed_client.delete(f"/api/v1/wallets/{wid}")
    assert r2.status_code == 204
    r3 = await authed_client.get(f"/api/v1/wallets/{wid}")
    assert r3.status_code == 404
