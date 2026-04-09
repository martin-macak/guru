"""Tests for the PEP 503 simple index generator."""

import sys
from pathlib import Path

# Allow importing the script from the same directory
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from generate_index import generate_index


@pytest.fixture
def wheel_dir(tmp_path):
    """Create a fake wheels directory with sample wheel files."""
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    # Create fake wheel files (content doesn't matter, just filenames)
    (wheels / "guru-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_core-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_server-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_mcp-0.1.0-py3-none-any.whl").touch()
    (wheels / "guru_cli-0.1.0-py3-none-any.whl").touch()
    return wheels


def test_generates_root_index(wheel_dir, tmp_path):
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    root_html = (simple / "index.html").read_text()
    assert '<a href="guru/">guru</a>' in root_html
    assert '<a href="guru-core/">guru-core</a>' in root_html
    assert '<a href="guru-server/">guru-server</a>' in root_html
    assert '<a href="guru-mcp/">guru-mcp</a>' in root_html
    assert '<a href="guru-cli/">guru-cli</a>' in root_html


def test_generates_package_index(wheel_dir, tmp_path):
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    guru_html = (simple / "guru" / "index.html").read_text()
    assert "guru-0.1.0-py3-none-any.whl" in guru_html
    # Check the href points to the wheels directory
    assert "../../wheels/guru-0.1.0-py3-none-any.whl" in guru_html


def test_multiple_versions(wheel_dir, tmp_path):
    (wheel_dir / "guru-0.2.0-py3-none-any.whl").touch()
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    guru_html = (simple / "guru" / "index.html").read_text()
    assert "guru-0.1.0-py3-none-any.whl" in guru_html
    assert "guru-0.2.0-py3-none-any.whl" in guru_html


def test_normalized_package_names(wheel_dir, tmp_path):
    """Wheel filenames use underscores but PEP 503 dirs use hyphens."""
    simple = tmp_path / "simple"
    generate_index(wheel_dir, simple)
    # guru_core wheel -> guru-core directory
    assert (simple / "guru-core" / "index.html").is_file()
    core_html = (simple / "guru-core" / "index.html").read_text()
    assert "guru_core-0.1.0-py3-none-any.whl" in core_html
