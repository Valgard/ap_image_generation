#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = ["pytest", "google-genai", "typer", "rich"]
# ///
"""Tests for generate_images helper functions."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

import generate_images as gi


def test_ensure_out_dir_creates_and_returns(tmp_path):
    target = tmp_path / "articles" / "x" / "sources"
    out = gi.ensure_out_dir(target)
    assert out == target
    assert out.is_dir()


def test_run_config_json_serializes_effective_config():
    out = gi.run_config_json(
        model=gi.MODEL,
        prompt="a cat",
        prompt_file=None,
        out_dir=Path("articles/x/sources"),
        name="feature-image",
        count=5,
        aspect_ratio="16:9",
        resolution="2K",
        start_index=1,
        references=[Path("ref.png")],
    )
    data = json.loads(out)
    assert data["model"] == gi.MODEL
    assert data["prompt"] == "a cat"
    assert data["prompt_file"] is None
    assert data["out_dir"] == "articles/x/sources"
    assert data["name"] == "feature-image"
    assert data["count"] == 5
    assert data["aspect_ratio"] == "16:9"
    assert data["resolution"] == "2K"
    assert data["start_index"] == 1
    assert data["references"] == ["ref.png"]


def test_run_config_json_preserves_non_ascii():
    out = gi.run_config_json(
        model=gi.MODEL,
        prompt="Café à la Größe",
        prompt_file=Path("p.txt"),
        out_dir=Path("o"),
        name="n",
        count=1,
        aspect_ratio="auto",
        resolution="1K",
        start_index=1,
        references=[],
    )
    assert "Café à la Größe" in out
    assert "\\u" not in out
    assert json.loads(out)["prompt_file"] == "p.txt"


def test_mime_for_known_suffixes():
    assert gi.mime_for(Path("a.jpg")) == "image/jpeg"
    assert gi.mime_for(Path("a.jpeg")) == "image/jpeg"
    assert gi.mime_for(Path("a.JPEG")) == "image/jpeg"
    assert gi.mime_for(Path("a.png")) == "image/png"
    assert gi.mime_for(Path("a.webp")) == "image/webp"


def test_mime_for_unknown_suffix_raises():
    with pytest.raises(ValueError):
        gi.mime_for(Path("a.gif"))


def test_resolve_prompt_from_argument():
    assert gi.resolve_prompt("a prompt", None) == "a prompt"


def test_resolve_prompt_from_file(tmp_path):
    f = tmp_path / "prompt.txt"
    f.write_text("  file prompt\n")
    assert gi.resolve_prompt(None, f) == "file prompt"


def test_resolve_prompt_neither_raises():
    with pytest.raises(ValueError):
        gi.resolve_prompt(None, None)


def test_resolve_prompt_both_raises(tmp_path):
    f = tmp_path / "prompt.txt"
    f.write_text("x")
    with pytest.raises(ValueError):
        gi.resolve_prompt("a prompt", f)


def test_candidate_indices_default_start():
    assert list(gi.candidate_indices(1, 5)) == [1, 2, 3, 4, 5]


def test_candidate_indices_offset_start():
    assert list(gi.candidate_indices(6, 5)) == [6, 7, 8, 9, 10]


def test_output_filename():
    assert gi.output_filename("feature-image", 3, "jpeg") == "feature-image-3.jpeg"
    assert gi.output_filename("diagram", 1, "png") == "diagram-1.png"


def test_require_api_key_present(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    assert gi.require_api_key() == "test-key-123"


def test_require_api_key_missing_exits(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(typer.Exit):
        gi.require_api_key()


def test_build_image_config_auto_returns_none():
    assert gi.build_image_config("auto", "1K") is None


def test_build_image_config_specific():
    cfg = gi.build_image_config("16:9", "2K")
    assert cfg is not None
    assert cfg.aspect_ratio == "16:9"
    assert cfg.image_size == "2K"


def _response(parts):
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts))]
    )


def _image_part(data, mime):
    return SimpleNamespace(
        inline_data=SimpleNamespace(data=data, mime_type=mime), text=None
    )


def _text_part(text):
    return SimpleNamespace(inline_data=None, text=text)


def test_extract_image_returns_bytes_and_ext():
    resp = _response([_image_part(b"PNGDATA", "image/png")])
    assert gi.extract_image(resp) == (b"PNGDATA", "png")


def test_extract_image_skips_text_parts():
    resp = _response([_text_part("some text"), _image_part(b"JPG", "image/jpeg")])
    assert gi.extract_image(resp) == (b"JPG", "jpeg")


def test_extract_image_no_image_returns_none():
    resp = _response([_text_part("refused")])
    assert gi.extract_image(resp) is None


def test_extract_image_empty_candidates_returns_none():
    assert gi.extract_image(SimpleNamespace(candidates=[])) is None
