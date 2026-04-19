from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class OllamaNotFoundError(RuntimeError):
    pass


class ModelNotFoundError(RuntimeError):
    pass


def check_ollama_installed() -> None:
    if shutil.which("ollama") is None:
        raise OllamaNotFoundError(
            "Ollama is not installed or not on PATH.\n"
            "Install it with: brew install ollama\n"
            "Or visit: https://ollama.com"
        )
    logger.info("Ollama found on PATH")


def check_model_available(model: str = "nomic-embed-text") -> None:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise ModelNotFoundError(
            f"Ollama did not respond within 10s. Is it still starting up?\n"
            f"Pull the model with: ollama pull {model}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ModelNotFoundError(
            f"Could not list Ollama models. Is Ollama running?\n"
            f"Pull the model with: ollama pull {model}"
        ) from exc
    if model not in result.stdout:
        raise ModelNotFoundError(
            f"Model '{model}' is not available.\nPull it with: ollama pull {model}"
        )
    logger.info("Model '%s' is available", model)


def start_ollama_serve() -> subprocess.Popen | None:
    try:
        subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=5)
        logger.info("Ollama is already running")
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    logger.info("Starting ollama serve")
    return subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop_ollama_serve(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


async def run_startup_reconcile(sync) -> None:
    """Run a best-effort reconcile on server boot when there's drift.

    Async because ``SyncService.status`` / ``reconcile`` are async (they
    issue HTTP/UDS calls to the graph daemon via GraphClient).
    """
    from guru_server.sync import SyncService  # noqa: F401 — kept for type-checking context

    status = await sync.status()
    if not status.graph_enabled:
        logger.info("startup.reconcile skipped: graph disabled")
        return
    if status.drift == 0:
        logger.info(
            "startup.reconcile skipped: no drift (lancedb=%d graph=%d)",
            status.lancedb_count,
            status.graph_count,
        )
        return
    logger.warning("startup.reconcile begin: drift=%d", status.drift)
    await sync.reconcile()
    logger.info("startup.reconcile complete")
