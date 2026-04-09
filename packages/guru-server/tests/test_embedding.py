import httpx
import pytest

from guru_server.embedding import OllamaEmbedder


class TestOllamaEmbedder:
    def test_embed_single(self, monkeypatch):
        """Test embedding a single text string."""
        fake_response = {"embedding": [0.1] * 768}

        async def fake_post(self, url, **kwargs):
            return httpx.Response(200, json=fake_response)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        import asyncio
        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        result = asyncio.run(embedder.embed("hello world"))
        assert len(result) == 768
        assert result[0] == 0.1

    def test_embed_batch(self, monkeypatch):
        """Test embedding multiple texts."""
        call_count = 0

        async def fake_post(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, json={"embedding": [0.1 * call_count] * 768})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

        import asyncio
        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        results = asyncio.run(embedder.embed_batch(["hello", "world"]))
        assert len(results) == 2
        assert len(results[0]) == 768
        assert len(results[1]) == 768
