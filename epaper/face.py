"""
Cute e-paper face for the Waveshare e-Paper HAT (V4) on a Raspberry Pi.

It's pure Pillow, so you can PREVIEW it on any computer (Windows/Mac/Linux)
with no display attached, then push the same image to the e-paper on the Pi.

Preview to a PNG (works anywhere):
    python face.py --mood happy --preview happy.png --scale 3

Show on the e-paper (on the Pi, with the Waveshare library installed):
    python face.py --mood happy --display

Moods: happy · sleepy · surprised · wink · love
Tip: wire the mood to your bot — e.g. "surprised" when a reminder is due in
the next hour, "sleepy" between 23:00-07:00, otherwise "happy".
"""

import argparse

from PIL import Image, ImageDraw

# In Pillow mode "1" (1-bit), 0 = black ink, 255 = white background.
BLACK = 0
WHITE = 255


def draw_face(width: int = 250, height: int = 122, mood: str = "happy") -> Image.Image:
    """Return a 1-bit Pillow image of a cute face sized for the panel."""
    img = Image.new("1", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    cx = width // 2

    # Eye geometry (scaled to the panel so it works at any resolution).
    eye_dx = int(width * 0.18)        # horizontal distance from centre
    eye_y = int(height * 0.40)
    eye_w = int(width * 0.11)
    eye_h = int(height * 0.22)
    left = (cx - eye_dx, eye_y)
    right = (cx + eye_dx, eye_y)

    def eye_open(c):
        x, y = c
        d.ellipse([x - eye_w, y - eye_h, x + eye_w, y + eye_h], fill=BLACK)
        # glossy white highlight, top-left — this is what makes it "cute".
        hx, hy = x - eye_w // 2, y - eye_h // 2
        d.ellipse([hx - eye_w // 4, hy - eye_h // 4, hx + eye_w // 4, hy + eye_h // 4], fill=WHITE)

    def eye_closed(c):  # happy/sleepy closed eye: a gentle "‿" curve
        x, y = c
        d.arc([x - eye_w, y - eye_h, x + eye_w, y + eye_h], start=200, end=340, fill=BLACK, width=3)

    def eye_circle(c):  # surprised: hollow wide eye
        x, y = c
        r = int(eye_w * 1.25)
        d.ellipse([x - r, y - r, x + r, y + r], outline=BLACK, width=3)

    def heart_eye(c):   # love: little filled heart
        x, y = c
        s = eye_w
        d.ellipse([x - s, y - s, x, y], fill=BLACK)
        d.ellipse([x, y - s, x + s, y], fill=BLACK)
        d.polygon([(x - s, y - s // 2), (x + s, y - s // 2), (x, y + int(s * 1.3))], fill=BLACK)

    # Mouth variants, centred a bit below the eyes.
    mcx, mcy = cx, int(height * 0.72)

    def mouth_cat():    # kawaii "ω" — two little bumps
        bw = int(width * 0.045)
        for off in (-bw, bw):
            d.arc([mcx + off - bw, mcy - bw, mcx + off + bw, mcy + bw], start=0, end=180, fill=BLACK, width=3)

    def mouth_smile():
        sw = int(width * 0.08)
        d.arc([mcx - sw, mcy - sw, mcx + sw, mcy + sw], start=20, end=160, fill=BLACK, width=3)

    def mouth_o():
        r = int(width * 0.03)
        d.ellipse([mcx - r, mcy - r, mcx + r, mcy + r], outline=BLACK, width=3)

    def blush():        # stippled cheeks (dither dots read as soft grey on e-ink)
        for cheek in (cx - int(width * 0.30), cx + int(width * 0.30)):
            for i in range(4):
                for j in range(3):
                    px, py = cheek - 8 + i * 5, int(height * 0.56) + j * 5
                    d.point((px, py), fill=BLACK)

    if mood == "happy":
        eye_open(left); eye_open(right); mouth_cat(); blush()
    elif mood == "sleepy":
        eye_closed(left); eye_closed(right); mouth_smile()
    elif mood == "surprised":
        eye_circle(left); eye_circle(right); mouth_o()
    elif mood == "wink":
        eye_open(left); eye_closed(right); mouth_cat(); blush()
    elif mood == "love":
        heart_eye(left); heart_eye(right); mouth_cat(); blush()
    else:  # fallback
        eye_open(left); eye_open(right); mouth_smile()

    return img


def show_on_epaper(mood: str) -> None:
    """Push the face to the physical panel. Runs only on the Pi."""
    # Imported here so the file still runs for --preview on machines without it.
    from waveshare_epd import epd2in13_V4

    epd = epd2in13_V4.EPD()
    epd.init()
    # The 2.13" V4 is portrait natively; (epd.height, epd.width) gives landscape.
    img = draw_face(epd.height, epd.width, mood)
    epd.display(epd.getbuffer(img))
    epd.sleep()


def main():
    p = argparse.ArgumentParser(description="Render a cute face for the e-Paper HAT.")
    p.add_argument("--mood", default="happy",
                   choices=["happy", "sleepy", "surprised", "wink", "love"])
    p.add_argument("--width", type=int, default=250, help="panel width (px)")
    p.add_argument("--height", type=int, default=122, help="panel height (px)")
    p.add_argument("--preview", metavar="PNG", help="save a PNG instead of using the display")
    p.add_argument("--scale", type=int, default=1, help="upscale factor for the PNG preview")
    p.add_argument("--display", action="store_true", help="render to the e-paper (on the Pi)")
    args = p.parse_args()

    if args.display:
        show_on_epaper(args.mood)
        return

    img = draw_face(args.width, args.height, args.mood)
    if args.scale > 1:
        img = img.resize((args.width * args.scale, args.height * args.scale), Image.NEAREST)
    out = args.preview or f"face_{args.mood}.png"
    img.save(out)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
