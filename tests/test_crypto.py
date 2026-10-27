"""Tests for evdc_network_api.crypto."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from evdc_network_api.crypto import encrypt_password


def _keypair() -> tuple[rsa.RSAPrivateKey, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, pem


def test_encrypt_password_is_rsa_oaep_sha256() -> None:
    private, pem = _keypair()
    ciphertext = base64.b64decode(encrypt_password("pässwörd", pem))
    plain = private.decrypt(
        ciphertext,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    )
    assert plain == "pässwörd".encode()


def test_encrypt_password_is_randomised() -> None:
    _, pem = _keypair()
    assert encrypt_password("secret", pem) != encrypt_password("secret", pem)


def test_default_key_is_rsa_2048() -> None:
    assert len(base64.b64decode(encrypt_password("secret"))) == 256
