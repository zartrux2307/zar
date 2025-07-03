from cryptography.fernet import Fernet

class AESNonceEncryptor:
    def __init__(self, key=None):
        self.key = key or Fernet.generate_key()
        self.cipher = Fernet(self.key)

    def encrypt(self, nonce: str) -> str:
        return self.cipher.encrypt(nonce.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self.cipher.decrypt(token.encode()).decode()
