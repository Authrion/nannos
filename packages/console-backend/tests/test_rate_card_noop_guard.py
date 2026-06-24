"""Tests for the rate-card write-time no-op guard.

`RateCardRepository.create_entry` skips the insert when the current active rate for a
(rate card, billing_unit) already equals the new price — so re-registering or re-saving a model
with unchanged prices doesn't accumulate identical superseding versions (history bloat). A genuine
price change still writes a new version, and the current rate resolves to the latest effective_from.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from console_backend.models.user import User
from console_backend.repositories.rate_card_repository import RateCardRepository
from console_backend.services.audit_service import AuditService
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _repo() -> RateCardRepository:
    repo = RateCardRepository()
    repo.set_audit_service(AuditService())
    return repo


async def _count(db: AsyncSession, provider: str, model: str, unit: str) -> int:
    result = await db.execute(
        text(
            """
            SELECT count(*) FROM rate_card_entries rce
            JOIN rate_cards rc ON rc.id = rce.rate_card_id
            WHERE rc.provider = :p AND rc.model_name = :m AND rce.billing_unit = :bu
            """
        ),
        {"p": provider, "m": model, "bu": unit},
    )
    return int(result.scalar() or 0)


@pytest.mark.asyncio
async def test_duplicate_same_price_is_skipped(pg_session: AsyncSession, test_user: User):
    """Re-creating an entry at the same active price is a no-op: no row added, existing id returned."""
    repo = _repo()
    provider, model, unit = "test-vertex", "noop-guard-model", "base_input_tokens"

    id1 = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit=unit, flow_direction="input", price_per_million=Decimal("3.00"), effective_from=T0,
    )
    # Same price (and an equivalent Decimal form), later effective_from → guard skips the insert.
    id2 = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit=unit, flow_direction="input", price_per_million=Decimal("3.000000"),
        effective_from=T0 + timedelta(days=1),
    )

    assert id2 == id1
    assert await _count(pg_session, provider, model, unit) == 1


@pytest.mark.asyncio
async def test_price_change_creates_new_version(pg_session: AsyncSession, test_user: User):
    """A different price writes a new version; the current rate is the latest effective_from."""
    repo = _repo()
    provider, model, unit = "test-vertex", "price-change-model", "base_input_tokens"

    id1 = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit=unit, flow_direction="input", price_per_million=Decimal("3.00"), effective_from=T0,
    )
    id2 = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit=unit, flow_direction="input", price_per_million=Decimal("5.00"),
        effective_from=T0 + timedelta(days=1),
    )

    assert id2 != id1
    assert await _count(pg_session, provider, model, unit) == 2

    rates = await repo.get_all_active_rates(pg_session, provider, model, as_of=T0 + timedelta(days=2))
    assert rates[unit] == Decimal("5.00")


@pytest.mark.asyncio
async def test_guard_is_per_billing_unit(pg_session: AsyncSession, test_user: User):
    """The same price on a different billing unit is NOT a duplicate — each unit is independent."""
    repo = _repo()
    provider, model = "test-vertex", "per-unit-model"

    id_in = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit="base_input_tokens", flow_direction="input", price_per_million=Decimal("2.00"),
        effective_from=T0,
    )
    id_out = await repo.create_entry(
        db=pg_session, actor=test_user, provider=provider, model_name=model,
        billing_unit="base_output_tokens", flow_direction="output", price_per_million=Decimal("2.00"),
        effective_from=T0,
    )

    assert id_out != id_in
    assert await _count(pg_session, provider, model, "base_input_tokens") == 1
    assert await _count(pg_session, provider, model, "base_output_tokens") == 1
