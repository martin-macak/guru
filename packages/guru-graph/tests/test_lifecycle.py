from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

from guru_graph.config import GraphPaths
from guru_graph.lifecycle import (
    connect_or_spawn,
    is_socket_alive,
    read_pid_file,
    write_pid_file,
)


def test_pid_file_round_trip(tmp_path: Path):
    pid_file = tmp_path / "d.pid"
    write_pid_file(pid_file, 12345)
    assert read_pid_file(pid_file) == 12345


def test_read_pid_missing_returns_none(tmp_path: Path):
    assert read_pid_file(tmp_path / "nope") is None


def test_read_pid_garbage_returns_none(tmp_path: Path):
    pid_file = tmp_path / "garbage"
    pid_file.write_text("not a number")
    assert read_pid_file(pid_file) is None


def test_socket_alive_nonexistent(tmp_path: Path):
    assert is_socket_alive(tmp_path / "missing.sock") is False


def test_connect_or_spawn_spawns_when_missing(tmp_path: Path):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    calls = []

    def fake_spawn():
        calls.append("spawn")
        # is_socket_alive is mocked below; no real socket needed
        return 99999

    with (
        patch("guru_graph.lifecycle._spawn_daemon", side_effect=fake_spawn),
        patch("guru_graph.lifecycle.is_socket_alive", side_effect=[False, False, True]),
    ):
        connect_or_spawn(paths=paths, ready_timeout_seconds=2.0)

    assert calls == ["spawn"]


def test_connect_or_spawn_skips_when_socket_alive(tmp_path: Path, monkeypatch):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    monkeypatch.setattr("guru_graph.lifecycle.is_socket_alive", lambda p: True)
    spawned = []
    monkeypatch.setattr(
        "guru_graph.lifecycle._spawn_daemon",
        lambda: spawned.append(1) or 1,
    )
    connect_or_spawn(paths=paths, ready_timeout_seconds=1.0)
    assert spawned == []


def test_concurrent_spawn_only_one_wins(tmp_path: Path, monkeypatch):
    paths = GraphPaths.for_test(base=tmp_path)
    paths.ensure_dirs()
    spawn_count = 0
    lock = threading.Lock()
    socket_alive = {"value": False}

    def fake_is_alive(path):
        return socket_alive["value"]

    def fake_spawn():
        nonlocal spawn_count
        with lock:
            spawn_count += 1
            socket_alive["value"] = True
        return 12345

    monkeypatch.setattr("guru_graph.lifecycle.is_socket_alive", fake_is_alive)
    monkeypatch.setattr("guru_graph.lifecycle._spawn_daemon", fake_spawn)

    threads = [
        threading.Thread(
            target=connect_or_spawn,
            kwargs={"paths": paths, "ready_timeout_seconds": 2.0},
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert spawn_count == 1
