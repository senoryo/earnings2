from __future__ import annotations

from earnings2.parsers.base import CompanyParser

_REGISTRY: dict[str, type[CompanyParser]] = {}


def register_parser(cls: type[CompanyParser]) -> type[CompanyParser]:
    _REGISTRY[cls.company_slug] = cls
    return cls


def get_parser(company_slug: str) -> CompanyParser:
    if company_slug not in _REGISTRY:
        # Trigger import to register parsers
        if company_slug == "morgan-stanley":
            import earnings2.parsers.morgan_stanley.parser  # noqa: F401
        elif company_slug == "jp-morgan":
            import earnings2.parsers.jp_morgan.parser  # noqa: F401
        elif company_slug == "goldman-sachs":
            import earnings2.parsers.goldman_sachs.parser  # noqa: F401
    if company_slug not in _REGISTRY:
        raise ValueError(f"No parser registered for: {company_slug}")
    return _REGISTRY[company_slug]()
