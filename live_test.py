"""Prove extraction is real: build a poster with known content, check the model reads it.

The poster contains deliberately invented names and numbers that appear nowhere in
mockdata.py. If they come back in the extracted card, the model genuinely read the
image rather than returning canned content.

Run: .venv\\Scripts\\python.exe live_test.py
"""

from __future__ import annotations

import io
import time
from datetime import date

from core.config import get_settings
from core.extract import extract_cards
from core.ingest import ingest
from core.llm import health_check

# Invented on purpose - none of this exists in the mock pool.
POSTER_LINES = [
    ("ABSTRACT 1147", 34, (0, 48, 135)),
    ("ZENTRELUTIDE IN ADULTS WITH OBESITY AND TYPE 2 DIABETES:", 26, (0, 0, 0)),
    ("52-WEEK RESULTS FROM THE HORIZON-3 PHASE 3 TRIAL", 26, (0, 0, 0)),
    ("Kestrel Therapeutics  |  Presented at Metabolic Congress 2026", 20, (90, 90, 90)),
    ("", 14, (0, 0, 0)),
    ("METHODS", 22, (0, 48, 135)),
    ("Randomised, double-blind, placebo-controlled. N = 1,842 adults.", 19, (0, 0, 0)),
    ("Primary endpoint: percent change in body weight at week 52.", 19, (0, 0, 0)),
    ("", 14, (0, 0, 0)),
    ("RESULTS", 22, (0, 48, 135)),
    ("Mean body weight change: -19.8% zentrelutide vs -2.4% placebo", 19, (0, 0, 0)),
    ("Participants achieving >=15% weight loss: 61.3% vs 4.1%", 19, (0, 0, 0)),
    ("HbA1c reduction: -1.9 percentage points from baseline", 19, (0, 0, 0)),
    ("Waist circumference: -14.2 cm vs -3.1 cm placebo", 19, (0, 0, 0)),
    ("", 14, (0, 0, 0)),
    ("SAFETY", 22, (0, 48, 135)),
    ("Nausea 31.2%, vomiting 14.7%, diarrhoea 18.0%", 19, (0, 0, 0)),
    ("Discontinuation due to adverse events: 8.4%", 19, (0, 0, 0)),
    ("No hepatic safety signal observed.", 19, (0, 0, 0)),
    ("", 14, (0, 0, 0)),
    ("CONCLUSION", 22, (0, 48, 135)),
    ("Zentrelutide produced clinically meaningful weight reduction with", 19, (0, 0, 0)),
    ("glycaemic benefit and a tolerability profile consistent with the class.", 19, (0, 0, 0)),
]

# Facts that must survive the round trip.
EXPECTED = ["zentrelutide", "kestrel", "horizon-3", "19.8", "8.4", "1,842"]


def build_poster() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1400, 1000), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 1400, 8], fill=(0, 48, 135))

    def font(size: int):
        for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    y = 40
    for text, size, colour in POSTER_LINES:
        if text:
            draw.text((60, y), text, fill=colour, font=font(size))
        y += size + 14

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def main() -> None:
    s = get_settings()
    print(f"provider : {s.provider}")
    print(f"model    : {s.vision_model}")
    print(f"is_live  : {s.is_live}\n")

    if not s.is_live:
        print("NOT LIVE - still in mock mode. Check .env")
        return

    ok, msg = health_check()
    print(f"health   : {'OK' if ok else 'FAILED'} - {msg}\n")
    if not ok:
        return

    png = build_poster()
    with open("data/test_poster.png", "wb") as fh:
        fh.write(png)
    print(f"poster   : {len(png) // 1024} KB written to data/test_poster.png\n")

    artifacts = ingest("HORIZON-3_poster.png", png)
    started = time.time()
    cards = extract_cards(artifacts[0], "Metabolic Congress 2026", date.today())
    elapsed = time.time() - started

    print(f"extracted {len(cards)} card(s) in {elapsed:.1f}s\n")
    print("=" * 70)
    for card in cards:
        print(f"title       : {card.title}")
        print(f"company     : {card.company}")
        print(f"asset       : {card.asset}")
        print(f"indication  : {card.indication}")
        print(f"trial       : {card.trial_name}  ({card.phase})")
        print(f"key message : {card.key_message}")
        print("data points :")
        for dp in card.data_points:
            print(f"  - {dp}")
        print(f"themes      : {', '.join(card.themes)}")
        print(f"confidence  : {card.confidence:.0%}")
        print("=" * 70)

    blob = " ".join(c.search_text().lower() for c in cards)
    print("\nDid the model actually read the poster?")
    missing = []
    for fact in EXPECTED:
        hit = fact in blob
        print(f"  {'FOUND   ' if hit else 'MISSING '} {fact}")
        if not hit:
            missing.append(fact)

    print()
    if len(missing) <= 1:
        print("REAL EXTRACTION CONFIRMED - the model read content that exists nowhere in the code.")
    else:
        print(f"SUSPECT - {len(missing)} expected facts missing. Check the model/prompt.")


if __name__ == "__main__":
    main()
