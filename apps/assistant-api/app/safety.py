"""Input safety: UK personal-data redaction and prompt-injection screening.

Pattern-based on purpose: deterministic, fast, explainable to a risk team.
A production bank would add an ML-based detector (e.g. Presidio) behind the
same interface.
"""

import re
from dataclasses import dataclass, field


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# Order matters: longer / more specific patterns first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("CARD_NUMBER", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("IBAN", re.compile(r"\bGB\d{2}\s?[A-Z]{4}(?:\s?\d{4}){3}\s?\d{2}\b", re.IGNORECASE)),
    ("NI_NUMBER", re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b", re.IGNORECASE)),
    ("SORT_CODE", re.compile(r"\b\d{2}-\d{2}-\d{2}\b")),
    ("PHONE", re.compile(r"(?:\+44\s?7\d{3}|\b07\d{3})\s?\d{3}\s?\d{3}\b")),
    ("ACCOUNT_NUMBER", re.compile(r"\b\d{8}\b")),
    ("POSTCODE", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)),
]


@dataclass
class Redaction:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> Redaction:
    counts: dict[str, int] = {}

    for label, pattern in _PATTERNS:
        def _sub(m: re.Match[str], label: str = label) -> str:
            if label == "CARD_NUMBER":
                digits = re.sub(r"\D", "", m.group(0))
                if not _luhn_ok(digits):
                    return m.group(0)
            counts[label] = counts.get(label, 0) + 1
            return f"[{label}]"

        text = pattern.sub(_sub, text)

    return Redaction(text=text, counts=counts)


_INJECTION = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore (all |any )?(the |your )?(previous|prior|above) (instructions|rules|prompts?)",
        r"disregard (the |your )?(system|previous) (prompt|instructions)",
        r"(reveal|print|show|repeat) (me )?(the |your )?(system prompt|hidden instructions)",
        r"you are now (?:in )?(developer|dan|jailbreak) mode",
        r"pretend (that )?you (have no|are not bound by) (rules|restrictions|policy)",
    ]
]


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION)
