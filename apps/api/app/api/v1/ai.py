from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.errors import ValidationError
from ...models.user import User
from ...schemas.models import AiExplainRequest, AiExplanationOut
from ...services.ai_explain import explain_transaction, explain_wallet
from ...utils.rate_limit import AI_GLOBAL, AI_USER, make_limiter
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/explain", response_model=AiExplanationOut)
async def explain(
    payload: AiExplainRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AiExplanationOut:
    if payload.wallet_id is None and payload.tx_id is None:
        raise ValidationError("either wallet_id or tx_id must be provided")

    user_limiter = make_limiter(AI_USER)
    await user_limiter.check(f"ai:user:{user.id}")
    global_limiter = make_limiter(AI_GLOBAL)
    await global_limiter.check("ai:global")

    if payload.tx_id is not None:
        row = await explain_transaction(db, user_id=user.id, tx_id=payload.tx_id)
    else:
        assert payload.wallet_id is not None
        row = await explain_wallet(db, user_id=user.id, wallet_id=payload.wallet_id)
    await db.commit()
    return AiExplanationOut(
        explanation=row.explanation,
        model=row.model,
        is_cached=row.is_cached,
        input_summary=row.input_summary,
    )
