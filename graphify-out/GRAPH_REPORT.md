# Graph Report - .  (2026-07-21)

## Corpus Check
- Corpus is ~19,830 words - fits in a single context window. You may not need a graph.

## Summary
- 541 nodes · 976 edges · 31 communities (28 shown, 3 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 168 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Gemini AI Client|Gemini AI Client]]
- [[_COMMUNITY_Frontend API Client|Frontend API Client]]
- [[_COMMUNITY_App Config and Deps|App Config and Deps]]
- [[_COMMUNITY_Image Trim Pipeline|Image Trim Pipeline]]
- [[_COMMUNITY_Animate Route Tests|Animate Route Tests]]
- [[_COMMUNITY_Generate Route API|Generate Route API]]
- [[_COMMUNITY_Design Spec and Plan|Design Spec and Plan]]
- [[_COMMUNITY_Frontend Dependencies|Frontend Dependencies]]
- [[_COMMUNITY_Sprite Sheet Packer|Sprite Sheet Packer]]
- [[_COMMUNITY_TypeScript Compiler Config|TypeScript Compiler Config]]
- [[_COMMUNITY_Pixelate Pipeline|Pixelate Pipeline]]
- [[_COMMUNITY_Domain Model Validation|Domain Model Validation]]
- [[_COMMUNITY_Export Multi-Frame Tests|Export Multi-Frame Tests]]
- [[_COMMUNITY_Atlas Metadata Writer|Atlas Metadata Writer]]
- [[_COMMUNITY_Prompt Builder|Prompt Builder]]
- [[_COMMUNITY_Background Removal|Background Removal]]
- [[_COMMUNITY_Project Store Tests|Project Store Tests]]
- [[_COMMUNITY_Config Validation Tests|Config Validation Tests]]
- [[_COMMUNITY_Export Route Models|Export Route Models]]
- [[_COMMUNITY_Animate Route API|Animate Route API]]
- [[_COMMUNITY_Prompt Builder Tests|Prompt Builder Tests]]
- [[_COMMUNITY_Frame Domain Models|Frame Domain Models]]
- [[_COMMUNITY_Node TypeScript Config|Node TypeScript Config]]
- [[_COMMUNITY_Project Manifest Model|Project Manifest Model]]
- [[_COMMUNITY_Product Root Concept|Product Root Concept]]

## God Nodes (most connected - your core abstractions)
1. `ProjectStore` - 34 edges
2. `GeminiClient` - 25 edges
3. `Style` - 20 edges
4. `GeminiError` - 20 edges
5. `compilerOptions` - 17 edges
6. `pack()` - 16 edges
7. `_generate()` - 16 edges
8. `SafetyBlockedError` - 15 edges
9. `RegenerateFrameRequest` - 14 edges
10. `DeleteFrameRequest` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Generate Animate Export Workflow` --semantically_similar_to--> `Stage 2 Animation`  [INFERRED] [semantically similar]
  README.md → docs/superpowers/specs/2026-07-20-sprite-game-asset-tool-design.md
- `Deterministic Python Pipeline` --semantically_similar_to--> `Pipeline Layer`  [INFERRED] [semantically similar]
  README.md → docs/superpowers/specs/2026-07-20-sprite-game-asset-tool-design.md
- `Global Region Model Risk Resolution` --semantically_similar_to--> `Gemini Global Endpoint`  [INFERRED] [semantically similar]
  docs/superpowers/plans/2026-07-20-sprite-game-asset-tool-implementation-plan.md → README.md
- `main()` --calls--> `build_default_client()`  [INFERRED]
  scripts/smoke_generate.py → backend/app/services/gemini_client.py
- `test_style_enum_values()` --calls--> `Style`  [INFERRED]
  backend/tests/test_models.py → backend/app/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Three Frame Consistency Decisions** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_base_anchored_editing, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_shared_bounding_box, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_regenerate_per_frame [EXTRACTED 1.00]
- **Two-Tier Architecture Layers** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_two_tier_architecture, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_ai_layer, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_pipeline_layer, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_filesystem_storage [EXTRACTED 1.00]
- **Testing and Verification Surface** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_testing_strategy, docs_superpowers_plans_2026_07_20_sprite_game_asset_tool_implementation_plan_tdd_approach, readme_smoke_generate, docs_superpowers_plans_2026_07_20_sprite_game_asset_tool_implementation_plan_dependency_injection [INFERRED 0.85]

## Communities (31 total, 3 thin omitted)

### Community 0 - "Gemini AI Client"
Cohesion: 0.09
Nodes (44): Any, Art style — differs mainly in one post-processing step (quantize)., Style, GeminiClient, GeminiError, GeminiTimeoutError, _is_transient(), Image (+36 more)

### Community 1 - "Frontend API Client"
Cohesion: 0.10
Nodes (32): animate(), AnimateResult, ApiError, deleteFrame(), deleteProject(), ExportFormat, exportProject(), ExportResult (+24 more)

### Community 2 - "App Config and Deps"
Cohesion: 0.08
Nodes (27): get_settings(), Application configuration.  Auth model: Vertex AI / Google Agent Platform. Prefe, Return cached settings, failing loudly on invalid/missing auth config., Settings, _default_gemini(), _default_store(), get_gemini_client(), get_store() (+19 more)

### Community 3 - "Image Trim Pipeline"
Cohesion: 0.11
Nodes (36): align_to_bbox(), _alpha_array(), autocrop(), content_bbox(), DegenerateBBoxError, EmptyImageError, Image, Alpha-based trimming and shared-bbox alignment.  Pure functions: ``Image -> Imag (+28 more)

### Community 4 - "Animate Route Tests"
Cohesion: 0.10
Nodes (24): app_and_store(), _fake_remover(), FakeGemini, _generate(), _make(), Image, Stage 2 route tests: /animate, /presets (fake Gemini edit)., Shared-bbox alignment: every successful frame must be the same size so the     c (+16 more)

### Community 5 - "Generate Route API"
Cohesion: 0.07
Nodes (17): create_app(), Remover, FastAPI application factory + wiring.  ``create_app`` builds the app so tests ca, generate(), _parse_style(), Request, Style, POST /generate — text/image -> clean, trimmed sprite (Stage 1).  Pipeline: gemin (+9 more)

### Community 6 - "Design Spec and Plan"
Cohesion: 0.07
Nodes (32): Seam Dependency Injection, Global Region Model Risk Resolution, google-genai SDK Call Shape, Sprite Game Asset Tool Implementation Plan, Partial Animation Failure Tolerance, Pipeline Purity Convention, TDD Implementation Approach, AI Layer Gemini (+24 more)

### Community 7 - "Frontend Dependencies"
Cohesion: 0.09
Nodes (22): dependencies, react, react-dom, zustand, devDependencies, jsdom, @testing-library/react, @types/react (+14 more)

### Community 8 - "Sprite Sheet Packer"
Cohesion: 0.19
Nodes (19): _grid_cols(), pack(), Image, Layout, Sprite-sheet packer (pure, deterministic).  Assumes frames are already uniformly, Pack frames into a single sheet.      Args:         frames: uniformly-sized RGBA, _frames(), Sprite-sheet packer: grid layout + pixel offsets (pure, deterministic). (+11 more)

### Community 9 - "TypeScript Compiler Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+11 more)

### Community 10 - "Pixelate Pipeline"
Cohesion: 0.20
Nodes (17): Image, quantize(), Pixel-art conversion: integer downscale + color quantization (pure).  This is th, Reduce ``img`` to a pixel-art look.      Steps: optional integer downscale (near, _distinct_opaque_colors(), _gradient(), Image, Pixelate pipeline: color quantization + integer downscale/upscale (pure). (+9 more)

### Community 11 - "Domain Model Validation"
Cohesion: 0.16
Nodes (16): AnimateRequest, ExportOptions, Options for packing frames into a sheet + atlas., Request to expand a project's base sprite into an animation (spec §3).      ``ac, Domain model validation., test_animate_request_defaults(), test_animate_request_explicit(), test_animate_request_rejects_empty_action() (+8 more)

### Community 12 - "Export Multi-Frame Tests"
Cohesion: 0.23
Nodes (11): _animated_project(), app_and_store(), _fake_remover(), FakeGemini, Image, Task 16 — multi-frame sprite-sheet export (JSON + XML, grid/padding options).  B, _read_atlas(), test_export_multi_frame_grid_cols_honored() (+3 more)

### Community 13 - "Atlas Metadata Writer"
Cohesion: 0.22
Nodes (13): _json_atlas(), Layout, Atlas metadata writer (pure, byte-stable).  Serializes a packer layout to either, Serialize ``layout`` for a sheet of ``sheet_size`` to ``fmt`` ('json'|'xml')., write_atlas(), _xml_atlas(), Atlas metadata writer: JSON (golden) + XML, byte-stable., test_json_content_shape() (+5 more)

### Community 14 - "Prompt Builder"
Cohesion: 0.14
Nodes (12): build_generate_prompt(), frame_prompt(), get_preset(), list_presets(), Style, Prompt construction (pure strings).  Style directives and per-frame animation pr, Compose the text-to-image prompt from a user description + style directives., Return the preset action table (copied so callers can't mutate it). (+4 more)

### Community 15 - "Background Removal"
Cohesion: 0.19
Nodes (11): _default_remover(), Image, Remover, Background removal wrapper.  The heavy ``rembg`` session is injected so unit tes, Remove the background using rembg. Imported lazily to avoid the heavy     onnxru, Return ``img`` with its background removed, always as an RGBA image.      Args:, remove(), Background removal wrapper (injected remover — no real rembg load in tests). (+3 more)

### Community 17 - "Config Validation Tests"
Cohesion: 0.36
Nodes (11): _clear_env(), _fresh_config(), Config module: fail-loud validation of Vertex AI service-account auth., Reload the module so the cached settings don't leak between tests., test_get_settings_is_cached(), test_missing_credentials_file_fails_loud(), test_missing_project_fails_loud(), test_model_ids_and_region_overridable() (+3 more)

### Community 18 - "Export Route Models"
Cohesion: 0.29
Nodes (9): ExportFormat, FrameStatus, Pydantic domain models (spec §3).  These describe the persisted project manifest, A generated frame either succeeded or failed (partial-failure tolerant)., export(), ExportRequest, POST /export — pack a project's frames into a sheet + atlas.  Stage 1 exports a, Enum (+1 more)

### Community 19 - "Animate Route API"
Cohesion: 0.24
Nodes (9): animate(), _fit_to_size(), Image, Request, POST /animate — expand a project's base sprite into an animation (Stage 2).  For, Center ``img``'s content on a transparent canvas of ``size``.      A regenerated, Clamp the requested frame count into the preset's [min, max] window, or     fall, regenerate_frame() (+1 more)

### Community 21 - "Frame Domain Models"
Cohesion: 0.27
Nodes (10): Frame, One frame of an animation (a single static sprite is one frame at index 0)., delete_frame(), DeleteFrameRequest, Regenerate a single frame in-place (FrameStrip escape hatch, spec §4).      The, Delete a single frame and re-index the remainder (FrameStrip escape hatch)., RegenerateFrameRequest, test_frame_defaults_and_construction() (+2 more)

### Community 22 - "Node TypeScript Config"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, composite, module, moduleResolution, skipLibCheck, strict, include

### Community 23 - "Project Manifest Model"
Cohesion: 0.33
Nodes (6): Project, Filesystem project manifest, persisted as ``project.json``.      ``action`` and, test_project_animation_fields_optional(), test_project_construction(), test_list_projects(), test_manifest_roundtrip()

## Knowledge Gaps
- **58 isolated node(s):** `sprite-game-asset-tool`, `name`, `private`, `version`, `type` (+53 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ProjectStore` connect `App Config and Deps` to `Animate Route Tests`, `Generate Route API`, `Export Multi-Frame Tests`, `Project Store Tests`, `Export Route Models`, `Animate Route API`, `Frame Domain Models`, `Project Manifest Model`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `EmptyImageError` connect `Image Trim Pipeline` to `Frame Domain Models`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `RegenerateFrameRequest` connect `Frame Domain Models` to `Gemini AI Client`, `App Config and Deps`, `Image Trim Pipeline`, `Domain Model Validation`, `Export Route Models`, `Animate Route API`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 11 inferred relationships involving `ProjectStore` (e.g. with `DeleteFrameRequest` and `RegenerateFrameRequest`) actually correct?**
  _`ProjectStore` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `GeminiClient` (e.g. with `DeleteFrameRequest` and `RegenerateFrameRequest`) actually correct?**
  _`GeminiClient` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `Style` (e.g. with `DeleteFrameRequest` and `RegenerateFrameRequest`) actually correct?**
  _`Style` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `GeminiError` (e.g. with `DeleteFrameRequest` and `RegenerateFrameRequest`) actually correct?**
  _`GeminiError` has 13 INFERRED edges - model-reasoned connections that need verification._