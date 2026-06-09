from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Optional


SAFE_CONFIDENCES = {"exact", "strong", "fuzzy"}


@dataclass(frozen=True)
class SearchMatch:
    value: Optional[str]
    confidence: str
    reason: str
    query: str
    candidates: tuple[str, ...] = ()
    score: float = 0.0

    @property
    def safe(self):
        return self.confidence in SAFE_CONFIDENCES and self.value is not None


def normalize_text(text):
    tokens = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower()).split()
    compacted = []
    index = 0
    while index < len(tokens):
        if len(tokens[index]) == 1 and tokens[index].isalpha():
            start = index
            while index < len(tokens) and len(tokens[index]) == 1 and tokens[index].isalpha():
                index += 1
            run = tokens[start:index]
            if len(run) > 1:
                compacted.append("".join(run))
            else:
                compacted.extend(run)
            continue
        compacted.append(tokens[index])
        index += 1
    return " ".join(compacted)


def contains_phrase(text, phrase):
    if not phrase:
        return False
    return re.search(rf"(^|\s){re.escape(phrase)}($|\s)", text) is not None


def search_text_from_question(question, stopwords):
    stopwords = set(stopwords or ())
    return " ".join(
        word
        for word in normalize_text(question).split()
        if word not in stopwords and not word.isdigit()
    )


def _normalized_values(values):
    rows = []
    seen = set()
    for value in values:
        value = str(value or "").strip()
        normalized = normalize_text(value)
        if not value or not normalized or value in seen:
            continue
        seen.add(value)
        rows.append((value, normalized, tuple(normalized.split())))
    return rows


def _token_matches(search_tokens, rows):
    if not search_tokens:
        return []
    matches = []
    for value, normalized, tokens in rows:
        token_set = set(tokens)
        matched = sum(1 for token in search_tokens if token in token_set)
        if len(search_tokens) == 1:
            if matched:
                matches.append((matched, len(tokens), value))
        elif matched == len(search_tokens):
            matches.append((matched, len(tokens), value))
    return matches


def _ambiguous(values, query, reason, score=0.0):
    return SearchMatch(
        value=None,
        confidence="ambiguous",
        reason=reason,
        query=query,
        candidates=tuple(values[:8]),
        score=score,
    )


def match_name(query, values, stopwords=None, fuzzy_threshold=0.88, fuzzy_gap=0.08):
    rows = _normalized_values(values)
    normalized_query = normalize_text(query)
    search_text = search_text_from_question(query, stopwords or ())
    search_tokens = tuple(search_text.split())
    if not rows or len(search_text) < 2:
        return SearchMatch(None, "none", "no searchable customer text", search_text)

    token_matches = _token_matches(search_tokens, rows)
    if len(search_tokens) == 1 and len(token_matches) > 1:
        return _ambiguous(
            [value for _, _, value in token_matches],
            search_text,
            "single-word customer search matches multiple customers",
        )

    exact_matches = [
        value
        for value, normalized, tokens in rows
        if contains_phrase(normalized_query, normalized)
        and (len(tokens) > 1 or len(token_matches) <= 1)
    ]
    if exact_matches:
        exact_matches.sort(key=lambda value: len(normalize_text(value).split()), reverse=True)
        best = exact_matches[0]
        best_len = len(normalize_text(best).split())
        tied = [value for value in exact_matches if len(normalize_text(value).split()) == best_len]
        if len(tied) == 1:
            return SearchMatch(best, "exact", "customer name appears in query", search_text, (best,), 1.0)
        return _ambiguous(tied, search_text, "multiple exact customer matches", 1.0)

    phrase_matches = [
        value
        for value, normalized, _tokens in rows
        if contains_phrase(normalized, search_text)
    ]
    if phrase_matches:
        phrase_matches.sort(key=lambda value: len(normalize_text(value).split()), reverse=True)
        best = phrase_matches[0]
        best_len = len(normalize_text(best).split())
        tied = [value for value in phrase_matches if len(normalize_text(value).split()) == best_len]
        if len(tied) == 1:
            return SearchMatch(best, "strong", "query phrase appears in customer name", search_text, (best,), 0.95)
        return _ambiguous(tied, search_text, "multiple phrase customer matches", 0.95)

    if token_matches and len(search_tokens) > 1:
        token_matches.sort(reverse=True)
        best_score, best_len, best_value = token_matches[0]
        tied = [
            value
            for score, length, value in token_matches
            if score == best_score and length == best_len
        ]
        if len(tied) == 1:
            return SearchMatch(best_value, "strong", "all query tokens match one customer", search_text, (best_value,), 0.9)
        return _ambiguous(tied, search_text, "multiple token customer matches", 0.9)

    if len(search_text) >= 5:
        scored = []
        for value, normalized, _tokens in rows:
            ratio = SequenceMatcher(None, search_text, normalized).ratio()
            sorted_ratio = SequenceMatcher(
                None,
                " ".join(sorted(search_tokens)),
                " ".join(sorted(normalized.split())),
            ).ratio()
            scored.append((max(ratio, sorted_ratio), value))
        scored.sort(reverse=True)
        best_score, best_value = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        close = [value for score, value in scored if best_score - score < fuzzy_gap]
        if best_score >= fuzzy_threshold and best_score - runner_up >= fuzzy_gap:
            return SearchMatch(best_value, "fuzzy", "fuzzy customer match", search_text, (best_value,), best_score)
        if best_score >= fuzzy_threshold and close:
            return _ambiguous(close, search_text, "multiple fuzzy customer matches", best_score)

    return SearchMatch(None, "none", "no confident customer match", search_text)
