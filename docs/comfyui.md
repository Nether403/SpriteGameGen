# Local ComfyUI Provider

SpriteGameGen can connect to an independently operated ComfyUI server only on
`localhost`, `127.0.0.0/8`, or `::1`, with an explicit port. HTTP environment
proxies and redirects are disabled. API and MCP callers cannot provide URLs,
workflow bodies, node IDs, model names, or filesystem paths.

The operator owns the API-format workflow and strict sibling descriptor. Review
both before use: ComfyUI custom nodes and workflows are trusted local code.
SpriteGameGen does not start ComfyUI, install nodes/models, download checkpoints,
or manage Python/CUDA.

Capabilities come from explicit descriptor bindings. Generation, identity edit,
pose reference, and seed are preflighted; unsupported inputs are rejected rather
than ignored. Output bytes/pixels and polling time are bounded. Cancellation may
delete only queued prompt IDs submitted by this process. The global `/interrupt`
endpoint is never used; an unconfirmed running job keeps the provider slot in an
unsafe/indeterminate state for operator review.

Use `scripts/validate_comfyui.py --preflight` before a manual billable/live
quality run. Generation, edit identity, and pose support are promoted separately.
