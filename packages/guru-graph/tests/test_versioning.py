from __future__ import annotations

import pytest

from guru_graph.versioning import (
    PROTOCOL_VERSION,
    SCHEMA_VERSION,
    ProtocolVersion,
    VersionNegotiationError,
    check_migration_target,
    negotiate_protocol,
    parse_version,
)


def test_parse_semver():
    v = parse_version("1.2.3")
    assert v == ProtocolVersion(1, 2, 3)


def test_parse_rejects_malformed():
    with pytest.raises(VersionNegotiationError):
        parse_version("1.2")
    with pytest.raises(VersionNegotiationError):
        parse_version("banana")


def test_major_mismatch_refused():
    server = parse_version("1.0.0")
    client = parse_version("2.0.0")
    with pytest.raises(VersionNegotiationError) as exc:
        negotiate_protocol(server=server, client=client)
    assert "MAJOR" in str(exc.value)


def test_minor_older_client_accepted():
    server = parse_version("1.5.0")
    client = parse_version("1.2.0")
    negotiate_protocol(server=server, client=client)  # no raise


def test_minor_newer_client_accepted():
    server = parse_version("1.2.0")
    client = parse_version("1.5.0")
    negotiate_protocol(server=server, client=client)  # no raise


def test_current_constants_are_semver():
    parse_version(PROTOCOL_VERSION)
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1


def test_migration_target_equal_ok():
    check_migration_target(current=1, target=1)  # no raise


def test_migration_target_forward_ok():
    check_migration_target(current=1, target=2)  # no raise


def test_migration_target_backward_refused():
    with pytest.raises(VersionNegotiationError) as exc:
        check_migration_target(current=3, target=2)
    msg = str(exc.value)
    assert "3" in msg and "2" in msg
