#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = ["google-genai", "typer", "rich"]
# ///
"""
Image Generator using the Gemini API (Nano Banana Pro).

Generates N candidate images into the given output directory. Optionally
takes reference images as multimodal input.

Usage:
  uv run generate_images.py --out-dir articles/<slug>/sources \
      --name feature-image "A prompt describing the image"
"""

import json
import os
from pathlib import Path
from typing import List, Optional

import typer
from google import genai
from google.genai import types
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

err_console = Console(stderr=True)
app = typer.Typer()

_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

MODEL = "gemini-3-pro-image-preview"


def ensure_out_dir(out_dir: Path) -> Path:
    """Ensure the output directory exists; return it. The caller owns layout."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def mime_for(path: Path) -> str:
    """Derive the MIME type of a reference image from its file suffix."""
    suffix = path.suffix.lower()
    if suffix not in _MIME_BY_SUFFIX:
        raise ValueError(f"Unsupported reference image type: {path.suffix}")
    return _MIME_BY_SUFFIX[suffix]


def resolve_prompt(prompt: Optional[str], prompt_file: Optional[Path]) -> str:
    """Return the effective prompt. Exactly one source must be given."""
    if prompt and prompt_file:
        raise ValueError("Pass either a prompt or --prompt-file, not both.")
    if not prompt and not prompt_file:
        raise ValueError(
            "A prompt is required: pass it as an argument or via --prompt-file."
        )
    if prompt_file:
        return prompt_file.read_text().strip()
    return prompt


def candidate_indices(start_index: int, count: int) -> range:
    """The candidate numbers to generate: count values from start_index."""
    return range(start_index, start_index + count)


def output_filename(name: str, index: int, ext: str) -> str:
    """Build a candidate filename: {name}-{index}.{ext}."""
    return f"{name}-{index}.{ext}"


def require_api_key() -> str:
    """Return the Gemini API key from the environment, or exit cleanly."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        err_console.print(
            "[red]Error:[/red] GEMINI_API_KEY is not set. "
            "Export it before running this script."
        )
        raise typer.Exit(1)
    return key


def build_image_config(
    aspect_ratio: str, resolution: str
) -> Optional[types.ImageConfig]:
    """ImageConfig for the request, or None when aspect ratio is 'auto'."""
    if aspect_ratio == "auto":
        return None
    return types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution)


def extract_image(response) -> Optional[tuple[bytes, str]]:
    """Return (image_bytes, ext) from the first inline-data part, or None."""
    if not response.candidates:
        return None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            mime_type = part.inline_data.mime_type
            ext = mime_type.split("/")[-1] if "/" in mime_type else "png"
            return part.inline_data.data, ext
    return None


def run_config_json(
    *,
    model: str,
    prompt: str,
    prompt_file: Optional[Path],
    out_dir: Path,
    name: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    start_index: int,
    references: List[Path],
) -> str:
    """Serialize the effective run configuration as a JSON object (data → stdout)."""
    config = {
        "model": model,
        "prompt": prompt,
        "prompt_file": str(prompt_file) if prompt_file else None,
        "out_dir": str(out_dir),
        "name": name,
        "count": count,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "start_index": start_index,
        "references": [str(r) for r in references],
    }
    return json.dumps(config, indent=2, ensure_ascii=False)


@app.command()
def generate_images(
    prompt_words: Optional[List[str]] = typer.Argument(
        None, help="Prompt für die Bildgenerierung"
    ),
    out_dir: Path = typer.Option(
        ...,
        "--out-dir",
        "-o",
        help="Zielordner für die Kandidaten, z.B. articles/<slug>/sources",
    ),
    name: str = typer.Option(
        ..., "--name", "-n", help="Datei-Basisname; Ausgabe {name}-{N}.{ext}"
    ),
    prompt_file: Optional[Path] = typer.Option(
        None,
        "--prompt-file",
        "-p",
        help="Datei mit dem Prompt (Alternative zum Prompt-Argument)",
    ),
    reference: Optional[List[Path]] = typer.Option(
        None,
        "--reference",
        "-ref",
        help="Referenzbild als multimodaler Input; mehrfach angebbar",
    ),
    start_index: int = typer.Option(
        1, "--start-index", "-s", help="Erste Kandidaten-Nummer"
    ),
    count: int = typer.Option(
        1, "--count", "-c", help="Anzahl der zu generierenden Bilder"
    ),
    aspect_ratio: str = typer.Option(
        "auto",
        "--aspect-ratio",
        "-ar",
        help="Seitenverhältnis (auto, 1:1, 4:3, 16:9, 9:16)",
    ),
    resolution: str = typer.Option(
        "1K", "--resolution", "-r", help="Kantenlänge: 1K, 2K, 4K (512 lehnt das Modell ab)"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Run-Config als JSON auf stdout (Human-Output → stderr)",
    ),
) -> None:
    console = Console(stderr=json_output)
    joined = " ".join(prompt_words) if prompt_words else None
    try:
        prompt = resolve_prompt(joined, prompt_file)
    except ValueError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    if json_output:
        print(
            run_config_json(
                model=MODEL,
                prompt=prompt,
                prompt_file=prompt_file,
                out_dir=out_dir,
                name=name,
                count=count,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                start_index=start_index,
                references=reference or [],
            )
        )

    client = genai.Client(api_key=require_api_key())

    try:
        reference_parts = [
            types.Part.from_bytes(data=ref.read_bytes(), mime_type=mime_for(ref))
            for ref in (reference or [])
        ]
    except ValueError as exc:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1)

    out = ensure_out_dir(out_dir)

    console.print(
        Panel(
            f"[bold]Prompt:[/bold] {prompt}\n"
            f"[bold]Name:[/bold] {name}  [bold]Referenzen:[/bold] {len(reference_parts)}\n"
            f"[bold]Auflösung:[/bold] {resolution}  [bold]Seitenverhältnis:[/bold] {aspect_ratio}",
            title=f"Images → [cyan]{out_dir}[/cyan]",
        )
    )

    image_config = build_image_config(aspect_ratio, resolution)

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), console=console
    ) as progress:
        for i in candidate_indices(start_index, count):
            task = progress.add_task(f"Generiere Bild {i}...", total=None)

            response = client.models.generate_content(
                model=MODEL,
                contents=[*reference_parts, prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=image_config,
                ),
            )

            progress.remove_task(task)

            result = extract_image(response)
            if result is not None:
                image_data, ext = result
                output_path = out / output_filename(name, i, ext)
                output_path.write_bytes(image_data)
                console.print(f"  [green]✓[/green] {output_path}")
            else:
                console.print(f"  [yellow]⚠ Kein Bild in Antwort {i}[/yellow]")
                if response.candidates:
                    for part in response.candidates[0].content.parts:
                        if part.text:
                            console.print(f"  [dim]{part.text[:200]}[/dim]")

    console.print(
        f"\n[bold green]Fertig![/bold green] Bilder gespeichert in [cyan]{out}[/cyan]"
    )


if __name__ == "__main__":
    app()
