from __future__ import annotations

import shutil
import subprocess


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


def check_model_available(model: str = "nomic-embed-text") -> None:
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ModelNotFoundError(
            f"Could not list Ollama models. Is Ollama running?\n"
            f"Pull the model with: ollama pull {model}"
        ) from exc
    if model not in result.stdout:
        raise ModelNotFoundError(
            f"Model '{model}' is not available.\nPull it with: ollama pull {model}"
        )


def start_ollama_serve() -> subprocess.Popen | None:
    try:
        subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True, timeout=5)
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
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
