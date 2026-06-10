from dataclasses import dataclass
import re
from typing import Iterable


PHRASE_ALIASES = {
    "set up": "setup",
}


@dataclass(frozen=True)
class MasterValue:
    value: str
    row_count: int = 1


@dataclass(frozen=True)
class DuplicateGroup:
    normalized_name: str
    canonical_value: str
    variants: tuple[MasterValue, ...]

    @property
    def total_rows(self):
        return sum(variant.row_count for variant in self.variants)

    @property
    def possible_duplicates(self):
        return tuple(
            variant for variant in self.variants if variant.value != self.canonical_value
        )

    def to_dict(self):
        return {
            "canonical_value": self.canonical_value,
            "normalized_name": self.normalized_name,
            "total_rows": self.total_rows,
            "variants": [
                {"value": variant.value, "row_count": variant.row_count}
                for variant in self.variants
            ],
        }


def normalize_name(value, phrase_aliases=None):
    phrase_aliases = phrase_aliases or PHRASE_ALIASES
    text = str(value or "").replace("\xa0", " ").strip().lower()
    text = re.sub(r"[_\-–—]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for source, replacement in phrase_aliases.items():
        text = re.sub(rf"\b{re.escape(source)}\b", replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def clean_display_name(value):
    text = str(value or "").replace("\xa0", " ").strip()
    text = re.sub(r"[_\-–—]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_value(values: Iterable[MasterValue]):
    ordered = sorted(
        values,
        key=lambda item: (
            -item.row_count,
            _display_quality_score(item.value),
            item.value.lower(),
        ),
    )
    return ordered[0].value if ordered else ""


def duplicate_groups(rows):
    grouped = {}
    for row in rows:
        raw_value = row.get("value") if isinstance(row, dict) else row.value
        value = str(raw_value or "").strip()
        if not value:
            continue
        row_count = row.get("row_count", 1) if isinstance(row, dict) else row.row_count
        normalized = normalize_name(value)
        if not normalized:
            continue
        grouped.setdefault(normalized, {})
        grouped[normalized][value] = grouped[normalized].get(value, 0) + int(row_count or 0)

    duplicates = []
    for normalized, variants_by_value in grouped.items():
        if len(variants_by_value) < 2:
            continue
        variants = tuple(
            sorted(
                (
                    MasterValue(value=value, row_count=row_count)
                    for value, row_count in variants_by_value.items()
                ),
                key=lambda item: (-item.row_count, item.value.lower()),
            )
        )
        duplicates.append(
            DuplicateGroup(
                normalized_name=normalized,
                canonical_value=canonical_value(variants),
                variants=variants,
            )
        )

    return sorted(duplicates, key=lambda group: (-group.total_rows, group.normalized_name))


def _display_quality_score(value):
    words = str(value or "").split()
    score = 0
    for word in words:
        if word.isupper() and len(word) > 1:
            score += 2
        elif word[:1].isupper():
            score += 1
    return -score
