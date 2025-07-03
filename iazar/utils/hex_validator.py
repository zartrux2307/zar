class HexNonceValidator:
    """Simple validator for hexadecimal nonce strings."""
    def __init__(self, min_length: int = 1, max_length: int = 64):
        self.min_length = min_length
        self.max_length = max_length
        self.allowed = set('0123456789abcdefABCDEF')

    def is_valid(self, nonce: str) -> bool:
        if not isinstance(nonce, str):
            return False
        length = len(nonce)
        if length < self.min_length or length > self.max_length:
            return False
        return all(c in self.allowed for c in nonce)
