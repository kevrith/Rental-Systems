"""BI/warehouse export (Sprint 26A, item 14) — app/services/export_service.py."""

import io
import uuid
from decimal import Decimal

import pyarrow.parquet as pq
from sqlalchemy import select

from app.api.deps import OrgContext
from app.models.organization import Organization
from app.models.user import User
from app.models.vacancy import DataExport, ExportFormat, ExportKind
from app.services import export_service
from tests.conftest import Actor
from tests.test_operations import occupied_unit


def test_to_parquet_preserves_null_and_numeric_types() -> None:
    rows = [
        {"Name": "Alice", "Amount": Decimal("1000.50"), "Notes": None},
        {"Name": "Bob", "Amount": Decimal("500.00"), "Notes": "paid late"},
    ]
    data = export_service.to_parquet(rows)
    assert data

    table = pq.read_table(io.BytesIO(data))
    assert table.num_rows == 2
    amount_column = table.column("Amount").to_pylist()
    assert amount_column == [1000.50, 500.00]
    notes_column = table.column("Notes").to_pylist()
    assert notes_column == [None, "paid late"]


def test_to_parquet_handles_an_empty_dataset() -> None:
    assert export_service.to_parquet([]) == b""


async def test_build_returns_parquet_bytes_for_a_real_dataset(owner: Actor, db) -> None:
    setup = await occupied_unit(owner)
    user = await db.get(User, uuid.UUID(owner.user["id"]))
    organization = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    context = OrgContext(user=user, organization=organization)

    data, filename, row_count = await export_service.build(
        db, context, ExportKind.TENANTS, ExportFormat.PARQUET
    )
    assert filename.endswith(".parquet")
    assert row_count >= 1
    assert data

    table = pq.read_table(io.BytesIO(data))
    assert table.num_rows == row_count
    assert setup["tenant"]["full_name"] in table.column("Full name").to_pylist()


async def test_run_bi_exports_skips_organizations_that_have_not_opted_in(owner: Actor, db) -> None:
    await occupied_unit(owner)
    built = await export_service.run_bi_exports(db)
    assert built == 0


async def test_run_bi_exports_builds_every_dataset_for_an_opted_in_organization(owner: Actor, db) -> None:
    await occupied_unit(owner)
    organization = await db.get(Organization, uuid.UUID(owner.user["organization_id"]))
    organization.bi_export_enabled = True
    await db.commit()

    built = await export_service.run_bi_exports(db)
    assert built == len(list(ExportKind))

    records = list(
        await db.scalars(
            select(DataExport).where(
                DataExport.organization_id == organization.id,
                DataExport.export_format == ExportFormat.PARQUET,
            )
        )
    )
    assert len(records) == len(list(ExportKind))
    assert all(record.is_scheduled is False for record in records)


async def test_parquet_export_downloads_through_the_api(owner: Actor) -> None:
    response = await owner.post(
        "/api/v1/vacancies/exports", json={"kind": "tenants", "export_format": "parquet"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/vnd.apache.parquet"
    assert response.content is not None
