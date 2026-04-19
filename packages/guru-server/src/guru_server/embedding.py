from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


# Known embedding dimensions for Ollama models. Update when adding support for new models.
_MODEL_DIMENSIONS = {
    "nomic-embed-text": 768,
}

# Known context-window sizes (in tokens) for Ollama embedding models.
_MODEL_CONTEXT_LENGTHS = {
    "nomic-embed-text": 2048,
}


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.model_name = model
        self.dimensions = _MODEL_DIMENSIONS.get(model, 768)

    def max_input_tokens(self) -> int:
        """Return the maximum input token count for the configured model."""
        return _MODEL_CONTEXT_LENGTHS.get(self.model, 2048)

    async def check_health(self) -> None:
        """Send a lightweight test embedding to verify Ollama is responsive.

        Raises EmbeddingError with actionable guidance when the check fails
        (e.g. stale daemon, network issue, model not loaded).
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": "health check"},
                    timeout=10.0,
                )
        except httpx.ConnectError as exc:
            raise EmbeddingError(
                "Cannot connect to Ollama. Is the Ollama server running?\n"
                "Start it with: ollama serve"
            ) from exc
        except httpx.TimeoutException as exc:
            raise EmbeddingError(
                "Ollama did not respond within 10 seconds.\n"
                "Try restarting the Ollama service: brew services restart ollama"
            ) from exc
        except httpx.HTTPError as exc:
            raise EmbeddingError(
                f"Ollama health check failed: {exc}\n"
                "Try restarting the Ollama service: brew services restart ollama"
            ) from exc

        if response.status_code != 200:
            raise EmbeddingError(
                f"Ollama embedding test failed (HTTP {response.status_code}): "
                f"{response.text.strip()}\n"
                "This often happens when the Ollama daemon is outdated or needs a restart.\n"
                "Try: brew services restart ollama"
            )

        data = response.json()
        if "embedding" not in data:
            raise EmbeddingError(
                "Ollama returned an unexpected response (missing 'embedding' field).\n"
                "Try restarting the Ollama service: brew services restart ollama"
            )
        logger.info("Ollama health check passed (model=%s)", self.model)

    async def embed(self, text: str) -> list[float]:
        logger.debug("Embedding text (length=%d)", len(text))
        t0 = time.monotonic()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
        if response.status_code != 200:
            logger.error("Ollama embedding failed (%d): %s", response.status_code, response.text)
            raise EmbeddingError(
                f"Ollama embedding failed ({response.status_code}): {response.text}"
            )
        logger.debug("Embedding complete in %.2fs", time.monotonic() - t0)
        return response.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts reusing a single HTTP client for efficiency."""
        logger.debug("Embedding batch of %d texts", len(texts))
        t0 = time.monotonic()
        async with httpx.AsyncClient() as client:
            results = []
            for i, text in enumerate(texts):
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0,
                )
                if response.status_code != 200:
                    logger.error(
                        "Ollama embedding failed for text %d/%d (%d): %s",
                        i + 1,
                        len(texts),
                        response.status_code,
                        response.text,
                    )
                    raise EmbeddingError(
                        f"Ollama embedding failed ({response.status_code}): {response.text}"
                    )
                results.append(response.json()["embedding"])
        logger.debug(
            "Batch embedding complete: %d texts in %.2fs", len(texts), time.monotonic() - t0
        )
        return results
