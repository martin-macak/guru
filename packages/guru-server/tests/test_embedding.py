import httpx
import pytest

from guru_server.embedding import EmbeddingError, OllamaEmbedder


class TestOllamaEmbedder:
    def test_embed_single(self, monkeypatch):
        """Test embedding a single text string."""
        fake_response = {"embedding": [0.1] * 768}

        async def fake_post(self, url, **kwargs):
            return httpx.Response(200, json=fake_response)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        # Prevent httpx from picking up sandbox SOCKS proxy env vars
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

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
        # Prevent httpx from picking up sandbox SOCKS proxy env vars
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        results = asyncio.run(embedder.embed_batch(["hello", "world"]))
        assert len(results) == 2
        assert len(results[0]) == 768
        assert len(results[1]) == 768


def test_ollama_embedder_has_model_name():
    from guru_server.embedding import OllamaEmbedder

    emb = OllamaEmbedder(model="nomic-embed-text")
    assert emb.model_name == "nomic-embed-text"


def test_ollama_embedder_has_dimensions():
    from guru_server.embedding import OllamaEmbedder

    emb = OllamaEmbedder(model="nomic-embed-text")
    assert emb.dimensions == 768


class TestCheckHealth:
    def test_check_health_success(self, monkeypatch):
        """Health check passes when Ollama returns a valid embedding."""
        fake_response = {"embedding": [0.1] * 768}

        async def fake_post(self, url, **kwargs):
            return httpx.Response(200, json=fake_response)

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        asyncio.run(embedder.check_health())  # should not raise

    def test_check_health_500_error(self, monkeypatch):
        """Health check raises EmbeddingError with guidance on HTTP 500."""

        async def fake_post(self, url, **kwargs):
            return httpx.Response(500, json={"error": "bad request"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        with pytest.raises(EmbeddingError, match="outdated or needs a restart"):
            asyncio.run(embedder.check_health())

    def test_check_health_connect_error(self, monkeypatch):
        """Health check raises EmbeddingError when Ollama is unreachable."""

        async def fake_post(self, url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        with pytest.raises(EmbeddingError, match="Cannot connect to Ollama"):
            asyncio.run(embedder.check_health())

    def test_check_health_timeout(self, monkeypatch):
        """Health check raises EmbeddingError on timeout."""

        async def fake_post(self, url, **kwargs):
            raise httpx.ReadTimeout("timed out")

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        with pytest.raises(EmbeddingError, match="did not respond within"):
            asyncio.run(embedder.check_health())

    def test_check_health_missing_embedding_field(self, monkeypatch):
        """Health check raises EmbeddingError when response lacks 'embedding'."""

        async def fake_post(self, url, **kwargs):
            return httpx.Response(200, json={"something": "else"})

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.delenv("ALL_PROXY", raising=False)
        monkeypatch.delenv("all_proxy", raising=False)

        import asyncio

        embedder = OllamaEmbedder(base_url="http://localhost:11434")
        with pytest.raises(EmbeddingError, match="unexpected response"):
            asyncio.run(embedder.check_health())
