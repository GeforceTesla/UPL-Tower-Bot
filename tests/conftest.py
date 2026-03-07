import sys
import pathlib
import pytest
import pytest_asyncio

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import db


@pytest_asyncio.fixture
async def fresh_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", str(db_file))
    await db.init_db()
    return str(db_file)
