# Live Gemini model validation

This is a manual, disposable acceptance check for the exact Vertex AI models and
location configured in `backend/.env`. It measures what the local project can
actually call; it does not replace Google Cloud status, quota, billing, or model
lifecycle monitoring.

The runner is deliberately outside pytest and CI. It makes billable live calls,
uses no retries, redacts the project ID from its JSON report, and writes only to
the git-ignored `scripts/live_validation_out/` directory.

## Supported configuration

Documentation was checked on **2026-07-21**. Recheck the linked model pages before
changing a model or location because availability and lifecycle dates can move.

| App role | Configured default | Supported Vertex location for this app | Launch stage | Source |
|---|---|---|---|---|
| Sprite generation | `gemini-3.1-flash-image` | `global` only | GA | [Gemini 3.1 Flash Image](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image) |
| Sprite editing | `gemini-3.1-flash-image` | `global` only | GA | [Gemini 3.1 Flash Image](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image) |
| Prompt enhancement | `gemini-3.5-flash` | `global`, `us`, `eu` for Standard PayGo | GA | [Gemini 3.5 Flash](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash) |

The supported whole-app intersection is therefore **`global`**. A text-only
deployment may use `us` or `eu`, but setting the app to either location makes the
configured image model unsupported. The Gemini 3.5 Flash page also lists several
regional locations for Provisioned Throughput; those are not treated as supported
here because this app is configured for ordinary PayGo calls.

An environment override with another model is reported as `unknown`, not silently
declared supported. Its direct live result remains in the matrix for investigation.

## Run the matrix

Run from `backend/` so Pydantic loads `backend/.env` and resolves its relative
credential path correctly:

```powershell
cd backend
.venv\Scripts\python.exe ..\scripts\validate_live_models.py
```

The cheap default makes three calls in the configured location: prompt enhancement,
base sprite generation, and image editing. It reports wall-clock request latency and
saves raw plus production-pipeline output for review.

For a release acceptance sample, use three repeats and the opt-in safety block probe:

```powershell
.venv\Scripts\python.exe ..\scripts\validate_live_models.py --repeats 3 --include-block-probe
```

That makes up to ten calls per location. The fixed safety prompt asks for extremist
propaganda, expects a provider safety block, and discards any returned image data.
It is opt-in so a normal smoke run never sends policy-boundary content.

To verify a deliberate region change, repeat `--region`:

```powershell
.venv\Scripts\python.exe ..\scripts\validate_live_models.py --region global --region eu
```

Each timestamped run contains:

- `matrix.json` — raw observations, documented expectation, timings, sanitized errors,
  and machine verdict;
- `MATRIX.md` — readable aggregate matrix, artifacts, and failures;
- `review.json` — human scoring sheet; and
- per-region text and PNG artifacts.

Availability is proven by the same operations the app uses, not merely by a model-list
response. `unavailable`, `access_denied`, `throttled`, `timeout`, `safety_blocked`, and
generic `error` remain distinct so IAM/quota incidents are not mislabeled as model
retirement. One sample is a smoke measurement, not an SLA; use at least three repeats
when evaluating latency.

## Automated acceptance

The automated verdict passes when every documented-supported prompt/generate/edit
probe is available, every documented-unsupported probe is unavailable, and an included
block probe is blocked. Unknown combinations are informational. The latency targets
shown in the report are:

| Operation | P95 target |
|---|---:|
| Prompt enhancement | 15 seconds |
| Sprite generation | 45 seconds |
| Sprite editing | 45 seconds |

Exceeding a latency target is highlighted for review but does not by itself turn a
single small-sample run into a failure. Treat repeated over-target results, throttling,
or timeouts as a release blocker until rechecked against Vertex status and quota.

The 2026-07-21 local acceptance run exposed a burst-quota limit after two immediate
image edits. With a 15-second quota cooldown and pose-reference inputs enabled, a
four-frame walk completed 4/4 without manual regeneration in 146.6 seconds. This
validates recovery behavior, not production capacity: confirm or raise the deployed
project's quota before release and include throttled runs in latency planning.

## Manual output-quality rubric

Open every artifact referenced by `review.json` and score each criterion `0`, `1`, or
`2`:

| Score | Meaning |
|---:|---|
| 0 | Unacceptable, materially wrong, unsafe, or missing |
| 1 | Usable only after visible correction or regeneration |
| 2 | Production-ready for this prototype without correction |

Prompt-enhancement criteria:

- `intent_preservation` — the subject and user constraints did not drift (**critical**);
- `sprite_specificity` — added detail improves silhouette, materials, and palette; and
- `clarity_and_editability` — concise plain text, easy for the user to edit.

Base-sprite criteria:

- `prompt_fidelity` — recognizable requested subject and attributes (**critical**);
- `silhouette_readability` — pose reads at intended game scale (**critical**);
- `style_adherence` — coherent pixel-art/game-sprite treatment;
- `directional_correctness` — side-scroller left-facing orientation is clear
  (**critical**);
- `background_separation` — subject separates cleanly from the generated background; and
- `technical_cleanliness` — no clipped body parts, corrupt pixels, or unusable artifacts
  after the production pipeline (**critical**).

Edited-frame criteria:

- `identity_consistency` — same character, equipment, colors, and proportions (**critical**);
- `motion_clarity` — the requested walk phase is visibly distinct (**critical**);
- `directional_correctness` — facing direction remains correct (**critical**);
- `style_consistency` — rendering and palette match the base;
- `background_separation` — subject remains cleanly isolated; and
- `technical_cleanliness` — frame is complete and pipeline-ready (**critical**).

A case passes with a mean score of at least **1.5** and no critical criterion scored
`0`. Every case must pass. After filling `review.json`, refresh the report:

```powershell
.venv\Scripts\python.exe ..\scripts\validate_live_models.py --finalize "..\scripts\live_validation_out\RUN_ID"
```

Finalize exits `0` for pass, `1` for pending/fail, and `2` for an invalid review file.
Keep a run only when it is useful as release evidence; otherwise delete its timestamped
directory.
