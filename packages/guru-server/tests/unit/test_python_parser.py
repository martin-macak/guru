from __future__ import annotations

from pathlib import Path

import pytest

from guru_core.types import MatchConfig, Rule
from guru_server.ingestion.python import PythonParser


@pytest.fixture
def rule():
    return Rule(ruleName="code", match=MatchConfig(glob="**/*.py"))


def test_supports_python_files_only(tmp_path: Path):
    p = PythonParser()
    assert p.supports(tmp_path / "x.py")
    assert not p.supports(tmp_path / "x.md")


def test_name_is_python():
    assert PythonParser().name == "python"


def test_parse_emits_document_and_module(tmp_path: Path, rule):
    f = tmp_path / "pkg" / "mod.py"
    f.parent.mkdir()
    f.write_text("def foo(): pass\n")
    (tmp_path / "pkg" / "__init__.py").write_text("")

    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="pkg/mod.py")

    assert result.document.label == "Document"
    assert result.document.node_id == "kb::pkg/mod.py"
    assert result.document.properties["language"] == "python"
    assert result.document.properties["file_type"] == "code"
    assert result.document.properties["parser_name"] == "python"

    module_nodes = [n for n in result.nodes if n.label == "Module"]
    assert any(n.properties["qualname"] == "pkg.mod" for n in module_nodes)


def test_parse_emits_class_and_methods(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text(
        '''\
class Foo:
    """Docs."""
    def bar(self):
        pass
    def baz(self):
        pass
'''
    )
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    classes = [n for n in result.nodes if n.label == "Class"]
    methods = [n for n in result.nodes if n.label == "Method"]
    assert any(c.properties["qualname"] == "a.Foo" for c in classes)
    assert {m.properties["qualname"] for m in methods} == {"a.Foo.bar", "a.Foo.baz"}

    # Class-contains-method edges
    method_edges = [
        e for e in result.edges if e.rel_type == "CONTAINS" and e.from_id == "kb::a.Foo"
    ]
    assert {e.to_id for e in method_edges} == {"kb::a.Foo.bar", "kb::a.Foo.baz"}


def test_parse_emits_inheritance_edge(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("class Base: pass\nclass Derived(Base): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "inherits_from"]
    assert len(edges) == 1
    edge = edges[0]
    assert edge.from_id == "kb::a.Derived"
    assert edge.to_id == "kb::a.Base"


def test_parse_emits_imports_edge(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    (tmp_path / "b.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("from b import x\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "imports"]
    assert len(edges) == 1
    assert edges[0].from_id == "kb::a"
    # b is first-party, so it resolves to a real module id (no __external__).
    assert edges[0].to_id == "kb::b"


def test_parse_emits_external_module_placeholder(tmp_path: Path, rule):
    f = tmp_path / "a.py"
    f.write_text("import os\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    placeholders = [
        n for n in result.nodes if n.label == "Module" and n.properties.get("unresolved")
    ]
    assert any(n.properties["qualname"] == "os" for n in placeholders)
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "imports"]
    assert any("__external__" in e.to_id for e in edges)


def test_parse_emits_code_chunks_with_qualname(tmp_path: Path, rule):
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    '''d'''\n    return 1\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    assert any(c.kind == "code" and c.artifact_qualname == "kb::a.foo" for c in result.chunks)
    # Module-level chunk also present
    assert any(c.kind == "code" and c.artifact_qualname == "kb::a" for c in result.chunks)


def test_parse_handles_decorated_functions(tmp_path: Path, rule):
    """``@decorator`` def foo(): ... should still be discovered."""
    f = tmp_path / "a.py"
    f.write_text("@my_dec\ndef foo(): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    fns = [n for n in result.nodes if n.label == "Function"]
    assert any(fn.properties["name"] == "foo" for fn in fns)


def test_parse_emits_unresolved_base_placeholder(tmp_path: Path, rule):
    """Bases that can't be resolved get a placeholder Class node."""
    f = tmp_path / "a.py"
    f.write_text("class Derived(SomethingExternal): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    placeholders = [
        n for n in result.nodes if n.label == "Class" and n.properties.get("unresolved")
    ]
    assert any("SomethingExternal" in n.properties["qualname"] for n in placeholders)
    # Edge present to the placeholder
    edges = [e for e in result.edges if e.rel_type == "RELATES" and e.kind == "inherits_from"]
    assert len(edges) == 1
    assert "__unresolved__" in edges[0].to_id


def test_parse_module_contains_edges(tmp_path: Path, rule):
    """Document -> Module and Module -> top-level symbol CONTAINS edges."""
    (tmp_path / "__init__.py").write_text("")
    f = tmp_path / "a.py"
    f.write_text("class Foo: pass\ndef bar(): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="a.py")
    contains = [e for e in result.edges if e.rel_type == "CONTAINS"]
    pairs = {(e.from_id, e.to_id) for e in contains}
    assert ("kb::a.py", "kb::a") in pairs
    assert ("kb::a", "kb::a.Foo") in pairs
    assert ("kb::a", "kb::a.bar") in pairs


def test_parse_handles_syntax_errors(tmp_path: Path, rule):
    """Tree-sitter is forgiving: malformed Python should still emit a Document + Module."""
    f = tmp_path / "broken.py"
    f.write_text("def foo(:\n    pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(f, rule, kb_name="kb", rel_path="broken.py")
    assert result.document.label == "Document"
    assert any(n.label == "Module" for n in result.nodes)


def test_parse_init_py_uses_package_qualname(tmp_path: Path, rule):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    init = pkg / "__init__.py"
    init.write_text("def boot(): pass\n")
    p = PythonParser(package_roots=[tmp_path])
    result = p.parse(init, rule, kb_name="kb", rel_path="pkg/__init__.py")
    module_nodes = [n for n in result.nodes if n.label == "Module"]
    assert any(n.properties["qualname"] == "pkg" for n in module_nodes)
