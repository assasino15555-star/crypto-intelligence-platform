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
    assert r.json()["name"] == "crypto-intelligence-platform"


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
    wid = wallet["id"]

    r2 = await authed_client.get("/api/v1/wallets")
    assert r2.status_code == 200
    data = r2.json()
    assert data["meta"]["total"] >= 1
    assert any(w["id"] == wid for w in data["items"])


@pytest.mark.asyncio
async def test_duplicate_wallet_rejected(authed_client):
    addr = "0x" + "cd" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    assert r.status_code == 201
    r2 = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_invalid_address_rejected(authed_client):
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "ethereum", "address": "not-an-address"}
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_unsupported_chain_rejected(authed_client):
    r = await authed_client.post(
        "/api/v1/wallets", json={"chain": "solana", "address": "0x" + "ab" * 20}
    )
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_active_only_filter(authed_client):
    addr = "0x" + "ef" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    assert r.status_code == 201
    wid = r.json()["id"]
    await authed_client.patch(f"/api/v1/wallets/{wid}", json={"is_active": False})
    r2 = await authed_client.get("/api/v1/wallets?active_only=true")
    assert r2.status_code == 200
    for w in r2.json()["items"]:
        assert w["is_active"] is True


@pytest.mark.asyncio
async def test_wallet_transactions(authed_client):
    addr = "0x" + "12" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    wid = r.json()["id"]
    r2 = await authed_client.get(f"/api/v1/wallets/{wid}/transactions")
    assert r2.status_code == 200
    assert "items" in r2.json() and "meta" in r2.json()


@pytest.mark.asyncio
async def test_take_snapshot(authed_client):
    addr = "0x" + "34" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    wid = r.json()["id"]
    r2 = await authed_client.post(f"/api/v1/wallets/{wid}/snapshot")
    assert r2.status_code == 201, r2.text
    assert "native_amount" in r2.json()


@pytest.mark.asyncio
async def test_alert_create_and_list(authed_client):
    addr = "0x" + "56" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
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
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    wid = r.json()["id"]
    r2 = await authed_client.post("/api/v1/alerts", json={"wallet_id": wid, "kind": "bogus_kind"})
    assert r2.status_code in (400, 422)


@pytest.mark.asyncio
async def test_alert_kinds(authed_client):
    r = await authed_client.get("/api/v1/alerts/kinds")
    assert r.status_code == 200
    kinds = r.json()
    assert "incoming_above" in kinds
    assert "outgoing_above" in kinds


@pytest.mark.asyncio
async def test_ai_explain_wallet(authed_client):
    addr = "0x" + "9a" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    wid = r.json()["id"]
    r2 = await authed_client.post("/api/v1/ai/explain", json={"wallet_id": wid})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert "explanation" in data
    assert "model" in data


@pytest.mark.asyncio
async def test_ai_explain_requires_target(authed_client):
    r = await authed_client.post("/api/v1/ai/explain", json={})
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_pagination_bounds(authed_client):
    r = await authed_client.get("/api/v1/wallets?page=0")
    assert r.status_code == 422
    r = await authed_client.get("/api/v1/wallets?page_size=0")
    assert r.status_code == 422
    r = await authed_client.get("/api/v1/wallets?page_size=1000")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unauth_rejected(client):
    r = await client.get("/api/v1/wallets")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_idor_returns_404(db_session):

    from apps.api.app.api.v1.wallets import _get_owned_wallet
    from apps.api.app.core.errors import NotFoundError
    from apps.api.app.models.user import User
    from apps.api.app.models.wallet import Wallet

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

    fetched = await _get_owned_wallet(db_session, user_id=user_a.id, wallet_id=wallet.id)
    assert fetched.id == wallet.id

    with pytest.raises(NotFoundError):
        await _get_owned_wallet(db_session, user_id=user_b.id, wallet_id=wallet.id)


@pytest.mark.asyncio
async def test_delete_wallet(authed_client):
    addr = "0x" + "02" * 20
    r = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr})
    wid = r.json()["id"]
    r2 = await authed_client.delete(f"/api/v1/wallets/{wid}")
    assert r2.status_code == 204
    r3 = await authed_client.get(f"/api/v1/wallets/{wid}")
    assert r3.status_code == 404


@pytest.mark.asyncio
async def test_wallet_quota_enforced(authed_client, monkeypatch):
    from apps.api.app.core import config as cfg

    cfg.get_settings().max_wallets_per_user = 1
    addr1 = "0x" + "11" * 20
    r1 = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr1})
    assert r1.status_code == 201
    addr2 = "0x" + "22" * 20
    r2 = await authed_client.post("/api/v1/wallets", json={"chain": "ethereum", "address": addr2})
    assert r2.status_code == 409
    cfg.get_settings().max_wallets_per_user = 20


@pytest.mark.asyncio
async def test_revoke_all(authed_client):
    r = await authed_client.post("/api/v1/auth/revoke-all")
    assert r.status_code == 204
