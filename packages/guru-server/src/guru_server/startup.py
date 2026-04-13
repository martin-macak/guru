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
