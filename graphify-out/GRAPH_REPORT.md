# Graph Report - .  (2026-07-21)

## Corpus Check
- 72 files · ~41,430 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 947 nodes · 2362 edges · 48 communities (40 shown, 8 thin omitted)
- Extraction: 67% EXTRACTED · 33% INFERRED · 0% AMBIGUOUS · INFERRED: 771 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_MCP Server Core|MCP Server Core]]
- [[_COMMUNITY_Gemini Client|Gemini Client]]
- [[_COMMUNITY_Deps And Settings|Deps And Settings]]
- [[_COMMUNITY_Config And Live Validation|Config And Live Validation]]
- [[_COMMUNITY_Projects API Routes|Projects API Routes]]
- [[_COMMUNITY_Live Model Validation Docs|Live Model Validation Docs]]
- [[_COMMUNITY_Animate Route Tests|Animate Route Tests]]
- [[_COMMUNITY_Trim Pipeline|Trim Pipeline]]
- [[_COMMUNITY_Animate Routes|Animate Routes]]
- [[_COMMUNITY_Azure Image Provider|Azure Image Provider]]
- [[_COMMUNITY_Stage1 Route Tests|Stage1 Route Tests]]
- [[_COMMUNITY_Frontend Package Deps|Frontend Package Deps]]
- [[_COMMUNITY_Frontend API Client|Frontend API Client]]
- [[_COMMUNITY_Implementation Plan Concepts|Implementation Plan Concepts]]
- [[_COMMUNITY_Sprite Packer|Sprite Packer]]
- [[_COMMUNITY_Pixelate Pipeline|Pixelate Pipeline]]
- [[_COMMUNITY_Frontend TSConfig|Frontend TSConfig]]
- [[_COMMUNITY_Prompt Builder|Prompt Builder]]
- [[_COMMUNITY_Project Store Tests|Project Store Tests]]
- [[_COMMUNITY_Prompt Builder Tests|Prompt Builder Tests]]
- [[_COMMUNITY_Project Browser UI|Project Browser UI]]
- [[_COMMUNITY_Atlas Writer|Atlas Writer]]
- [[_COMMUNITY_Background Removal|Background Removal]]
- [[_COMMUNITY_Config Tests|Config Tests]]
- [[_COMMUNITY_Pose Reference Guides|Pose Reference Guides]]
- [[_COMMUNITY_Export Panel UI|Export Panel UI]]
- [[_COMMUNITY_Animate Panel UI|Animate Panel UI]]
- [[_COMMUNITY_Project State Types|Project State Types]]
- [[_COMMUNITY_Direction Controls UI|Direction Controls UI]]
- [[_COMMUNITY_Node TSConfig|Node TSConfig]]
- [[_COMMUNITY_Frame Strip UI|Frame Strip UI]]
- [[_COMMUNITY_Generate Panel UI|Generate Panel UI]]
- [[_COMMUNITY_Shared Image Types|Shared Image Types]]
- [[_COMMUNITY_Frame Edit Helpers|Frame Edit Helpers]]
- [[_COMMUNITY_MCP Audit Concepts|MCP Audit Concepts]]
- [[_COMMUNITY_MCP Smoke Script|MCP Smoke Script]]
- [[_COMMUNITY_Typing Any|Typing Any]]
- [[_COMMUNITY_Image Type Node|Image Type Node]]
- [[_COMMUNITY_Global Region Risk|Global Region Risk]]
- [[_COMMUNITY_Exception Type|Exception Type]]
- [[_COMMUNITY_Product Name|Product Name]]
- [[_COMMUNITY_Project Concept|Project Concept]]

## God Nodes (most connected - your core abstractions)
1. `ProjectStore` - 77 edges
2. `SpriteService` - 68 edges
3. `ViewMode` - 53 edges
4. `Style` - 50 edges
5. `Direction` - 50 edges
6. `Project` - 39 edges
7. `SpriteServiceError` - 37 edges
8. `AnimationResult` - 37 edges
9. `Frame` - 36 edges
10. `AnimateRequest` - 36 edges

## Surprising Connections (you probably didn't know these)
- `SpriteService` --semantically_similar_to--> `SpriteService Application Boundary`  [INFERRED] [semantically similar]
  README.md → tasks/plan.md
- `Hyperagent Not Listed as Supported` --semantically_similar_to--> `MCP tools/list Audit Distinction`  [INFERRED] [semantically similar]
  docs/live-model-validation.md → AGENTS.md
- `sprite-mcp Local MCP Server` --semantically_similar_to--> `FastMCP Stdio Server`  [INFERRED] [semantically similar]
  README.md → tasks/plan.md
- `Hyperagent Experimental Provider` --semantically_similar_to--> `Hyperagent Not Listed as Supported`  [INFERRED] [semantically similar]
  README.md → docs/live-model-validation.md
- `GeminiClient` --semantically_similar_to--> `GeminiClient`  [INFERRED] [semantically similar]
  graphify-out/memory/query_20260721_114540_assess_loading_and_per_frame_progress__partial_fai.md → tasks/plan.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Generate Animate Export Product Flow** — readme_generate_animate_export_workflow, readme_ai_sprite_game_asset_tool, readme_deterministic_image_pipeline, tasks_plan_implementation_roadmap [EXTRACTED 1.00]
- **Shared SpriteService HTTP and MCP Adapters** — tasks_plan_spriteservice, tasks_plan_fastmcp_stdio_server, readme_sprite_mcp, readme_spriteservice [EXTRACTED 1.00]
- **Live Model Validation Acceptance Bundle** — docs_live_model_validation_live_gemini_model_validation, docs_live_model_validation_manual_quality_rubric, docs_live_model_validation_safety_block_probe, docs_live_model_validation_burst_quota_recovery, tasks_todo_live_validation_findings [EXTRACTED 1.00]
- **Three Frame Consistency Decisions** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_base_anchored_editing, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_shared_bounding_box, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_regenerate_per_frame [EXTRACTED 1.00]
- **Two-Tier Architecture Layers** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_two_tier_architecture, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_ai_layer, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_pipeline_layer, docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_filesystem_storage [EXTRACTED 1.00]
- **Testing and Verification Surface** — docs_superpowers_specs_2026_07_20_sprite_game_asset_tool_design_testing_strategy, docs_superpowers_plans_2026_07_20_sprite_game_asset_tool_implementation_plan_tdd_approach, readme_smoke_generate, docs_superpowers_plans_2026_07_20_sprite_game_asset_tool_implementation_plan_dependency_injection [INFERRED 0.85]

## Communities (48 total, 8 thin omitted)

### Community 0 - "MCP Server Core"
Cohesion: 0.07
Nodes (118): AppContext, _asset_path(), _frame_paths(), main(), MCPAnimationResult, MCPExportResult, MCPFrameResult, MCPGenerateResult (+110 more)

### Community 1 - "Gemini Client"
Cohesion: 0.08
Nodes (54): GeminiClient, GeminiError, GeminiTimeoutError, _is_quota_exhausted(), _is_timeout(), _is_transient(), Any, Direction (+46 more)

### Community 2 - "Deps And Settings"
Cohesion: 0.05
Nodes (44): get_settings(), Return cached settings, failing loudly on invalid/missing auth config., _default_gemini(), _default_store(), get_gemini_client(), get_store(), FastAPI dependency providers.  Defined separately so tests can override them (``, Provide the project store (overridden in tests). (+36 more)

### Community 3 - "Config And Live Validation"
Cohesion: 0.08
Nodes (51): ArgumentParser, Application configuration.  Auth model: Vertex AI / Google Agent Platform. Prefe, Settings, Pure behavior tests for the disposable live Gemini validation harness., test_documented_support_matches_configured_model_roles_and_regions(), test_errors_are_classified_for_an_actionable_availability_matrix(), test_finalize_refreshes_report_and_returns_quality_verdict(), test_manual_review_requires_complete_scores_and_critical_quality() (+43 more)

### Community 4 - "Projects API Routes"
Cohesion: 0.08
Nodes (30): create_mcp_server(), ProjectDetail, ProjectSummary, Compact catalog entry used by the project browser., Full project state with browser metadata and fresh asset URLs., delete_project(), get_project(), list_projects() (+22 more)

### Community 5 - "Live Model Validation Docs"
Cohesion: 0.05
Nodes (43): Azure GPT Image 2 Acceptance Snapshot, Burst Quota Recovery Finding, gemini-3.1-flash-image, gemini-3.5-flash, Supported Whole-App Location global, Live Gemini Model Validation, Manual Output-Quality Rubric, Opt-in Safety Block Probe (+35 more)

### Community 6 - "Animate Route Tests"
Cohesion: 0.08
Nodes (30): app_and_store(), _fake_remover(), FakeGemini, _generate(), _make(), Image, Stage 2 route tests: /animate, /presets (fake Gemini edit)., generate() makes a removable-bg sprite; edit() echoes a similar sprite.      ``f (+22 more)

### Community 7 - "Trim Pipeline"
Cohesion: 0.11
Nodes (36): align_to_bbox(), _alpha_array(), autocrop(), content_bbox(), DegenerateBBoxError, EmptyImageError, Image, Alpha-based trimming and shared-bbox alignment.  Pure functions: ``Image -> Imag (+28 more)

### Community 8 - "Animate Routes"
Cohesion: 0.08
Nodes (29): animate(), _animation_payload(), delete_frame(), image_providers(), Request, POST /animate — expand a project's base sprite into an animation (Stage 2).  For, regenerate_frame(), generate() (+21 more)

### Community 9 - "Azure Image Provider"
Cohesion: 0.10
Nodes (26): _default_azure(), get_azure_image_provider(), Provide Azure GPT Image when its three required settings are present., _azure_error(), AzureImageProvider, _normalize_base_url(), Direction, Image (+18 more)

### Community 10 - "Stage1 Route Tests"
Cohesion: 0.09
Nodes (8): app_and_store(), _fake_remover(), FakeGemini, Image, Stage 1 route tests: /generate, /export, projects list/delete (fake Gemini)., Returns a sprite: opaque disk on a solid (removable) background, with margins., Green-screen remover: makes pure-green pixels transparent., test_auto_provider_prefers_configured_azure()

### Community 11 - "Frontend Package Deps"
Cohesion: 0.09
Nodes (22): dependencies, react, react-dom, zustand, devDependencies, jsdom, @testing-library/react, @types/react (+14 more)

### Community 12 - "Frontend API Client"
Cohesion: 0.17
Nodes (19): animate(), AnimateResult, ApiError, enhancePrompt(), EnhancePromptRequest, EnhancePromptResult, exportProject(), FrameStatus (+11 more)

### Community 13 - "Implementation Plan Concepts"
Cohesion: 0.10
Nodes (22): Seam Dependency Injection, google-genai SDK Call Shape, Sprite Game Asset Tool Implementation Plan, Partial Animation Failure Tolerance, Pipeline Purity Convention, TDD Implementation Approach, AI Layer Gemini, Base-Anchored Editing (+14 more)

### Community 14 - "Sprite Packer"
Cohesion: 0.19
Nodes (19): _grid_cols(), pack(), Image, Layout, Sprite-sheet packer (pure, deterministic).  Assumes frames are already uniformly, Pack frames into a single sheet.      Args:         frames: uniformly-sized RGBA, _frames(), Sprite-sheet packer: grid layout + pixel offsets (pure, deterministic). (+11 more)

### Community 15 - "Pixelate Pipeline"
Cohesion: 0.19
Nodes (18): Image, quantize(), Pixel-art conversion: integer downscale + color quantization (pure).  This is th, Reduce ``img`` to a pixel-art look.      Steps: optional integer downscale (near, _distinct_opaque_colors(), _gradient(), Image, Pixelate pipeline: color quantization + integer downscale/upscale (pure). (+10 more)

### Community 16 - "Frontend TSConfig"
Cohesion: 0.11
Nodes (18): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+10 more)

### Community 17 - "Prompt Builder"
Cohesion: 0.15
Nodes (16): build_generate_prompt(), _camera_direction(), frame_prompt(), get_preset(), list_presets(), Direction, Style, ViewMode (+8 more)

### Community 18 - "Project Store Tests"
Cohesion: 0.12
Nodes (4): Filesystem project store: dirs, image round-trip, manifest, list/delete., store(), test_list_projects(), test_write_manifest_preserves_creation_and_advances_update()

### Community 20 - "Project Browser UI"
Cohesion: 0.16
Nodes (10): deleteProject(), ProjectSummary, App(), ProjectBrowser(), broken, deleteProject, detail, getProject (+2 more)

### Community 21 - "Atlas Writer"
Cohesion: 0.22
Nodes (13): _json_atlas(), Layout, Atlas metadata writer (pure, byte-stable).  Serializes a packer layout to either, Serialize ``layout`` for a sheet of ``sheet_size`` to ``fmt`` ('json'|'xml')., write_atlas(), _xml_atlas(), Atlas metadata writer: JSON (golden) + XML, byte-stable., test_json_content_shape() (+5 more)

### Community 22 - "Background Removal"
Cohesion: 0.19
Nodes (12): _default_remover(), Image, Remover, Background removal wrapper.  The heavy ``rembg`` session is injected so unit tes, Remove the background using rembg. Imported lazily to avoid the heavy     onnxru, Return ``img`` with its background removed, always as an RGBA image.      Args:, remove(), Background removal wrapper (injected remover — no real rembg load in tests). (+4 more)

### Community 23 - "Config Tests"
Cohesion: 0.33
Nodes (13): _clear_env(), _fresh_config(), Config module: fail-loud validation of Vertex AI service-account auth., Reload the module so the cached settings don't leak between tests., test_get_settings_is_cached(), test_missing_credentials_file_fails_loud(), test_missing_project_fails_loud(), test_model_ids_and_region_overridable() (+5 more)

### Community 24 - "Pose Reference Guides"
Cohesion: 0.21
Nodes (11): Direction, Image, Deterministic pose guides for Gemini image edits.  Gemini preserves character id, Return a side-profile walk skeleton for a requested animation frame., walk_pose_reference(), Deterministic structural pose-guide tests., test_four_frame_walk_uses_mirrored_contact_and_passing_guides(), test_left_pose_is_horizontal_mirror_of_right_pose() (+3 more)

### Community 25 - "Export Panel UI"
Cohesion: 0.26
Nodes (6): ExportFormat, AnimationPlayer(), ExportPanel(), exportProject, frameAt(), useProjectStore

### Community 26 - "Animate Panel UI"
Cohesion: 0.21
Nodes (9): ImageProviderOption, Preset, AnimatePanel(), animate, listAnimationOptions, listImageProviders, listPresets, viewModeLabel() (+1 more)

### Community 27 - "Project State Types"
Cohesion: 0.31
Nodes (9): ExportResult, Frame, ImageProviderName, ProjectDetail, PromptSource, Style, initialAnimation, ProjectState (+1 more)

### Community 28 - "Direction Controls UI"
Cohesion: 0.36
Nodes (7): AnimationOptions, Direction, ViewMode, DIRECTION_LABELS, DirectionControls(), DirectionControlsProps, PromptEnhancer()

### Community 29 - "Node TSConfig"
Cohesion: 0.22
Nodes (8): compilerOptions, allowSyntheticDefaultImports, module, moduleResolution, noEmit, skipLibCheck, strict, include

### Community 30 - "Frame Strip UI"
Cohesion: 0.29
Nodes (5): deleteFrame(), FrameStrip(), deleteFrame, okFrames, regenerateFrame

### Community 31 - "Generate Panel UI"
Cohesion: 0.25
Nodes (7): GeneratePanel(), enhancePrompt, generate, listAnimationOptions, listImageProviders, options, providers

### Community 32 - "Shared Image Types"
Cohesion: 0.38
Nodes (4): Direction, Image, Style, ViewMode

### Community 33 - "Frame Edit Helpers"
Cohesion: 0.40
Nodes (4): Direction, Image, ViewMode, Edit one frame, adding a structural guide where the model needs it.

### Community 34 - "MCP Audit Concepts"
Cohesion: 0.67
Nodes (3): MCP tools/list Audit Distinction, Hyperagent Not Listed as Supported, Hyperagent Experimental Provider

## Knowledge Gaps
- **92 isolated node(s):** `Preset Action Library`, `Filesystem Project Storage`, `google-genai SDK Call Shape`, `Partial Animation Failure Tolerance`, `React Root Mount Point` (+87 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ProjectStore` connect `Projects API Routes` to `MCP Server Core`, `Deps And Settings`, `Animate Route Tests`, `Animate Routes`, `Stage1 Route Tests`, `Project Store Tests`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Why does `SpriteService` connect `MCP Server Core` to `Animate Routes`, `Frame Edit Helpers`, `Deps And Settings`, `Projects API Routes`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `GeminiClient` connect `Gemini Client` to `Animate Routes`, `MCP Server Core`, `Deps And Settings`, `Config And Live Validation`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Are the 40 inferred relationships involving `ProjectStore` (e.g. with `AppContext` and `_default_service()`) actually correct?**
  _`ProjectStore` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `SpriteService` (e.g. with `AppContext` and `MCPAnimationResult`) actually correct?**
  _`SpriteService` has 46 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `ViewMode` (e.g. with `AppContext` and `MCPAnimationResult`) actually correct?**
  _`ViewMode` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 46 inferred relationships involving `Style` (e.g. with `AppContext` and `MCPAnimationResult`) actually correct?**
  _`Style` has 46 INFERRED edges - model-reasoned connections that need verification._