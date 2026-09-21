"""Skärmbildsbeskrivning med Claude API (vision).

Detta är det enda steget i applikationen som skickar data externt: de extraherade
bildrutorna (aldrig ljud eller tal) skickas till Anthropics API för beskrivning.
Steget är opt-in per uppladdning och kräver ANTHROPIC_API_KEY i .env.
"""
from __future__ import annotations

import base64
import logging
from typing import Callable, Optional

from app.config import settings
from app.jobs import UserVisibleError

logger = logging.getLogger(__name__)

PROMPT = (
    "Detta är en skärmbild ur en utbildningsfilm om ett ärendehanteringssystem. "
    "Beskriv kort på svenska vad som visas: vilken vy eller flik som är öppen, "
    "synliga menyval, fältnamn och deras ifyllda värden, knapptexter samt eventuella "
    "statusar eller felmeddelanden. Var konkret och ordagrann med gränssnittstexter. "
    "Svara med löpande text utan inledning."
)

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.vision_available:
            raise UserVisibleError(
                "Skärmbildsbeskrivning kräver en API-nyckel. Lägg ANTHROPIC_API_KEY i .env "
                "och starta om applikationen."
            )
        import anthropic

        _client = anthropic.Anthropic()
    return _client


def _describe_image(png_bytes: bytes) -> str:
    """Beskriv en bild. Returnerar beskrivningen eller ett platshållarmeddelande."""
    import anthropic

    client = _get_client()
    request = dict(
        model=settings.vision_model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64.standard_b64encode(png_bytes).decode("ascii"),
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
    )
    try:
        # Server-side fallback: dirigerar om till annan modell om säkerhetsklassificerare
        # avböjer — stöds inte av äldre SDK-versioner, därav reserven nedan.
        response = client.beta.messages.create(
            **request, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
        )
    except TypeError:
        response = client.messages.create(**request)
    except anthropic.AuthenticationError:
        raise UserVisibleError(
            "API-nyckeln avvisades av Anthropic. Kontrollera ANTHROPIC_API_KEY i .env."
        ) from None

    if getattr(response, "stop_reason", None) == "refusal":
        return "(Bilden kunde inte beskrivas av modellen.)"
    parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
    return " ".join(parts).strip() or "(Ingen beskrivning returnerades.)"


def describe_frames(
    frames: list,
    progress: Optional[Callable] = None,
    describe_fn: Optional[Callable] = None,
) -> list:
    """Beskriv nyckelbilder. Returnerar list[dict] med time och text.

    `describe_fn` (bytes -> str) kan skickas in i tester i stället för API-anropet.
    """
    try:
        import anthropic

        api_errors: tuple = (anthropic.APIError,)
    except ImportError:  # tester utan anthropic installerat
        api_errors = ()

    describe = describe_fn or _describe_image
    results: list = []
    failures = 0
    for index, frame in enumerate(frames):
        png_bytes = frame.path.read_bytes()
        try:
            text = describe(png_bytes)
        except UserVisibleError:
            raise
        except api_errors as exc:
            logger.warning("Bildbeskrivning misslyckades vid %.0f s: %s", frame.time, exc)
            failures += 1
            text = "(Bilden kunde inte beskrivas — API-fel.)"
        results.append({"time": frame.time, "text": text})
        if progress is not None:
            progress((index + 1) / len(frames))
    if frames and failures == len(frames):
        raise UserVisibleError(
            "Ingen skärmbild kunde beskrivas — Claude API svarade med fel på samtliga anrop. "
            "Se serverloggen för detaljer."
        )
    return results
