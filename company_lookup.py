"""Company identity matching shared by saved reports and the search box."""
import re
import json
from functools import lru_cache
from pathlib import Path


DIRECTORY_PATH = Path(__file__).parent / "data" / "company_directory.json"


@lru_cache(maxsize=1)
def load_company_directory():
    """The deployment bundles identities; no visitor request downloads this file."""
    try:
        return json.loads(DIRECTORY_PATH.read_text())["companies"]
    except (OSError, ValueError, KeyError):
        return []


# Familiar names also work when Yahoo's name-search endpoint is unavailable.
# These are identities, not fabricated reports or additions to the ranked universe.
COMMON_COMPANIES = {
    "AAPL": ("Apple Inc.", ["Apple"]),
    "NVDA": ("NVIDIA Corporation", ["Nvidia"]),
    "MSFT": ("Microsoft Corporation", ["Microsoft"]),
    "TSLA": ("Tesla, Inc.", ["Tesla"]),
    "AMZN": ("Amazon.com, Inc.", ["Amazon", "Amazon.com"]),
    "GOOGL": ("Alphabet Inc.", ["Google", "Alphabet"]),
    "META": ("Meta Platforms, Inc.", ["Meta", "Facebook"]),
    "GM": ("General Motors Company", ["General Motors"]),
    "INTC": ("Intel Corporation", ["Intel"]),
    "AMD": ("Advanced Micro Devices, Inc.", ["Advanced Micro Devices"]),
    "NFLX": ("Netflix, Inc.", ["Netflix"]),
    "MOD": ("Modine Manufacturing Company", ["Modine"]),
    "IESC": ("IES Holdings, Inc.", ["IES"]),
    "ACLS": ("Axcelis Technologies, Inc.", ["Axcelis"]),
    "POWL": ("Powell Industries, Inc.", ["Powell"]),
    "ONTO": ("Onto Innovation Inc.", ["Onto"]),
    "NVMI": ("Nova Ltd.", ["Nova"]),
    "AMKR": ("Amkor Technology, Inc.", ["Amkor"]),
    "TMDX": ("TransMedics Group, Inc.", ["TransMedics"]),
    "MYRG": ("MYR Group Inc.", ["MYR"]),
    "FLR": ("Fluor Corporation", ["Fluor"]),
}


def normalize_company_name(value):
    value = value.casefold().strip().replace("&", " and ")
    value = re.sub(r"[.,'’]", "", value).replace("-", " ")
    value = " ".join(value.split())
    if value.startswith("the "):
        value = value[4:]
    endings = (" corporation", " corp", " incorporated", " inc", " company",
               " co", " ltd", " limited", " plc", " group", " holdings",
               " holding", " technologies", " technology", " sa", " nv", " ag")
    while any(value.endswith(ending) for ending in endings):
        value = next(value[:-len(ending)].strip() for ending in endings if value.endswith(ending))
    return value


def company_catalog(reports=()):
    companies = {item["symbol"]: item for item in load_company_directory()}
    companies.update({symbol: {"symbol": symbol, "name": name}
                      for symbol, (name, _) in COMMON_COMPANIES.items()})
    for report in reports:
        companies[report["symbol"]] = {"symbol": report["symbol"], "name": report["name"], "saved": True}
    return list(companies.values())


def names_for(company):
    return normalized_names(company["symbol"], company["name"])


@lru_cache(maxsize=20000)
def normalized_names(symbol, name):
    names = [name]
    common = COMMON_COMPANIES.get(symbol)
    if common:
        names.extend([common[0], *common[1]])
    return frozenset(normalize_company_name(name) for name in names)


def resolve_company(query, companies, *, allow_prefix=False):
    """Resolve tickers or unambiguous names, optionally accepting whole-word prefixes."""
    query = query.strip()
    companies = list(companies)
    symbol = query.upper().lstrip("$").replace(".", "-")
    exact = [c["symbol"] for c in companies if c["symbol"].upper() == symbol]
    if len(set(exact)) == 1:
        return exact[0]
    name = normalize_company_name(query)
    matches = {c["symbol"] for c in companies if name and name in names_for(c)}
    if not matches and allow_prefix and len(name) >= 3:
        matches = {c["symbol"] for c in companies
                   if any(candidate.startswith(name + " ") for candidate in names_for(c))}
    return next(iter(matches)) if len(matches) == 1 else None


def matching_companies(query, companies, limit=8):
    normalized = normalize_company_name(query)
    symbol = query.strip().upper().lstrip("$").replace(".", "-")
    if not normalized:
        return []
    matches = []
    for company in companies:
        names = names_for(company)
        if company["symbol"] == symbol:
            rank = 0
        elif normalized in names:
            rank = 1
        elif any(name.startswith(normalized) for name in names):
            rank = 2
        elif company["symbol"].startswith(symbol):
            rank = 3
        elif any(normalized in name for name in names):
            rank = 4
        else:
            continue
        priority = 0 if company.get("saved") else 1 if company["symbol"] in COMMON_COMPANIES else 2
        matches.append((rank, priority, company["name"].casefold(), company))
    return [{"symbol": item[3]["symbol"], "name": item[3]["name"]}
            for item in sorted(matches, key=lambda item: item[:3])[:limit]]
