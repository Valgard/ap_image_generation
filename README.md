# image-generation

A Claude Code plugin that generates images from a text prompt or reference images with
the Gemini image model (Nano Banana Pro), and recovers transparent PNGs whose glow and
soft edges survive.

## Usage

The skill triggers on its own whenever an image has to be generated or an image needs a
transparent background — including files the user already has. It can also be invoked
explicitly:

~~~
/image-generation:image-generation
~~~

It bundles two self-contained [PEP 723](https://peps.python.org/pep-0723/) scripts that
`uv run` executes without any project setup:

| Script | What it does | Needs |
|--------|--------------|-------|
| `generate_images.py` | Renders one or more candidates from a finished prompt, with optional reference images, aspect ratio and resolution | `GEMINI_API_KEY` in the environment |
| `transparify.py` | Computes a transparent PNG from a white-background and a black-background render of the same subject | nothing — runs locally |

The model cannot emit an alpha channel, so transparency always comes from such a
white/black pair. The procedure, including the checks that catch a failed black pass,
is in [`skills/image-generation/transparent-output.md`](skills/image-generation/transparent-output.md).
Flags, prompt craft and candidate ranking are in
[`skills/image-generation/SKILL.md`](skills/image-generation/SKILL.md).

## Tests

~~~bash
cd skills/image-generation
uv run --with pytest --with google-genai --with typer --with rich --with pillow pytest
~~~

The tests make no API calls.

## Repository layout

~~~
.claude-plugin/plugin.json                    plugin manifest
skills/image-generation/SKILL.md              the skill
skills/image-generation/transparent-output.md transparency procedure
skills/image-generation/generate_images.py    Gemini image generator
skills/image-generation/transparify.py        white/black pair → transparent PNG
skills/image-generation/test_*.py             tests for both scripts
docs/specs/                                   original design document
~~~
