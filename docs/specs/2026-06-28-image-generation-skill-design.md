# Design: Extract image generation into a standalone global `image-generation` skill

- **Date:** 2026-06-28
- **Status:** Approved (brainstorming) — pending implementation plan
- **Scope:** Two repos — global skills repo (`~/.claude/skills`) and the blogs repo (`editorial-workflow` skill + docs)

## Context

`generate_images.py` is a self-contained PEP-723 `uv` script (inline deps: `google-genai`,
`typer`, `rich`) that generates candidate images via the Gemini image model
(`gemini-3-pro-image-preview`, "Nano Banana Pro"). It currently lives inside the project-local
`editorial-workflow` skill (`.claude/skills/editorial-workflow/`) and is invoked only in
**Phase 10a (Asset Generation)**.

The script is generic ("prompt + optional reference images → N images"), but it is welded to the
article workflow in two ways: its CLI takes `--article-dir` and hardcodes the output subfolder to
`<article-dir>/sources/`, and the surrounding Phase-10a spec carries the invocation path verbatim.

We want image generation to be a reusable capability across **any** project, not just the blogs.

## Goals

- A standalone, project-agnostic **global** skill `image-generation` under `~/.claude/skills/`.
- Generic image know-how (prompt craft, bias mitigation, aspect/resolution, candidate ranking) lives
  in one place — the skill — instead of being locked inside `editorial-workflow`.
- `editorial-workflow` Phase 10a **delegates generation to the skill** with **no script path or
  command string in its spec text** — it names the skill and the parameter contract only.
- The image-generation **prompt stays deterministic and traceable** across the Phase 10a → Phase 11
  boundary (byte-identical persistence and copy-in).

## Non-Goals

- Pixel-level reproducibility of generated images. Image output is intentionally stochastic — that is
  precisely why N candidates are generated and then ranked. "Deterministic" here means **prompt and
  invocation fidelity**, not identical bytes.
- Rewriting historical run logs. Per-article `asset-generation.md` files and the 2026-05-18
  `docs/superpowers/` consolidation artifacts are history and are left untouched.
- Adding new image backends. The skill is Gemini-backed today; the name is backend-neutral to keep
  that option open, but no abstraction layer is built now (YAGNI).

## Design

### 1. The global skill

```
~/.claude/skills/image-generation/        (its own git repo — commit there, NOT in ~/.claude)
  SKILL.md                  ← instructional knowledge (knowledge role)
  generate_images.py        ← moved from editorial-workflow, generalized
  test_generate_images.py   ← moved; one test function adapted
```

- **Name:** `image-generation` — substantive, backend-neutral, consistent with existing global skills
  (`glossar`, `summarize-article`, `excalidraw-generation`).
- **Trigger:** auto-triggerable. The `description` names Gemini / Nano Banana so it fires on
  "generate / create an image" intents without firing on every mention of "image".
- **Two roles, explicitly separated:**
  - **Knowledge role** (read *during prompt synthesis* by a caller, and by ad-hoc users): prompt
    craft, bias-mitigation technique (negative constraints, demographic specification), aspect-ratio /
    resolution guidance, candidate-ranking criteria.
  - **Execution role** (the generator run): a **pure pass-through** — it takes a *finished* prompt and
    parameters and never synthesizes, augments, or "improves" the prompt.
- **Path independence:** `SKILL.md` references its bundled `generate_images.py` relative to the
  skill's load-time base directory. No absolute `~/.claude/...` path appears in any spec text.

### 2. Script generalization (`generate_images.py`)

The only code change. Behavioral deltas:

| Aspect | Before | After |
| --- | --- | --- |
| Output target | `--article-dir X` → hardcoded `X/sources/` | `--out-dir <dir>` (the caller owns `sources/`) |
| `candidate_dir()` | appends `/sources` to article dir | ensures and returns the given out-dir |
| `count` default | 5 | **1** (a candidate *set* is a caller opt-in) |
| Model id | inline literal in the API call | module constant `MODEL` (single source for call + echo) |
| Machine output | none | `--json` flag (see §3) |

Preserved: the ad-hoc convenience of passing the prompt as a positional argument **or** via
`--prompt-file`; `--reference` multimodal inputs; `--start-index`; `--aspect-ratio`; `--resolution`.

### 3. Output contract (`--json`, opt-in)

- **`--json` flag, default off.**
- **Without `--json`:** current human behavior — `rich` panel + spinner + `✓`/`⚠` result lines. No
  JSON.
- **With `--json`:** **stdout = exactly one JSON object** (the run configuration); the human `rich`
  output is routed to **stderr** (`Console(stderr=True)`) so stdout stays pure JSON and
  `… --json > run-config.json` works cleanly. The JSON config is emitted once, at the start of the run
  (so even an interrupted run has recorded its configuration).
- **JSON shape** (`json.dumps(…, indent=2, ensure_ascii=False)` — `ensure_ascii=False` keeps non-ASCII
  prompt text readable and diff-able):

  ```json
  {
    "model": "gemini-3-pro-image-preview",
    "prompt": "<resolved prompt text>",
    "prompt_file": "<path or null>",
    "out_dir": "<path>",
    "name": "feature-image",
    "count": 5,
    "aspect_ratio": "16:9",
    "resolution": "1K",
    "start_index": 1,
    "references": ["<path>", ...]
  }
  ```

- The JSON is produced by a **pure helper** `run_config_json(...) -> str`, unit-testable without the
  API (parse with `json.loads`, assert `["model"] == MODEL` and that core parameters are present).

### 4. Determinism / traceability contract

The prompt is a load-bearing artifact that must survive byte-identical across phase boundaries.
Two design rules guarantee that:

1. **The skill never synthesizes the prompt.** Prompt synthesis (ALT scene + skeleton hook +
   bias-mitigation negative constraints) stays in the caller (Phase 10a), because it depends on
   article-specific inputs the skill does not see. The skill's execution role is a dumb, faithful
   pass-through: finished string in → unchanged to the model.
2. **Prompt-as-file, not shell argument** (for the editorial path). A long bias-constrained prompt
   passed as a shell argument is exposed to quoting/escaping hazards (`"`, `$`, backticks, newlines)
   that can make the executed prompt diverge from the persisted one. A canonical file eliminates that.

A single canonical file collapses three requirements into one artifact:

`articles/{article-dir}/sources/feature-image-prompt.txt`
- the **deterministic input** (`--prompt-file`, no shell escaping),
- the **single source of truth** Phase 11 copies byte-identical into `metadata.yaml`
  `header_image.prompt`,
- embedded/referenced verbatim in `asset-generation.md § Image-Generation-Prompt` (human work-doc).

Run-configuration traceability comes from the **script's own `--json` stdout**, captured into the
work-doc — recording the *actual* model + parameters used, not what the caller *believes* it passed
(eliminating intended-vs-actual drift).

### 5. `editorial-workflow` Phase 10a — delegation

Phase 10a keeps **all** article-specific duties (caption finalization, ALT parity, image-prompt
staging, metadata coupling, in-context candidate ranking). What changes:

- It **invokes the `image-generation` skill** and passes the parameter contract — **no `uv run …`
  command, no script path** in the spec text.
- Parameters: `out-dir = articles/{article-dir}/sources`, `name = feature-image`, `--prompt-file`
  pointing at `feature-image-prompt.txt`, **`count` explicitly (5 — the candidate-set size is an
  editorial decision)**, aspect ratio, and `--json`.
- Generic prompt craft and ranking criteria: **referenced** from the skill (not duplicated).
  Article-specific rules (ALT / caption / staging) remain stated verbatim in Phase 10a.
- The staging section records the verbatim prompt (from the `.txt`) **plus** the run config (from the
  script's `--json` stdout).

### 6. Input contract (execution role)

| Input | Required | Default | Purpose |
| --- | --- | --- | --- |
| `--prompt-file` *(or positional prompt, ad-hoc)* | yes (editorial: file) | — | the **finished** prompt, verbatim |
| `--out-dir` | yes | — | output directory (editorial: `…/sources`) |
| `--name` | yes | — | filename base (`feature-image` → `feature-image-{N}.{ext}`) |
| `--count` | no | **1** | number of candidates |
| `--aspect-ratio` | no | `auto` | `auto / 1:1 / 4:3 / 16:9 / 9:16` |
| `--resolution` | no | `1K` | `512 / 1K / 2K / 4K` |
| `--reference` | no | — | reference image(s), multimodal; repeatable |
| `--start-index` | no | 1 | candidate numbering (re-runs) |
| `--json` | no | off | emit run-config JSON to stdout, human output to stderr |

Model is **not** a caller input — it is pinned in the script (`MODEL`) so the model choice is stable
and traceable.

## Edit inventory

**Live spec / docs — updated to delegation references (NOT a new path):**
- `editorial-workflow/SKILL.md`, `phases.md`, `roadmap.md` — Phase-10a invocation lines become
  skill-delegation references; roadmap file-tree drops the moved files.
- `blogs/README.md` (line ~77), `docs/workflow.md` (lines ~421/423), `docs/style-guide.md`
  (lines ~57/60) — pipeline description points at the skill instead of a command line.

Exact line edits are resolved at implementation time via a per-file grep; this inventory is at the
file level.

**Deliberately left untouched (history):**
- 6× `articles/*/sources/asset-generation.md` — per-article run logs of the command actually executed.
- `docs/superpowers/specs|plans/2026-05-18-image-generator-consolidation*` — historical artifacts.

## Testing / Verification

- Move `test_generate_images.py`; adapt the one coupled test
  (`test_candidate_dir_resolves_into_article_sources` → asserts `candidate_dir` creates/returns the
  given out-dir). The 16 pure-helper tests are unaffected.
- Add a test for `run_config_json(...)`: `json.loads` parses, `["model"] == MODEL`, core params present.
- Run the suite in the new location → all green.
- Smoke test: `--out-dir /tmp/imgtest --count 1 --json "…"` → emits valid JSON on stdout and either a
  file (if `GEMINI_API_KEY` set) or a clean key-error without a key.
- `grep -rn "editorial-workflow/generate_images" blogs/` finds no **live** reference (history only).

## Commits (two repos, separate)

- **`~/.claude/skills` repo:** `feat(image-generation): extract Gemini image generator into standalone global skill`
- **`blogs` repo:** `refactor(editorial-workflow): delegate image generation to global image-generation skill`
  — removes the moved script + test, repoints live references to the skill delegation, adds the
  `feature-image-prompt.txt` canonical-prompt convention.

## Open implementation details (decided during implementation, no further input needed)

- Exact per-file line edits in the edit inventory.
- Whether the `~/.claude/skills` repo has a remote (push handling).
- Commit ordering across the two repos.
