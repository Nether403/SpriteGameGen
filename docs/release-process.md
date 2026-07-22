# Release Process

1. Review `CHANGELOG.md` and classify the package change with Semantic Versioning.
2. Confirm any manifest, bundle, action-pack, recipe, or batch-state change has an explicit compatibility rule in `docs/version-contracts.md`.
3. Run the credential-free verification commands documented in `CONTRIBUTING.md` on Windows and Linux CI.
4. Run manual cloud-provider, ComfyUI, and Godot gates only for capabilities claimed by the release. Never put credentials in release artifacts or logs.
5. Inspect the source archive for generated projects, browser captures, workflows, credentials, and local paths.
6. Tag the reviewed commit with an annotated `vMAJOR.MINOR.PATCH` tag and publish release notes from the curated changelog.

Rollback is a normal release operation: retain the previous tag and artifacts,
and never rewrite persisted projects to an older schema.
