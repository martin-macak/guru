import subprocess
from unittest.mock import MagicMock, patch

import pytest

from guru_server.startup import (
    ModelNotFoundError,
    OllamaNotFoundError,
    check_model_available,
    check_ollama_installed,
)


def test_check_ollama_installed_success():
    with patch("shutil.which", return_value="/opt/homebrew/bin/ollama"):
        check_ollama_installed()  # should not raise


def test_check_ollama_installed_not_found():
    with (
        patch("shutil.which", return_value=None),
        pytest.raises(OllamaNotFoundError, match="brew install ollama"),
    ):
        check_ollama_installed()


def test_check_model_available_success():
    mock_result = MagicMock()
    mock_result.stdout = "nomic-embed-text:latest\tsome-hash\t274 MB"
    with patch("subprocess.run", return_value=mock_result):
        check_model_available("nomic-embed-text")  # should not raise


def test_check_model_available_not_found():
    mock_result = MagicMock()
    mock_result.stdout = "llama3:latest\tsome-hash\t4.7 GB"
    with (
        patch("subprocess.run", return_value=mock_result),
        pytest.raises(ModelNotFoundError, match="ollama pull nomic-embed-text"),
    ):
        check_model_available("nomic-embed-text")


def test_check_model_available_ollama_not_running():
    with (
        patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ollama")),
        pytest.raises(ModelNotFoundError),
    ):
        check_model_available("nomic-embed-text")


def test_check_model_available_ollama_timeout():
    """check_model_available raises ModelNotFoundError when ollama list times out."""
    with (
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["ollama", "list"], 10)),
        pytest.raises(ModelNotFoundError, match="did not respond within"),
    ):
        check_model_available("nomic-embed-text")
