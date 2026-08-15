from __future__ import annotations

PRODUCT_ID = "jp-ru-kolobok-400k"
PRODUCT_NAME = "Колобок 400k"
DICTIONARY_VERSION = "1.0"
COMPILATION_DATETIME_UTC = "2026-08-15T21:04:30Z"
VERSIONED_PRODUCT_ID = f"{PRODUCT_ID}-v{DICTIONARY_VERSION}"
VERSIONED_PRODUCT_NAME = f"{PRODUCT_NAME} v{DICTIONARY_VERSION}"
DICTIONARY_AUTHORS = "Stephen Kraus; Yuri Katkov"
ATTRIBUTION = (
    f"Dictionary version: {DICTIONARY_VERSION}.\n"
    f"Compilation datetime (UTC): {COMPILATION_DATETIME_UTC}.\n"
    "Jitendex, JMdict and Tatoeba attribution is retained.\n"
    "Russian derivative content is distributed under CC BY-SA 4.0.\n"
    "Russian edition co-author: Yuri Katkov.\n"
    "Соавтор русской редакции: Юрий Катков.\n"
    "See the upstream Jitendex project for complete source attribution.\n"
)


def release_description(description: str) -> str:
    """Add stable, user-visible release identity to native format metadata."""
    return (
        f"{description} Версия словаря {DICTIONARY_VERSION}. "
        f"Дата и время компиляции (UTC): {COMPILATION_DATETIME_UTC}."
    )
