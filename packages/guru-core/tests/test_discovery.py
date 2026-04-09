import pytest

from guru_core.discovery import GuruNotFoundError, find_guru_root


def test_find_guru_root_in_current_dir(tmp_path):
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    result = find_guru_root(tmp_path)
    assert result == tmp_path


def test_find_guru_root_walks_up(tmp_path):
    guru_dir = tmp_path / ".guru"
    guru_dir.mkdir()
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    result = find_guru_root(nested)
    assert result == tmp_path


def test_find_guru_root_not_found(tmp_path):
    nested = tmp_path / "no" / "guru" / "here"
    nested.mkdir(parents=True)
    with pytest.raises(GuruNotFoundError, match="Not a guru project"):
        find_guru_root(nested)


def test_find_guru_root_stops_at_filesystem_root(tmp_path):
    # tmp_path has no .guru — should raise, not infinite loop
    with pytest.raises(GuruNotFoundError):
        find_guru_root(tmp_path)
