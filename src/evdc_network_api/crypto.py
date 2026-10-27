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


def generate_device_key() -> str:
    """Create a new RSA-2048 private key for biometric device-key login, as a PKCS#8 PEM string.

    The matching public key is registered with the account (see ``device_public_key``). Keep the private key
    outside the repository, like the tokens: it is a long-term login credential.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def _load_device_key(private_key_pem: str) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("Device key is not an RSA private key")
    return key


def device_public_key(private_key_pem: str) -> str:
    """The public half of a device key, base64-encoded DER (SubjectPublicKeyInfo), as the app registers it."""
    der = (
        _load_device_key(private_key_pem)
        .public_key()
        .public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    return base64.b64encode(der).decode("ascii")


def sign_device_payload(private_key_pem: str, payload: str) -> str:
    """Sign a biometric-login *payload* with the device key: RSA PKCS#1 v1.5 over SHA-256, base64."""
    signature = _load_device_key(private_key_pem).sign(payload.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")
