"""Anonymisering: KB-BERT-NER + regexdetektering + konsekvent pseudonymisering + kodnyckel.

En `Anonymizer`-instans används för en hel körning (ett jobb) så att samma
ursprungssträng alltid får samma pseudonym genom hela dokumentet.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from app.config import settings

# Svenska etiketter per typkod. NER-koder från KB-BERT + egna koder för regexfynd.
TYPE_LABELS = {
    "PER": "Person",
    "LOC": "Plats",
    "ORG": "Organisation",
    "TME": "Tidpunkt",
    "EVN": "Händelse",
    "WRK": "Verk",
    "OBJ": "Objekt",
    "MSR": "Mått",
    "PRC": "Procent",
    "PNR": "Personnummer",
    "TEL": "Telefon",
    "EMAIL": "E-post",
    "REG": "Registreringsnummer",
}

# Regexdetektering av strukturerade personuppgifter som NER missar.
# Ordningen är prioritetsordning vid överlappande träffar.
REGEX_PATTERNS = [
    # Personnummer: ÅÅÅÅMMDD-XXXX eller ÅÅMMDD-XXXX (separator - eller +, eller ingen vid 12 siffror)
    ("PNR", re.compile(
        r"(?<!\d)(?:19|20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]?\d{4}(?!\d)"
    )),
    # E-postadresser
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # Svenska telefonnummer: +46/0046/0 följt av 7–9 siffror med valfria mellanslag/bindestreck
    ("TEL", re.compile(r"(?<![\d\w])(?:\+46|0046|0)[\s-]?\d(?:[\s-]?\d){6,9}(?![\d\w])")),
    # Registreringsnummer: ABC 123 eller ABC 12A
    ("REG", re.compile(r"\b[A-ZÅÄÖ]{3}\s?\d{2}[A-ZÅÄÖ\d]\b")),
]

_GENITIVE_TYPES = {"PER", "LOC", "ORG", "EVN", "WRK", "OBJ"}


@dataclass
class CodebookEntry:
    pseudonym: str
    original: str
    type_label: str
    count: int


class Anonymizer:
    """Håller pseudonymmappningen för en körning.

    `ner` är en funktion text -> lista av NER-träffar (dictar med nycklarna
    entity_group, word, start, end, score). Utan argument laddas KB-BERT-NER
    via transformers först när den behövs.
    """

    def __init__(
        self,
        ner: Optional[Callable] = None,
        entity_types: Optional[tuple] = None,
        score_threshold: Optional[float] = None,
    ):
        self._ner = ner
        self._pipeline = None
        self.entity_types = tuple(entity_types if entity_types is not None else settings.ner_entity_types)
        self.score_threshold = (
            score_threshold if score_threshold is not None else settings.ner_score_threshold
        )
        # nyckel: (typkod, normaliserad sträng) -> pseudonym
        self._pseudonyms: dict = {}
        # pseudonym -> [ursprunglig visningssträng, typkod, antal förekomster]
        self._entries: dict = {}
        self._counters: dict = {}

    # ---------------------------------------------------------------- NER

    def _run_ner(self, text: str) -> list:
        if self._ner is not None:
            return self._ner(text)
        if self._pipeline is None:
            from transformers import pipeline

            device = 0 if settings.resolve_device() == "cuda" else -1
            self._pipeline = pipeline(
                "token-classification",
                model=settings.ner_model,
                aggregation_strategy="first",
                device=device,
            )
        # BERT klarar ~512 token — kör längre texter i bitar med offsetjustering.
        results: list = []
        for offset, chunk in _chunk_text(text, max_chars=1200):
            for hit in self._pipeline(chunk):
                hit = dict(hit)
                hit["start"] = (hit.get("start") or 0) + offset
                hit["end"] = (hit.get("end") or 0) + offset
                results.append(hit)
        return results

    # ------------------------------------------------------- pseudonymer

    def _canonical_key(self, type_code: str, text: str) -> tuple:
        normalized = text.casefold()
        key = (type_code, normalized)
        if key in self._pseudonyms:
            return key
        if type_code in _GENITIVE_TYPES:
            if normalized.endswith("s") and (type_code, normalized[:-1]) in self._pseudonyms:
                return (type_code, normalized[:-1])  # "Annas" när "Anna" redan setts
            genitive = (type_code, normalized + "s")
            if genitive in self._pseudonyms:
                # "Anna" när bara "Annas" setts — uppdatera visningsform till grundformen
                pseudonym = self._pseudonyms[genitive]
                self._entries[pseudonym][0] = text
                return genitive
        return key

    def _pseudonym_for(self, type_code: str, text: str) -> str:
        key = self._canonical_key(type_code, text)
        if key not in self._pseudonyms:
            label = TYPE_LABELS.get(type_code, type_code)
            self._counters[type_code] = self._counters.get(type_code, 0) + 1
            pseudonym = f"[{label} {self._counters[type_code]}]"
            self._pseudonyms[key] = pseudonym
            self._entries[pseudonym] = [text, type_code, 0]
        return self._pseudonyms[key]

    def _register_use(self, pseudonym: str) -> None:
        self._entries[pseudonym][2] += 1

    # ------------------------------------------------------ anonymisering

    def anonymize(self, text: str) -> str:
        """Anonymisera en textbit. Mappningen delas över alla anrop på instansen."""
        if not text or not text.strip():
            return text

        spans: list = []  # (start, end, typkod, träfftext)

        def overlaps(start: int, end: int) -> bool:
            return any(s < end and start < e for s, e, _, _ in spans)

        for type_code, pattern in REGEX_PATTERNS:
            for match in pattern.finditer(text):
                if not overlaps(match.start(), match.end()):
                    spans.append((match.start(), match.end(), type_code, match.group()))

        for hit in self._run_ner(text):
            type_code = str(hit.get("entity_group", "")).upper()
            start, end = int(hit.get("start", 0)), int(hit.get("end", 0))
            word = text[start:end] if end > start else str(hit.get("word", ""))
            if (
                type_code in self.entity_types
                and float(hit.get("score", 1.0)) >= self.score_threshold
                and len(word.strip()) > 1
                and not overlaps(start, end)
            ):
                spans.append((start, end, type_code, word))

        # Ersätt spann bakifrån med sentineler så att en andra svepning inte
        # träffar redan insatta pseudonymer.
        sentinels: dict = {}
        result = text
        for start, end, type_code, word in sorted(spans, key=lambda s: s[0], reverse=True):
            stripped = word.strip()
            lead = len(word) - len(word.lstrip())
            trail = len(word) - len(word.rstrip())
            replacement = self._replacement(type_code, stripped)
            sentinel = f"\x00{len(sentinels)}\x00"
            sentinels[sentinel] = replacement
            result = result[: start + lead] + sentinel + result[end - trail if trail else end:]

        # Andra svepningen: fånga redan kända entiteter (case-insensitivt, valfri
        # genitiv-s) på ställen där NER/regex inte gav träff i just denna textbit.
        result = self._sweep_known(result, sentinels)

        for sentinel, replacement in sentinels.items():
            result = result.replace(sentinel, replacement)
        return result

    def _replacement(self, type_code: str, word: str) -> str:
        """Pseudonym för en träff, med bevarad genitiv-s ("Annas" -> "[Person 1]s")."""
        pseudonym = self._pseudonym_for(type_code, word)
        self._register_use(pseudonym)
        normalized = word.casefold()
        base = self._entries[pseudonym][0].casefold()
        if type_code in _GENITIVE_TYPES and normalized == base + "s":
            return pseudonym + "s"
        return pseudonym

    def _sweep_known(self, text: str, sentinels: dict) -> str:
        known = sorted(
            ((type_code, original) for (type_code, original) in self._pseudonyms),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        for type_code, normalized in known:
            if len(normalized) < 2:
                continue
            suffix = r"(s)?" if type_code in _GENITIVE_TYPES else r"()"
            pattern = re.compile(r"\b" + re.escape(normalized) + suffix + r"\b", re.IGNORECASE)

            def substitute(match: re.Match, tc: str = type_code, norm: str = normalized) -> str:
                pseudonym = self._pseudonyms[(tc, norm)]
                self._register_use(pseudonym)
                return pseudonym + ("s" if match.group(1) else "")

            text = pattern.sub(substitute, text)
        return text

    # ---------------------------------------------------------- kodnyckel

    def codebook(self) -> list:
        """Kodnyckelposter sorterade per typ och nummer. list[CodebookEntry]."""
        entries = [
            CodebookEntry(pseudonym=p, original=orig, type_label=TYPE_LABELS.get(tc, tc), count=count)
            for p, (orig, tc, count) in self._entries.items()
        ]
        order = {code: i for i, code in enumerate(TYPE_LABELS)}
        entries.sort(key=lambda e: (order.get(_type_code_of(e, self._entries), 99), _number_of(e.pseudonym)))
        return entries


def _type_code_of(entry: CodebookEntry, raw: dict) -> str:
    return raw[entry.pseudonym][1]


def _number_of(pseudonym: str) -> int:
    match = re.search(r"(\d+)\]$", pseudonym)
    return int(match.group(1)) if match else 0


def _chunk_text(text: str, max_chars: int) -> list:
    """Dela text i bitar om ~max_chars vid meningsgränser. Returnerar (offset, bit)."""
    if len(text) <= max_chars:
        return [(0, text)]
    chunks: list = []
    position = 0
    while position < len(text):
        end = min(position + max_chars, len(text))
        if end < len(text):
            split = max(text.rfind(". ", position, end), text.rfind("\n", position, end))
            if split > position:
                end = split + 1
        chunks.append((position, text[position:end]))
        position = end
    return chunks
