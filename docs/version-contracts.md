# Version Contracts

SpriteGameGen versions application code and every persisted or exchanged format
independently. A package release does not implicitly change a data format.

| Contract | Current version | Compatibility rule |
|---|---:|---|
| Python/frontend package | 0.1.0 | Semantic Versioning describes user-visible software changes. |
| Filesystem project manifest | 2 | V1 is migrated in memory; the first successful mutation writes V2. Future versions are rejected, never downgraded. |
| Character bundle | 1 | Readers must reject unsupported versions. Bundle V1 remains deterministic. |
| Action pack | 1 | Strict data-only JSON; unknown fields and versions are rejected. |
| Recipe | 1 | Credential-free strict JSON; runners preflight the complete recipe before provider work. |
| Batch state | 1 | Atomic locked state; changed recipe digests are rejected. |

Browser URLs, credentials, provider endpoints, environment values, and absolute
paths are not part of portable formats. Compatibility projections in HTTP and
MCP are transport adapters and are not dual-written into the V2 manifest.
