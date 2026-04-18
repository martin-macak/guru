from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from guru_core.types import MatchConfig, Rule
from guru_server.ingestion.openapi import OpenApiParser


@pytest.fixture
def rule():
    return Rule(ruleName="api", match=MatchConfig(glob="**/openapi.yaml"))


def _write_yaml(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _minimal_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Demo API", "version": "1.0.0"},
        "paths": {
            "/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "summary": "Get user by id",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/UserResource"},
                                },
                            },
                        },
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "UserResource": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            }
        },
    }


def test_supports_yaml_and_json(tmp_path: Path):
    p = OpenApiParser()
    assert p.supports(tmp_path / "openapi.yaml")
    assert p.supports(tmp_path / "openapi.yml")
    assert p.supports(tmp_path / "openapi.json")
    assert p.supports(tmp_path / "API.YAML")  # case-insensitive
    assert not p.supports(tmp_path / "README.md")
    assert not p.supports(tmp_path / "x.py")


def test_name_is_openapi():
    assert OpenApiParser().name == "openapi"


def test_parse_emits_spec_node(tmp_path: Path, rule):
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, _minimal_spec())
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    assert result.document.label == "OpenApiSpec"
    assert result.document.node_id == "kb::openapi.yaml"
    assert result.document.properties["valid"] is True
    assert result.document.properties["openapi_version"] == "3.0.3"
    assert result.document.properties["title"] == "Demo API"
    assert result.document.properties["parser_name"] == "openapi"
    assert result.document.properties["language"] == "yaml"


def test_parse_emits_one_operation_per_path_method(tmp_path: Path, rule):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {
            "/a": {
                "get": {"summary": "a-get"},
                "post": {"summary": "a-post"},
            },
            "/b": {
                "get": {"summary": "b-get"},
                "delete": {"summary": "b-delete"},
            },
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    ops = [n for n in result.nodes if n.label == "OpenApiOperation"]
    assert len(ops) == 4
    # Operation qualname scheme: {kb}::{rel_path}::{path}::{method}
    ids = {n.node_id for n in ops}
    assert ids == {
        "kb::openapi.yaml::/a::get",
        "kb::openapi.yaml::/a::post",
        "kb::openapi.yaml::/b::get",
        "kb::openapi.yaml::/b::delete",
    }
    # CONTAINS from the spec to every operation
    contains = [
        e for e in result.edges if e.rel_type == "CONTAINS" and e.from_id == "kb::openapi.yaml"
    ]
    assert {e.to_id for e in contains} >= ids


def test_parse_emits_one_schema_per_components_schema(tmp_path: Path, rule):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "A": {"type": "object"},
                "B": {"type": "string"},
                "C": {"type": "integer"},
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    schemas = [n for n in result.nodes if n.label == "OpenApiSchema"]
    assert len(schemas) == 3
    names = {n.properties["name"] for n in schemas}
    assert names == {"A", "B", "C"}

    contains = [
        e
        for e in result.edges
        if e.rel_type == "CONTAINS" and e.to_id.startswith("kb::openapi.yaml::components/schemas/")
    ]
    assert len(contains) == 3


def test_parse_emits_local_ref_edge(tmp_path: Path, rule):
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, _minimal_spec())
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    ref_edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "references"]
    op_id = "kb::openapi.yaml::/users/{id}::get"
    schema_id = "kb::openapi.yaml::components/schemas/UserResource"
    assert any(e.from_id == op_id and e.to_id == schema_id for e in ref_edges)


def test_parse_emits_schema_to_schema_ref_edge(tmp_path: Path, rule):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Outer": {
                    "type": "object",
                    "properties": {
                        "inner": {"$ref": "#/components/schemas/Inner"},
                    },
                },
                "Inner": {"type": "object"},
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    ref_edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "references"]
    assert any(
        e.from_id == "kb::openapi.yaml::components/schemas/Outer"
        and e.to_id == "kb::openapi.yaml::components/schemas/Inner"
        for e in ref_edges
    )


def test_parse_handles_circular_ref_without_loop(tmp_path: Path, rule):
    """Node references itself via properties.next — parse must terminate."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "next": {"$ref": "#/components/schemas/Node"},
                    },
                }
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    schemas = [n for n in result.nodes if n.label == "OpenApiSchema"]
    assert len(schemas) == 1
    # Self-reference edge is present
    ref_edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "references"]
    node_id = "kb::openapi.yaml::components/schemas/Node"
    assert any(e.from_id == node_id and e.to_id == node_id for e in ref_edges)


def test_parse_collapses_oneof_to_shape_property(tmp_path: Path, rule):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Pet": {
                    "oneOf": [
                        {"$ref": "#/components/schemas/Cat"},
                        {"$ref": "#/components/schemas/Dog"},
                    ]
                },
                "Cat": {"type": "object"},
                "Dog": {"type": "object"},
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")
    pet_nodes = [
        n for n in result.nodes if n.label == "OpenApiSchema" and n.properties.get("name") == "Pet"
    ]
    assert len(pet_nodes) == 1
    assert pet_nodes[0].properties["shape"] == "oneOf"


def test_parse_collapses_anyof_and_allof_too(tmp_path: Path, rule):
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Any": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                "All": {"allOf": [{"type": "object"}, {"type": "object"}]},
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")
    schemas = {n.properties["name"]: n for n in result.nodes if n.label == "OpenApiSchema"}
    assert schemas["Any"].properties["shape"] == "anyOf"
    assert schemas["All"].properties["shape"] == "allOf"


def test_parse_handles_malformed_yaml(tmp_path: Path, rule):
    f = tmp_path / "openapi.yaml"
    f.write_text("key: value:\n: bad\n  -\n - : -\n", encoding="utf-8")
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    assert result.document.label == "Document"
    assert result.document.properties["valid"] is False
    assert result.document.properties.get("error")
    assert result.chunks == []
    assert result.nodes == []
    assert result.edges == []


def test_parse_supports_json(tmp_path: Path, rule):
    spec = _minimal_spec()
    f = tmp_path / "openapi.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.json")

    assert result.document.label == "OpenApiSpec"
    assert result.document.properties["language"] == "json"
    ops = [n for n in result.nodes if n.label == "OpenApiOperation"]
    schemas = [n for n in result.nodes if n.label == "OpenApiSchema"]
    assert len(ops) == 1
    assert len(schemas) == 1
    # Chunk language reflects file type
    assert all(c.language == "json" for c in result.chunks)


def test_parse_supports_openapi_31(tmp_path: Path, rule):
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "T31", "version": "2"},
        "paths": {
            "/things": {
                "get": {
                    "summary": "list things",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "webhooks": {
            "newThing": {
                "post": {
                    "summary": "a webhook",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Thing": {"type": "object"},
            }
        },
    }
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    assert result.document.label == "OpenApiSpec"
    assert result.document.properties["openapi_version"] == "3.1.0"
    ops = [n for n in result.nodes if n.label == "OpenApiOperation"]
    assert any(n.properties["path"] == "/things" for n in ops)
    schemas = [n for n in result.nodes if n.label == "OpenApiSchema"]
    assert any(n.properties["name"] == "Thing" for n in schemas)


def test_parse_emits_chunks_with_correct_kind_and_qualname(tmp_path: Path, rule):
    f = tmp_path / "openapi.yaml"
    _write_yaml(f, _minimal_spec())
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="openapi.yaml")

    op_chunks = [c for c in result.chunks if c.kind == "openapi_operation"]
    schema_chunks = [c for c in result.chunks if c.kind == "openapi_schema"]
    assert len(op_chunks) == 1
    assert len(schema_chunks) == 1

    op = op_chunks[0]
    assert op.artifact_qualname == "kb::openapi.yaml::/users/{id}::get"
    assert op.parent_document_id == "kb::openapi.yaml"
    assert op.language == "yaml"
    assert "getUser" in op.content or "Get user by id" in op.content

    sch = schema_chunks[0]
    assert sch.artifact_qualname == "kb::openapi.yaml::components/schemas/UserResource"
    assert sch.parent_document_id == "kb::openapi.yaml"


def test_parse_unrecognised_yaml_passthrough(tmp_path: Path, rule):
    """A non-OpenAPI YAML file should produce just a Document node (openapi=False)."""
    f = tmp_path / "ci.yaml"
    _write_yaml(
        f,
        {
            "jobs": {
                "build": {"runs-on": "ubuntu-latest", "steps": [{"run": "make test"}]},
            }
        },
    )
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="ci.yaml")

    assert result.document.label == "Document"
    assert result.document.properties.get("openapi") is False
    assert result.chunks == []
    assert result.nodes == []
    assert result.edges == []


def test_parse_cross_file_ref_emits_placeholder_when_missing(tmp_path: Path, rule):
    """Cross-file $ref to a nonexistent file creates a placeholder node + edge."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "T", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "Main": {"$ref": "./missing.yaml#/components/schemas/Other"},
            }
        },
    }
    (tmp_path / "api").mkdir()
    f = tmp_path / "api" / "openapi.yaml"
    _write_yaml(f, spec)
    result = OpenApiParser().parse(f, rule, kb_name="kb", rel_path="api/openapi.yaml")

    placeholders = [n for n in result.nodes if n.properties.get("unresolved")]
    assert placeholders, "expected a placeholder node for the missing cross-file ref"
    assert all(n.label == "OpenApiSchema" for n in placeholders)
    # Edge from Main → placeholder
    ref_edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "references"]
    from_id = "kb::api/openapi.yaml::components/schemas/Main"
    assert any(e.from_id == from_id and e.to_id == placeholders[0].node_id for e in ref_edges)
