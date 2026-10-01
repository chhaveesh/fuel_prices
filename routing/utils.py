import re

_PREFIXES = [
    (re.compile(r"^st\.?\s+"), "saint "),
    (re.compile(r"^ste\.?\s+"), "sainte "),
    (re.compile(r"^ft\.?\s+"), "fort "),
    (re.compile(r"^mt\.?\s+"), "mount "),
]


def normalize_city(name: str) -> str:
    """Normalize a city name so 'St. Louis ' and 'Saint Louis' match."""
    s = name.strip().lower()
    for pattern, repl in _PREFIXES:
        s = pattern.sub(repl, s)
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def city_key(city: str, state: str) -> str:
    return f"{normalize_city(city)}|{state.strip().upper()}"
