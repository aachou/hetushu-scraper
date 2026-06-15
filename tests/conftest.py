import pytest


@pytest.fixture
def patch_cache_dir(tmp_path, monkeypatch):
    from hetushu_scraper import config, cache
    d = str(tmp_path / ".chapter_cache")
    monkeypatch.setattr(config, "CACHE_DIR", d)
    monkeypatch.setattr(cache, "CACHE_DIR", d)
