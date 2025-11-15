from typing import Set

VALID_TOKENS: Set[str] = set()


def add_token(token: str) -> None:
    VALID_TOKENS.add(token)


def is_token_valid(token: str) -> bool:
    return token in VALID_TOKENS
