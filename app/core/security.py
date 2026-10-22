import hmac


def token_matches(given: str, expected: str) -> bool:
    """Comparacion en tiempo constante; un token esperado vacio nunca coincide."""
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())
