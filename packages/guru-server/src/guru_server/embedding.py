from __future__ import annotations

import httpx


class EmbeddingError(RuntimeError):
    pass


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )
        if response.status_code != 200:
            raise EmbeddingError(
                f"Ollama embedding failed ({response.status_code}): {response.text}"
            )
        return response.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts reusing a single HTTP client for efficiency."""
        async with httpx.AsyncClient() as client:
            results = []
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=30.0,
                )
                if response.status_code != 200:
                    raise EmbeddingError(
                        f"Ollama embedding failed ({response.status_code}): {response.text}"
                    )
                results.append(response.json()["embedding"])
            return results
