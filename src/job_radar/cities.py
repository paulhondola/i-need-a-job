import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

_HYPHEN_SPACE_RE = re.compile(r"[-\s]+")
_ROMANIA_WORD_RE = re.compile(r"(?<!\w)romania(?!\w)")
_REMOTE_WORD_RE = re.compile(r"(?<!\w)remote(?!\w)")
_RO_CODE_RE = re.compile(r"(?:^|[\s,(/-])RO(?:$|[\s,)/-])")


def _strip_diacritics(text: str) -> str:
    # NFKD splits both ș (comma) and ş (cedilla), plus ț/ţ/ă/â/î, into base + combining mark.
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def fold(text: str) -> str:
    """Strip diacritics, casefold, and collapse whitespace."""
    return " ".join(_strip_diacritics(text).casefold().split())


def _lookup_key(text: str) -> str:
    return _HYPHEN_SPACE_RE.sub(" ", fold(text))


def _compile_aliases(aliases: Iterable[str]) -> re.Pattern[str] | None:
    parts = [
        r"[-\s]+".join(
            re.escape(seg) for seg in _HYPHEN_SPACE_RE.split(fold(alias)) if seg
        )
        for alias in aliases
    ]
    parts = [p for p in parts if p]
    if not parts:
        return None
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)")


@dataclass(frozen=True)
class CitySpec:
    canonical: str
    aliases: tuple[str, ...]
    search_terms: tuple[str, ...]


ROMANIAN_CITIES: tuple[CitySpec, ...] = (
    CitySpec("Timișoara", ("timisoara",), ("Timisoara",)),
    CitySpec("Bucharest", ("bucharest", "bucuresti"), ("Bucharest", "Bucuresti")),
    CitySpec("Cluj-Napoca", ("cluj-napoca", "cluj"), ("Cluj",)),
    CitySpec("Iași", ("iasi",), ("Iasi",)),
    CitySpec("Brașov", ("brasov",), ("Brasov",)),
    CitySpec("Sibiu", ("sibiu",), ("Sibiu",)),
    CitySpec("Oradea", ("oradea",), ("Oradea",)),
    CitySpec("Craiova", ("craiova",), ("Craiova",)),
    CitySpec("Constanța", ("constanta",), ("Constanta",)),
    CitySpec("Arad", ("arad",), ("Arad",)),
    CitySpec("Ploiești", ("ploiesti",), ("Ploiesti",)),
    CitySpec(
        "Târgu Mureș",
        ("targu mures", "tg mures", "tg. mures"),
        ("Targu Mures",),
    ),
    CitySpec("Pitești", ("pitesti",), ("Pitesti",)),
    CitySpec("Galați", ("galati",), ("Galati",)),
    CitySpec("Bacău", ("bacau",), ("Bacau",)),
)

_CATALOG_BY_KEY: dict[str, CitySpec] = {
    _lookup_key(alias): spec for spec in ROMANIAN_CITIES for alias in spec.aliases
}
_ALL_CATALOG_RE = _compile_aliases(
    alias for spec in ROMANIAN_CITIES for alias in spec.aliases
)


def _has_ro_code(location: str) -> bool:
    return _RO_CODE_RE.search(location) is not None


@dataclass(frozen=True)
class CityFilter:
    cities: tuple[CitySpec, ...]
    is_all: bool = False
    _alias_re: re.Pattern[str] | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        alias_re = (
            _ALL_CATALOG_RE
            if self.is_all
            else _compile_aliases(
                alias for spec in self.cities for alias in spec.aliases
            )
        )
        object.__setattr__(self, "_alias_re", alias_re)

    @property
    def label(self) -> str:
        if self.is_all:
            return "Romania"
        return ", ".join(spec.canonical for spec in self.cities)

    def matches(self, location: str) -> bool:
        plain = fold(location)
        if not plain:
            return False
        if self.is_all:
            return (
                _ROMANIA_WORD_RE.search(plain) is not None
                or _has_ro_code(location)
                or (
                    self._alias_re is not None
                    and self._alias_re.search(plain) is not None
                )
            )
        if self._alias_re is not None and self._alias_re.search(plain) is not None:
            return True
        if plain == "romania":
            return True
        return _REMOTE_WORD_RE.search(plain) is not None and (
            _ROMANIA_WORD_RE.search(plain) is not None or _has_ro_code(location)
        )

    def search_terms(self) -> tuple[str, ...]:
        terms: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            if term not in seen:
                seen.add(term)
                terms.append(term)

        if self.is_all:
            _add("Romania")
            for spec in ROMANIAN_CITIES:
                for term in spec.search_terms:
                    _add(term)
        else:
            for spec in self.cities:
                for term in spec.search_terms:
                    _add(term)
            _add("Romania")
        return tuple(terms)


DEFAULT_CITY_FILTER = CityFilter(cities=(ROMANIAN_CITIES[0],))


def _fallback_city(raw_token: str) -> CitySpec:
    cleaned = " ".join(raw_token.split())
    canonical = cleaned if any(c.isupper() for c in cleaned) else cleaned.title()
    ascii_term = _strip_diacritics(canonical)
    return CitySpec(
        canonical=canonical, aliases=(fold(cleaned),), search_terms=(ascii_term,)
    )


def parse_city_filter(raw: list[str] | None) -> CityFilter:
    """Parse CLI --city values into a CityFilter (defaults to Timișoara when omitted)."""
    if raw is None:
        return DEFAULT_CITY_FILTER
    tokens = [part.strip() for item in raw for part in item.split(",") if part.strip()]
    if not tokens:
        raise ValueError("at least one city name is required")
    if any(fold(tok) in {"all", "romania"} for tok in tokens):
        return CityFilter(cities=(), is_all=True)

    resolved: list[CitySpec] = []
    seen_keys: set[str] = set()
    for tok in tokens:
        spec = _CATALOG_BY_KEY.get(_lookup_key(tok)) or _fallback_city(tok)
        key = _lookup_key(spec.aliases[0])
        if key not in seen_keys:
            seen_keys.add(key)
            resolved.append(spec)
    return CityFilter(cities=tuple(resolved))
