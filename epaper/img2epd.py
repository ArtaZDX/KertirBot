"""
Convert ANY image into a 1-bit e-paper picture and (optionally) show it.

Ideal for high-contrast line art / logos / tribal-chrome designs: those convert
beautifully to pure black & white. For such art use the default --mode threshold
(crisp edges). For photos, use --mode dither (Floyd-Steinberg, softer greys).

Preview on any computer (no hardware needed):
    python img2epd.py art.png --preview out.png --scale 3

Show it on the e-paper (on the Pi, Waveshare lib available):
    python img2epd.py art.png --display

Useful knobs:
    --mode threshold|dither     how to reduce to black/white (default threshold)
    --threshold 128             cut-off for threshold mode (lower = more black)
    --invert                    swap black/white (some panels/looks want this)
    --no-contrast               skip auto-contrast stretch
    --fit contain|cover         contain = whole image with margins (default)
    --rotate 90                 rotate the source before fitting
    --panel epd2in13_V4         your Waveshare driver module
"""

import argparse

from PIL import Image, ImageOps


def _load_flat(path) -> Image.Image:
    """Open an image and flatten any transparency onto a WHITE background."""
    src = Image.open(path)
    if src.mode in ("RGBA", "LA", "PA") or (src.mode == "P" and "transparency" in src.info):
        src = src.convert("RGBA")
        bg = Image.new("RGBA", src.size, (255, 255, 255, 255))
        src = Image.alpha_composite(bg, src)
    return src.convert("L")                        # grayscale


def convert(path, width=250, height=122, mode="threshold", threshold=128,
            invert=False, contrast=True, fit="contain", rotate=0) -> Image.Image:
    src = _load_flat(path)                          # grayscale, transparency -> white
    if contrast:
        src = ImageOps.autocontrast(src)          # stretch greys for punchier B/W
    if rotate:
        src = src.rotate(rotate, expand=True)

    canvas = Image.new("L", (width, height), 255)  # white background
    if fit == "cover":
        fitted = ImageOps.fit(src, (width, height), method=Image.LANCZOS)
        canvas.paste(fitted, (0, 0))
    else:                                          # contain: whole image, centered
        s = src.copy()
        s.thumbnail((width, height), Image.LANCZOS)
        canvas.paste(s, ((width - s.width) // 2, (height - s.height) // 2))

    if invert:
        canvas = ImageOps.invert(canvas)

    if mode == "dither":
        return canvas.convert("1")                 # Floyd-Steinberg dithering
    # threshold: every pixel becomes pure black or pure white
    return canvas.point(lambda p: 255 if p >= threshold else 0, mode="1")


def show_on_epaper(img: Image.Image, panel: str = "epd2in13_V4") -> None:
    import importlib

    epd_module = importlib.import_module(f"waveshare_epd.{panel}")
    epd = epd_module.EPD()
    epd.init()
    epd.display(epd.getbuffer(img))
    epd.sleep()


def main():
    p = argparse.ArgumentParser(description="Convert an image for an e-Paper panel.")
    p.add_argument("image", help="path to the source image")
    p.add_argument("--width", type=int, default=250)
    p.add_argument("--height", type=int, default=122)
    p.add_argument("--mode", choices=["threshold", "dither"], default="threshold")
    p.add_argument("--threshold", type=int, default=128)
    p.add_argument("--invert", action="store_true")
    p.add_argument("--no-contrast", dest="contrast", action="store_false")
    p.add_argument("--fit", choices=["contain", "cover"], default="contain")
    p.add_argument("--rotate", type=int, default=0)
    p.add_argument("--preview", metavar="PNG")
    p.add_argument("--scale", type=int, default=1)
    p.add_argument("--display", action="store_true")
    p.add_argument("--panel", default="epd2in13_V4")
    args = p.parse_args()

    img = convert(args.image, args.width, args.height, args.mode, args.threshold,
                  args.invert, args.contrast, args.fit, args.rotate)

    if args.display:
        show_on_epaper(img, args.panel)
        return

    out = img
    if args.scale > 1:
        out = img.resize((args.width * args.scale, args.height * args.scale), Image.NEAREST)
    dest = args.preview or "epaper_image.png"
    out.save(dest)
    print(f"Saved {dest}  ({args.width}x{args.height}, mode={args.mode})")


if __name__ == "__main__":
    main()
