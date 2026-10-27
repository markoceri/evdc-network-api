"""Client-side crypto used by the EVDC app."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .const import PASSWORD_ENC_PUBLIC_KEY


def encrypt_password(password: str, public_key_pem: str = PASSWORD_ENC_PUBLIC_KEY) -> str:
    """Encrypt *password* the way the app does for ``/api/signIn-enc``.

    RSA-OAEP with SHA-256 for both the hash and MGF1, over the UTF-8 password, base64-encoded.
    """
    key = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(key, rsa.RSAPublicKey):
        raise TypeError("Password encryption key is not an RSA public key")
    ciphertext = key.encrypt(
        password.encode("utf-8"),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(ciphertext).decode("ascii")
