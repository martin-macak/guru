from __future__ import annotations

import socket
import webbrowser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebRuntime:
    enabled: bool
    available: bool
    url: str | None
    port: int | None
    assets_dir: Path | None
    reason: str | None
    auto_open: bool


def _pick_free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def bind_web_listener_sockets(*, uds_path: Path, port: int) -> list[socket.socket]:
    uds_path.parent.mkdir(parents=True, exist_ok=True)
    uds_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        uds_socket.bind(str(uds_path))
        uds_socket.listen(2048)

        tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_socket.bind(("127.0.0.1", port))
        tcp_socket.listen(2048)
    except Exception:
        uds_socket.close()
        tcp_socket.close()
        uds_path.unlink(missing_ok=True)
        raise
    return [uds_socket, tcp_socket]


def open_web_browser(url: str | None) -> bool:
    if not url:
        return False
    try:
        return bool(webbrowser.open(url))
    except webbrowser.Error:
        return False


def build_web_runtime(
    *,
    project_root: Path,
    assets_dir: Path,
    enabled: bool,
    auto_open: bool = False,
) -> WebRuntime:
    _ = project_root
    if not enabled:
        return WebRuntime(
            enabled=False,
            available=False,
            url=None,
            port=None,
            assets_dir=None,
            reason="disabled",
            auto_open=auto_open,
        )

    assets_dir = assets_dir.resolve()
    if not assets_dir.is_dir():
        return WebRuntime(
            enabled=True,
            available=False,
            url=None,
            port=None,
            assets_dir=None,
            reason="assets_missing",
            auto_open=auto_open,
        )

    port = _pick_free_port()
    return WebRuntime(
        enabled=True,
        available=True,
        url=f"http://127.0.0.1:{port}",
        port=port,
        assets_dir=assets_dir,
        reason=None,
        auto_open=auto_open,
    )
