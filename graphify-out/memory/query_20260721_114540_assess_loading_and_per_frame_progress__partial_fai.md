---
type: "query"
date: "2026-07-21T11:45:40.178039+00:00"
question: "Assess loading and per-frame progress, partial-failure summaries, an opt-in prompt enhancer, directional animation controls, and a thin MCP server for SpriteGameGen."
contributor: "graphify"
outcome: "useful"
source_nodes: ["AnimatePanel", "GeminiClient", "ProjectStore", "FrameStatus", "frame_prompt", "export"]
---

# Q: Assess loading and per-frame progress, partial-failure summaries, an opt-in prompt enhancer, directional animation controls, and a thin MCP server for SpriteGameGen.

## Answer

Expanded from original query via graph vocab: animate, frame, failure, prompt, direction, sprite, frontend, gemini, service, export, test, architecture. Source verification found that per-frame progress needs an application-service callback plus an HTTP job or stream adapter; partial pipeline exceptions are not all isolated; partial export compresses missing frame indices; reused asset URLs can show stale regenerated images; frame regeneration does not invalidate prior export state; and Gemini timeout_s is stored but not applied. Direction support should separate view mode from direction and first make frame prompts phase-aware. MCP fits after route workflows are extracted into transport-neutral services shared by FastAPI and MCP, with project locking and atomic persistence.

## Outcome

- Signal: useful

## Source Nodes

- AnimatePanel
- GeminiClient
- ProjectStore
- FrameStatus
- frame_prompt
- export