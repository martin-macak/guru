from pathlib import Path

from guru_core.types import MatchConfig, Rule
from guru_server.watcher import should_watch_path


def test_should_watch_markdown_file():
    config = [Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/docs/guide.md"), project_root, config) is True


def test_should_not_watch_non_matching_file():
    config = [Rule(rule_name="docs", match=MatchConfig(glob="docs/**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/src/main.py"), project_root, config) is False


def test_should_not_watch_guru_dir():
    config = [Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/.guru/db/data.md"), project_root, config) is False


def test_should_not_watch_transient_files():
    config = [Rule(rule_name="all", match=MatchConfig(glob="**/*.md"))]
    project_root = Path("/project")
    assert should_watch_path(Path("/project/docs/guide.md.swp"), project_root, config) is False
    assert should_watch_path(Path("/project/docs/guide.md~"), project_root, config) is False
    assert should_watch_path(Path("/project/docs/.guide.md.tmp"), project_root, config) is False
