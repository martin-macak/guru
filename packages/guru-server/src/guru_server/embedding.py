from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

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
