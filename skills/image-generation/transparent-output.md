# Transparent output — white/black difference matting

The model cannot emit an alpha channel. A transparent PNG is recovered by rendering
the subject **twice** — once on pure white, once on pure black — and computing alpha
from the difference with the bundled `transparify.py`.

## Quick reference

```bash
# 1. white candidates (always 1:1; -r sized to the source)
uv run <skill-dir>/generate_images.py --reference <source> --out-dir <dir> \
    --name white -ar 1:1 -r 1K -c 3 --prompt-file <prompt.txt>

# 2. black pass — references the CHOSEN white candidate, same -ar and -r
uv run <skill-dir>/generate_images.py --reference <dir>/white-N.jpeg --out-dir <dir> \
    --name black -ar 1:1 -r 1K -c 3 \
    "replace the white background with pure black #000000; keep everything else unchanged"

# 3. verify the corner is actually black, THEN matte
python3 -c "from PIL import Image; print(Image.open('black-1.jpeg').convert('RGB').load()[5,5])"
uv run <skill-dir>/transparify.py -w white-N.jpeg -b black-M.jpeg -o out.png

# 4. trim (fuzz 8%, not 3%) and review on grey / saturated / dark-UI backgrounds
magick out.png -bordercolor none -fuzz 8% -trim +repage final.png
```

Non-negotiable: **a pair, never a single image**; **`-ar 1:1`, never the target
ratio**; **never a local cutout instead**; **look at the result, not at the
statistics**.

## The three steps

1. **White candidates — always `-ar 1:1`.** Generate N, prompting for a *plain white
   background*, subject **centred with margin**. Rank them, pick one. The square
   format is load-bearing, not cosmetic (see below) — never pass `auto` here, and
   never request the final aspect ratio directly. Trim the finished PNG instead.

   **Pick `-r` from what the source actually carries — bigger is not better.** All
   three sizes matte equally well, so the only question is pixels, and **pixels
   beyond the source are invented, not recovered**. Generating a 320×400 original at
   `4K` buys latency and model invention, nothing else.

   A centred subject with margin occupies about **85 % of the edge length** in its
   longer dimension after trimming — identical at all three sizes (1024² → 332×869,
   2048² → 662×1736, 4096² → 1324×3473), so usable output is `edge × 0.85`: `1K`
   ~870 px, `2K` ~1740, `4K` ~3480. Anchor on the original's long edge and take the
   **smallest size that covers it**. `1K` is right for almost everything.

2. **Black version — natively, not by swapping the background.** Re-run with the
   **chosen white image as `--reference`**, `-ar 1:1` and the **same `-r` as the
   white version** (`transparify` requires identical dimensions), plus a minimal
   prompt ("replace the white background with pure black #000000; keep everything
   else unchanged"). Use `--count 3`: the model **sometimes ignores the instruction**
   and returns a white background again (3 of 14 runs so far, and it has hit two
   separate sessions), which mattes to a fully opaque PNG. Verify the corner before
   matting, do not assume. Take the first candidate whose corners are near
   `(0,0,0)`.

3. **Matte the pair** with `transparify.py`. Flags: `--white/-w`, `--black/-b`,
   `--out/-o`, `--threshold` (default `0.01`).

**Trim with `-fuzz 8%`, not `3%`.** The matted background is not perfectly zero: it
carries alpha 1–7 over much of its area (88 % of it at 4K), invisible at ≤ 2.7 %
opacity but sitting right at the `3%` threshold. A few hundred scattered pixels just
above it defeat the trim entirely — at 4K it returned 3882 px wide instead of 1324.
`8%` trims correctly at every size and costs at most one edge pixel.

## Starting from an image the user already has

The common request is "make this file transparent". The obvious move — treat that
file as the white version and only generate the black one — **does not work**: the
model repaints the subject rather than reproducing it (different size, missing
details), and `transparify` reads every foreground deviation as partial
transparency. A real case came out at 0.1 % opaque, the whole figure see-through.

Instead, the existing file becomes **`--reference` for a white version you
generate**, and the black pass references *that*:

1. `--reference <user-file> -ar 1:1 --count 3`, with `-r` sized to the original (a
   small source does not justify a large `-r`), and **describe the subject in the
   prompt**: a bare "reproduce this" loses details (hat ribbons went missing). Pick
   the candidate closest to the original.
2. Black pass referencing that candidate, then matte, as in the three steps above.

The trade is explicit: the result is a faithful **reproduction**, not the original
pixels cut out. Its gain is a flawless background (alpha 0–2) that no edge-detection
cutout achieves. It also comes out larger than the source, but treat that as a side
effect, not a benefit — the added pixels are the model's invention, not detail
recovered from the original. If the user needs the original pixels preserved
exactly, this method is wrong; say so rather than delivering a repaint.

**Do not substitute a local cutout, however clean the source looks.** This applies
to hard-edged flat vector art on pure white just as much as to glows and soft
edges — that case reads as the easy one and is the treacherous one: white areas
*inside* the subject (a shirt, a life ring, a highlight) have **no contour
separating them from the white background**, so any flood-fill or threshold takes
them with it. That is not a tuning problem, the boundary is simply not present in
the pixels — a human in Photoshop would have to redraw it too. Tried on 2026-08-07:
every statistic said the cutout was clean, and it had punched holes straight through
a life ring.

| Rationalisation | Why it fails |
| --- | --- |
| "transparify needs a pair, I only have one image" | The file is not the white version — it is the reference for one you generate. |
| "Hard vector edges on pure white need no repaint" | White subject areas without a contour are indistinguishable from the background; the cutout eats them. |
| "This subject is too simple / too complex for the method" | Neither predicts success — the aspect ratio does. |

There is exactly one question worth raising, and only when the answer plausibly
matters: does the user need the **original pixels** preserved? If yes, this method
is wrong — say so. Otherwise run it. Do not present a menu of alternatives.

## Why it works this way

**Why native black, never matting:** a glow rendered *against white* has its
semi-transparent pixels already blended with white — mechanically replacing the
background with black leaves a flat, washed-out halo. Re-rendering on black gives
the correct colour-into-black falloff.

**Why the chosen white image is the reference:** the matte derives alpha and true
colour from `P_white − P_black` per pixel, which only holds while the **foreground
is identical** in both. Referencing the white image keeps the subject in register.
The two files must have identical dimensions — a mismatch raises `ValueError`.

**Why the square format is load-bearing — and the resolution is not.** An extreme
aspect ratio, which `auto` will happily produce from a portrait reference, forces
the model to extrapolate, and the black pass then reproduces the white one far less
exactly. Measured on one subject as mean RGB deviation inside the motif and share of
strongly deviating pixels (`>60`), three runs per resolution:

| `-r` at `-ar 1:1` | pixels | register | strongly deviating |
| --- | --- | --- | --- |
| `1K` | 1024² | 10.5–11.2 | 0.58–0.63 % |
| `2K` | 2048² | 8.6–9.7 | 0.52–0.57 % |
| `4K` | 4096² | 11.3–11.7 | 0.49–0.57 % |
| `auto` → 656×1603 | — | **37.3** | **17.2 %** |

Every square resolution lands in the same narrow band and all of them beat a shipped
logo that was judged good (15.0 / 6.37 %); only the non-square run collapses. The
ranking survives normalising all pairs to 1024² first, so it is not a pixel-count
artefact. Subject complexity is *not* the limiting factor either: an ornate logo with
glow, rays and sparkles registers better than a plain figure in the wrong format, and
tuning the prompt does not help where the format is wrong.

`transparify.py` is a 1:1 port of transparify.app's client-side algorithm (that site
has no API), validated against its output. The math is in the module docstring; tests
sit beside it in `test_transparify.py`.

## Checking the result

**The preview background decides what you can see.** A white seam ("sticker look")
is invisible on the two backgrounds one reaches for first: bright magenta overpowers
light fringes, and black lets them pass as antialiasing. Composite over **mid grey, a
saturated hue, and the dark-UI tone (~#22242e)**; a light background (yellow, pale
blue) additionally reveals any residual veil. Judge the image, not the statistics —
"0.00 % halo" was once reported for a fully opaque PNG, because a metric over
semi-transparent pixels has almost nothing to measure when there are none.

**Comparing two runs: use the alpha channel, never a byte diff.** Alpha derives from
the white↔black *distance* and is reproducible bit-for-bit. Colour derives from
`B / a`, so at low alpha a single bit of JPEG-decoder noise in the black render is
amplified by `1/a` — re-matting a shipped pair on a newer Pillow moved RGB by up to
84 in semi-transparent pixels while alpha stayed identical across all 1M pixels, and
opaque/transparent pixels did not move at all. The image is unchanged; only
near-invisible pixels drift.
