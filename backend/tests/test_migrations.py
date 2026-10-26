"""The Alembic migration history builds exactly the schema the models describe."""
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_upgrade_match_models_and_downgrade(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_DATABASE_URL", f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "alembic"))
        command.upgrade(cfg, "head")
        command.check(cfg)  # raises if models and migrations have drifted apart
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    finally:
        get_settings.cache_clear()
