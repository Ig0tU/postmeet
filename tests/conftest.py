"""Deterministic metadata boundaries: no regression test should reach YouTube."""
from unittest.mock import Mock

import pytest

EXACT_TITLE = '  Board Meeting — "Public Comment" & Budget <2026>  '


@pytest.fixture(autouse=True)
def block_metadata_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected network metadata lookup; patch resolve_youtube_title")
    monkeypatch.setattr("postmeet.playback.urlopen", blocked)
    monkeypatch.setattr("postmeet.source_fields._ytdlp", blocked)


@pytest.fixture
def youtube_metadata(monkeypatch):
    resolver = Mock(return_value=EXACT_TITLE)
    monkeypatch.setattr("postmeet.playback.resolve_youtube_title", resolver)
    return resolver
