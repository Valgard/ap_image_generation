---
name: image-generation
description: Use when generating images from a text prompt or reference images — feature images, illustrations, candidate sets — or when ANY image needs a transparent background: making an existing file transparent, cutting out or isolating a subject, removing a white background, or producing a logo, sticker, icon or overlay whose glow and soft edges must survive. Covers both images you generate and files the user already has. Backed by the Gemini image model (Nano Banana Pro).
---

# Image Generation

Generate one or more candidate images from a text prompt (plus optional reference
images) via the Gemini image model, and — when the result needs an alpha channel —
recover a transparent PNG from a white/black render pair. Both bundled scripts
(`generate_images.py`, `transparify.py`) are self-contained PEP-723 `uv` scripts
living in this skill's directory; `uv run` resolves their dependencies itself.

## Two roles — keep them separate

- **Knowledge role** (read this file while *writing* a prompt): prompt craft, bias
  mitigation, aspect/resolution choices, candidate ranking.
- **Execution role** (running the generator): a **pure pass-through**. It takes a
  *finished* prompt and parameters and never synthesizes, augments, or "improves"
  the prompt. If you need a prompt to stay byte-identical across steps (e.g. a
  caller persists it and copies it elsewhere), pass it via `--prompt-file` so no
  shell escaping can alter it — the file is the single source of truth.

## Running the generator

Run the bundled script with `uv` (it declares its own dependencies inline):

```bash
uv run <this-skill-dir>/generate_images.py --out-dir <dir> --name <base> "<prompt>"
```

| Flag | Required | Default | Purpose |
| --- | --- | --- | --- |
| `--prompt-file` / `-p` *(or positional prompt)* | yes | — | the finished prompt, verbatim |
| `--out-dir` / `-o` | yes | — | output directory (created if absent) |
| `--name` / `-n` | yes | — | filename base → `{name}-{N}.{ext}` |
| `--count` / `-c` | no | 1 | number of candidates |
| `--aspect-ratio` / `-ar` | no | `auto` | `auto / 1:1 / 4:3 / 16:9 / 9:16` |
| `--resolution` / `-r` | no | `1K` | `1K / 2K / 4K` — **edge length**, not a display mode |
| `--reference` / `-ref` | no | — | reference image; repeatable, multimodal |
| `--start-index` / `-s` | no | 1 | candidate numbering (for re-runs) |
| `--json` | no | off | emit run-config JSON to stdout; human output → stderr |

Output files are `{name}-{N}.{ext}` in `--out-dir`. A *set* of candidates is opt-in
(`--count N`) — the default is a single image.

### `--json` for machine callers

With `--json`, **stdout is exactly one JSON object** (the effective run config:
`model`, `prompt`, `prompt_file`, `out_dir`, `name`, `count`, `aspect_ratio`,
`resolution`, `start_index`, `references`) and all human/progress output goes to
stderr — so `… --json > run-config.json` captures the config cleanly. The JSON is
emitted at the start of the run (before the API call), so even an interrupted run
records its config. Use this to capture the *actual* model and parameters of a run
(not what you believe you passed).

## API key

`generate_images.py` needs `GEMINI_API_KEY` in the environment (`transparify.py`
is purely local and needs nothing). Without it, the script exits with a clean error
on stderr.

It comes from the environment — no `source` step, and no path worth documenting:
where the shell exports it from is the shell's business and changes over time. If it
is missing, suspect the shell layer before the declaration — a long-running process
keeps the environment it started with, and a non-interactive shell reads different
startup files than an interactive one.

## Prompt craft

- Structure: subject + setting + composition + style/lighting/mood, concrete over
  vague.
- **Negative constraints** are often stronger than positive ones — e.g. "no readable
  text", "no balls, no nets, no identifiable team sport".
- **Counter demographic bias:** when depicting people, specify gender / age /
  activity explicitly. If the first N candidates share the same demographic, the
  prompt is too open — tighten it before regenerating, don't just re-roll.

## Aspect ratio & resolution

- `auto` lets the model choose; pin `16:9` for wide feature images, `1:1` for
  square thumbnails, `9:16` for portrait.
- **`1K`/`2K`/`4K` name the edge length, not a display standard.** At `-ar 1:1` they
  produce exactly 1024², 2048² and 4096² (verified). `4K` here is **not** UHD
  3840×2160 and `2K` is not DCI 2048×1080 — the value sizes the image box, which the
  aspect ratio then shapes. `1K` is a good default; raise it only when the downstream
  use needs the detail (each step costs latency).
- **`4K` is the ceiling and there is nothing in between.** `8K`, `6K` and `3K` are
  all refused with `INVALID_ARGUMENT`; the SDK's `ImageSize` enum offers exactly
  `512`, `1K`, `2K`, `4K`. And **`512`, though the SDK lists it, is rejected by this
  model** (`size 512 is not supported for this model`) — so the usable set is three
  values. Match `-r` to the output you need; you cannot ask for an arbitrary size.

## Reference images

Pass `--reference <path>` (repeatable) to condition generation on existing images
(style or subject reference). JPEG/PNG/WebP supported.

## Ranking a candidate set

Image output is stochastic — that is why you generate N and choose. **Read each
candidate** (multimodal Read), then rank on: Prompt Coherence, Visual Impact,
Thematic Fit, Rule Violations. Never recommend from the prompt alone — the
generator's output is the evidence, not its input.

## Transparent output (alpha channel)

The model cannot emit alpha. A transparent PNG is recovered from **two renders** of
the same subject — one on white, one on black — with the bundled `transparify.py`.

**Read [transparent-output.md](transparent-output.md) before you start.** It is the
procedure, not background reading: the required flags per step, the recipe for a file
the user already has, the check that catches a black pass which silently came back
white, and the review backgrounds on which a white seam is actually visible. Two
attempts have already failed by working from a summary instead.

Three points are settled there and are not open for re-derivation:

- Generate a **pair**. Never matte a single image, and never treat the user's file
  as the white version — it is the `--reference` for one you generate.
- **`-ar 1:1` always**, then trim; never request the target aspect ratio directly.
- **Never substitute a local cutout**, however clean the source looks — flat art on
  pure white is the treacherous case, not the easy one.

## Model

Pinned in the script as `MODEL = "gemini-3-pro-image-preview"` (Nano Banana Pro).
It is not a caller parameter, so the model choice stays stable and traceable.
