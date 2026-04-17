"""Protocol and schema version constants and negotiation helpers.

See spec §Schema, versioning & compatibility. Three axes:
  - PROTOCOL_VERSION: semver wire-protocol between GraphClient and daemon
  - SCHEMA_VERSION: integer DB schema version (migrations)
  - backend_version: Neo4j engine version (reported, not negotiated)
"""

from __future__ import annotations

from dataclasses import dataclass

PROTOCOL_VERSION = "1.0.0"
SCHEMA_VERSION = 1

PROTOCOL_HEADER = "X-Guru-Graph-Protocol"


class VersionNegotiationError(RuntimeError):
    """Raised when version constraints cannot be satisfied."""


@dataclass(frozen=True)
class ProtocolVersion:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_version(s: str) -> ProtocolVersion:
    parts = s.split(".")
    if len(parts) != 3:
        raise VersionNegotiationError(f"expected X.Y.Z semver, got {s!r}")
    try:
        major, minor, patch = (int(p) for p in parts)
    except ValueError as e:
        raise VersionNegotiationError(f"non-integer component in {s!r}") from e
    return ProtocolVersion(major, minor, patch)


def negotiate_protocol(*, server: ProtocolVersion, client: ProtocolVersion) -> None:
    """Accept the request if client and server share the same MAJOR.

    Raises VersionNegotiationError otherwise. Tolerance within a MAJOR is
    each side's responsibility (unknown fields ignored, missing features
    degraded).
    """
    if server.major != client.major:
        raise VersionNegotiationError(f"protocol MAJOR mismatch: server={server}, client={client}")


def check_migration_target(*, current: int, target: int) -> None:
    """Guard against an older daemon running against a newer store.

    Current > target means someone downgraded the daemon. We refuse with a
    clear error — no automatic downgrade, no silent data loss.
    """
    if current > target:
        raise VersionNegotiationError(
            f"graph store is schema v{current}; this daemon supports up to "
            f"v{target}. Upgrade the daemon or wipe the graph data dir."
        )
