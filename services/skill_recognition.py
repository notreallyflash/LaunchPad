"""Deterministic ESCO skill recognition for LaunchPad AI.

This module deliberately separates label recognition from career ranking.
It matches exact ESCO preferred/alternative/hidden labels, reports ambiguous
labels for review, and returns unique canonical skill URIs only for unambiguous
matches. It does not infer proficiency from a mention.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence


# Keep common technical terms intact. The general token expression also keeps
# punctuation inside tokens such as Node.js, CI/CD, ASP.NET and SQL-like names.
_TOKEN_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:\.net|c\+\+|c#|f#|r\+)(?![A-Za-z0-9_])"
    r"|[A-Za-z0-9]+(?:[+#./-][A-Za-z0-9+#]+)*"
    r"|[^\W_]",
    re.UNICODE,
)

_LABEL_TYPE_PRIORITY = {"preferred": 0, "alternative": 1, "hidden": 2}


class RecognitionInputError(ValueError):
    """Raised when text exceeds safe local recognition limits."""


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int


@dataclass(frozen=True)
class SkillLabelRow:
    normalized_label: str
    skill_uri: str
    label: str
    label_type: str
    preferred_label: str
    skill_type: str | None = None
    reuse_level: str | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "SkillLabelRow":
        return cls(
            normalized_label=normalize_label(str(row.get("normalized_label") or row.get("label") or "")),
            skill_uri=str(row.get("skill_uri") or ""),
            label=str(row.get("label") or row.get("normalized_label") or ""),
            label_type=str(row.get("label_type") or "alternative"),
            preferred_label=str(row.get("preferred_label") or row.get("label") or ""),
            skill_type=_optional_string(row.get("skill_type")),
            reuse_level=_optional_string(row.get("reuse_level")),
        )


@dataclass
class SkillDetection:
    skill_uri: str
    preferred_label: str
    label_type: str
    skill_type: str | None
    reuse_level: str | None
    matched_phrases: list[str] = field(default_factory=list)
    evidence_snippets: list[str] = field(default_factory=list)
    occurrence_count: int = 0
    match_status: str = "exact_unique_label"


@dataclass
class AmbiguousCandidate:
    skill_uri: str
    preferred_label: str
    skill_type: str | None
    reuse_level: str | None


@dataclass
class AmbiguousSkill:
    matched_phrase: str
    evidence_snippets: list[str]
    candidates: list[AmbiguousCandidate]
    occurrence_count: int = 1
    match_status: str = "ambiguous_requires_review"


@dataclass
class ReviewSkill:
    """A unique match found only through an ESCO hidden label.

    Hidden labels are useful for discovery but can be broad or misleading in
    resume context. They are therefore not credited to ranking until reviewed
    or supported by a preferred/alternative label elsewhere in the resume.
    """
    skill_uri: str
    preferred_label: str
    matched_phrases: list[str] = field(default_factory=list)
    evidence_snippets: list[str] = field(default_factory=list)
    occurrence_count: int = 0
    match_status: str = "hidden_label_requires_review"


@dataclass
class RecognitionResult:
    confirmed_skills: list[SkillDetection]
    ambiguous_matches: list[AmbiguousSkill]
    token_count: int
    candidate_phrase_count: int
    catalog_row_count: int
    review_matches: list[ReviewSkill] = field(default_factory=list)
    truncated: bool = False

    @property
    def confirmed_skill_uris(self) -> list[str]:
        """Unique skill URIs suitable for the first-pass ranking function."""
        return sorted({item.skill_uri for item in self.confirmed_skills})

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmed_skills": [asdict(item) for item in self.confirmed_skills],
            "ambiguous_matches": [asdict(item) for item in self.ambiguous_matches],
            "review_matches": [asdict(item) for item in self.review_matches],
            "confirmed_skill_uris": self.confirmed_skill_uris,
            "token_count": self.token_count,
            "candidate_phrase_count": self.candidate_phrase_count,
            "catalog_row_count": self.catalog_row_count,
            "truncated": self.truncated,
        }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_label(value: str) -> str:
    """Mirror the database's lower(trim(label)) lookup convention.

    NFKC normalisation and whitespace collapse make PDF text more stable while
    preserving meaningful technical punctuation (C++, C#, .NET, Node.js, CI/CD).
    """
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def tokenize_with_spans(text: str) -> list[Token]:
    """Tokenise text while retaining offsets and common technical punctuation."""
    normalised_text = unicodedata.normalize("NFKC", text or "")
    return [
        Token(value=match.group(0).lower(), start=match.start(), end=match.end())
        for match in _TOKEN_RE.finditer(normalised_text)
    ]


def build_candidate_phrases(
    text: str,
    *,
    max_words: int = 12,
    max_candidate_phrases: int = 20_000,
    max_tokens: int = 5_000,
    max_text_characters: int = 40_000,
) -> tuple[list[str], list[Token], bool]:
    """Build unique contiguous n-grams to send to the indexed SQL lookup.

    A maximum of 12 tokens per phrase is a practical first-pass bound. Very
    long ESCO labels can be added later through specialised phrase handling.
    """
    if not isinstance(text, str):
        raise TypeError("Resume text must be a string.")
    if len(text) > max_text_characters:
        raise RecognitionInputError(
            f"Resume text exceeds {max_text_characters:,} characters. "
            "Split the text into sections before recognition."
        )

    tokens = tokenize_with_spans(text)
    truncated = len(tokens) > max_tokens
    if truncated:
        raise RecognitionInputError(
            f"Resume contains {len(tokens):,} tokens; the current limit is "
            f"{max_tokens:,}. Split the resume into sections before recognition."
        )

    normalised_text = unicodedata.normalize("NFKC", text)
    phrases: set[str] = set()
    for start in range(len(tokens)):
        upper = min(len(tokens), start + max_words)
        phrase_parts: list[str] = []
        for end in range(start, upper):
            if end > start and _crosses_hard_boundary(normalised_text, tokens[end - 1], tokens[end]):
                break
            phrase_parts.append(tokens[end].value)
            phrase = " ".join(phrase_parts)
            if len(phrase) >= 2:
                phrases.add(phrase)
                if len(phrases) > max_candidate_phrases:
                    raise RecognitionInputError(
                        "The resume generates too many lookup phrases. "
                        "Process it section-by-section or increase the configured limit."
                    )

    return sorted(phrases), tokens, truncated


def _crosses_hard_boundary(text: str, left: Token, right: Token) -> bool:
    """Prevent phrases from spanning sentence-ending punctuation or semicolons."""
    gap = text[left.end:right.start]
    return bool(re.search(r"[.!?;]", gap))


def _evidence_snippet(text: str, start: int, end: int, radius: int = 85) -> str:
    start_bound = max(0, start - radius)
    end_bound = min(len(text), end + radius)
    snippet = re.sub(r"\s+", " ", text[start_bound:end_bound]).strip()
    if start_bound > 0:
        snippet = "…" + snippet
    if end_bound < len(text):
        snippet += "…"
    return snippet


def _row_priority(row: SkillLabelRow) -> tuple[int, str, str]:
    return (
        _LABEL_TYPE_PRIORITY.get(row.label_type, 9),
        row.preferred_label.lower(),
        row.skill_uri,
    )


def recognise_from_label_rows(
    text: str,
    label_rows: Iterable[Mapping[str, Any] | SkillLabelRow],
    *,
    max_words: int = 12,
    max_candidate_phrases: int = 20_000,
    max_tokens: int = 5_000,
    max_text_characters: int = 40_000,
) -> RecognitionResult:
    """Recognise skills against rows returned by resolve_esco_skill_labels.

    Unique phrase-to-URI matches become confirmed detections. If one phrase
    maps to multiple distinct URIs, it is held for review and awards no URI.
    Longest matching phrase wins at a given text position. Each URI is credited
    once, while evidence occurrences are retained.
    """
    phrases, tokens, truncated = build_candidate_phrases(
        text,
        max_words=max_words,
        max_candidate_phrases=max_candidate_phrases,
        max_tokens=max_tokens,
        max_text_characters=max_text_characters,
    )

    rows: list[SkillLabelRow] = []
    for raw_row in label_rows:
        row = raw_row if isinstance(raw_row, SkillLabelRow) else SkillLabelRow.from_mapping(raw_row)
        if row.normalized_label and row.skill_uri:
            rows.append(row)

    phrase_set = set(phrases)
    phrase_row_map: dict[str, list[SkillLabelRow]] = defaultdict(list)
    for row in rows:
        if row.normalized_label in phrase_set:
            phrase_row_map[row.normalized_label].append(row)

    # Phrase tokens are indexed by their first token to avoid testing every
    # catalogue label at every resume position.
    phrase_index: dict[str, list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
    for phrase in phrase_row_map:
        phrase_tokens = tuple(token.value for token in tokenize_with_spans(phrase))
        if phrase_tokens:
            phrase_index[phrase_tokens[0]].append((phrase, phrase_tokens))

    for first_token in phrase_index:
        phrase_index[first_token].sort(key=lambda item: (-len(item[1]), item[0]))

    confirmed_by_uri: dict[str, SkillDetection] = {}
    review_by_uri: dict[str, ReviewSkill] = {}
    ambiguous_by_phrase: dict[str, AmbiguousSkill] = {}
    index = 0
    occupied_until = -1

    normalised_text = unicodedata.normalize("NFKC", text)

    while index < len(tokens):
        if index < occupied_until:
            index += 1
            continue

        possible: list[tuple[str, tuple[str, ...]]] = []
        for phrase, phrase_tokens in phrase_index.get(tokens[index].value, []):
            end_index = index + len(phrase_tokens)
            if end_index <= len(tokens) and tuple(
                token.value for token in tokens[index:end_index]
            ) == phrase_tokens and all(
                not _crosses_hard_boundary(normalised_text, tokens[pos], tokens[pos + 1])
                for pos in range(index, end_index - 1)
            ):
                possible.append((phrase, phrase_tokens))

        if not possible:
            index += 1
            continue

        # At the same starting position, prefer the longest exact phrase.
        longest_length = max(len(item[1]) for item in possible)
        longest = [item for item in possible if len(item[1]) == longest_length]
        chosen_phrases = sorted({item[0] for item in longest})
        chosen_phrase = chosen_phrases[0]
        phrase_rows = phrase_row_map[chosen_phrase]

        # If equally long normalised phrases resolve to different labels, merge
        # their rows and resolve by distinct canonical URI, not row count.
        if len(chosen_phrases) > 1:
            phrase_rows = [row for phrase in chosen_phrases for row in phrase_row_map[phrase]]
            chosen_phrase = " / ".join(chosen_phrases)

        end_index = index + longest_length
        start_char = tokens[index].start
        end_char = tokens[end_index - 1].end
        snippet = _evidence_snippet(normalised_text, start_char, end_char)

        # Collapse duplicate label types for the same canonical skill URI.
        best_row_by_uri: dict[str, SkillLabelRow] = {}
        for row in phrase_rows:
            current = best_row_by_uri.get(row.skill_uri)
            if current is None or _row_priority(row) < _row_priority(current):
                best_row_by_uri[row.skill_uri] = row

        if len(best_row_by_uri) == 1:
            row = next(iter(best_row_by_uri.values()))

            # Hidden labels are deliberately not promoted to confirmed skills.
            # Example: "reporting" is a hidden label for ESCO "report facts";
            # "built reporting tools" is not sufficient evidence of that skill.
            if row.label_type == "hidden":
                review = review_by_uri.get(row.skill_uri)
                if review is None:
                    review = ReviewSkill(
                        skill_uri=row.skill_uri,
                        preferred_label=row.preferred_label,
                    )
                    review_by_uri[row.skill_uri] = review

                if chosen_phrase not in review.matched_phrases:
                    review.matched_phrases.append(chosen_phrase)
                if snippet not in review.evidence_snippets and len(review.evidence_snippets) < 5:
                    review.evidence_snippets.append(snippet)
                review.occurrence_count += 1

            else:
                detection = confirmed_by_uri.get(row.skill_uri)
                if detection is None:
                    detection = SkillDetection(
                        skill_uri=row.skill_uri,
                        preferred_label=row.preferred_label,
                        label_type=row.label_type,
                        skill_type=row.skill_type,
                        reuse_level=row.reuse_level,
                    )
                    confirmed_by_uri[row.skill_uri] = detection
                else:
                    if _LABEL_TYPE_PRIORITY.get(row.label_type, 9) < _LABEL_TYPE_PRIORITY.get(detection.label_type, 9):
                        detection.label_type = row.label_type
                    if detection.skill_type is None:
                        detection.skill_type = row.skill_type
                    if detection.reuse_level is None:
                        detection.reuse_level = row.reuse_level

                if chosen_phrase not in detection.matched_phrases:
                    detection.matched_phrases.append(chosen_phrase)
                if snippet not in detection.evidence_snippets and len(detection.evidence_snippets) < 5:
                    detection.evidence_snippets.append(snippet)
                detection.occurrence_count += 1

        else:
            candidates = [
                AmbiguousCandidate(
                    skill_uri=row.skill_uri,
                    preferred_label=row.preferred_label,
                    skill_type=row.skill_type,
                    reuse_level=row.reuse_level,
                )
                for row in sorted(best_row_by_uri.values(), key=lambda item: (item.preferred_label.lower(), item.skill_uri))
            ]
            ambiguous = ambiguous_by_phrase.get(chosen_phrase)
            if ambiguous is None:
                ambiguous = AmbiguousSkill(
                    matched_phrase=chosen_phrase,
                    evidence_snippets=[snippet],
                    candidates=candidates,
                )
                ambiguous_by_phrase[chosen_phrase] = ambiguous
            else:
                ambiguous.occurrence_count += 1
                if snippet not in ambiguous.evidence_snippets and len(ambiguous.evidence_snippets) < 5:
                    ambiguous.evidence_snippets.append(snippet)

        occupied_until = end_index
        index = end_index

    confirmed = sorted(
        confirmed_by_uri.values(),
        key=lambda item: (item.preferred_label.lower(), item.skill_uri),
    )
    ambiguous = sorted(
        ambiguous_by_phrase.values(),
        key=lambda item: item.matched_phrase.lower(),
    )

    # If a skill URI has a stronger preferred/alternative-label match anywhere
    # in the resume, keep it confirmed and remove its weaker hidden-label review.
    review = sorted(
        (
            item for uri, item in review_by_uri.items()
            if uri not in confirmed_by_uri
        ),
        key=lambda item: (item.preferred_label.lower(), item.skill_uri),
    )

    return RecognitionResult(
        confirmed_skills=confirmed,
        ambiguous_matches=ambiguous,
        token_count=len(tokens),
        candidate_phrase_count=len(phrases),
        catalog_row_count=len(rows),
        review_matches=review,
        truncated=truncated,
    )


class SupabaseSkillCatalog:
    """Fetch matching ESCO labels through the indexed PostgreSQL RPC.

    The RPC is supplied in sql/02_resolve_esco_skill_labels.sql. This keeps the
    100k+ label catalogue in Postgres instead of loading it into FastAPI RAM.
    """

    def __init__(self, supabase_client: Any, *, rpc_name: str = "resolve_esco_skill_labels", chunk_size: int = 2_000):
        if chunk_size < 1 or chunk_size > 5_000:
            raise ValueError("chunk_size must be between 1 and 5,000")
        self.client = supabase_client
        self.rpc_name = rpc_name
        self.chunk_size = chunk_size

    def lookup(self, normalized_labels: Sequence[str]) -> list[dict[str, Any]]:
        unique_labels = sorted({normalize_label(value) for value in normalized_labels if value})
        results: list[dict[str, Any]] = []

        for offset in range(0, len(unique_labels), self.chunk_size):
            batch = unique_labels[offset:offset + self.chunk_size]
            response = self.client.rpc(
                self.rpc_name,
                {"p_normalized_labels": batch},
            ).execute()
            data = getattr(response, "data", None)
            if not isinstance(data, list):
                raise RuntimeError("Supabase label lookup returned an unexpected response.")
            results.extend(data)

        return results

    def recognise(self, text: str, **limits: Any) -> RecognitionResult:
        phrases, _, _ = build_candidate_phrases(text, **limits)
        rows = self.lookup(phrases)
        return recognise_from_label_rows(text, rows, **limits)


# American spelling alias for callers that prefer it.
recognize_from_label_rows = recognise_from_label_rows
