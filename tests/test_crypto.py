"""Tests for evdc_network_api.crypto."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from evdc_network_api.crypto import (
    device_public_key,
    encrypt_password,
    generate_device_key,
    sign_device_payload,
)


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


def test_generate_device_key_is_an_rsa_2048_private_pem() -> None:
    pem = generate_device_key()
    key = serialization.load_pem_private_key(pem.encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size == 2048


def test_device_public_key_is_base64_der_spki() -> None:
    pem = generate_device_key()
    der = base64.b64decode(device_public_key(pem))
    key = serialization.load_der_public_key(der)  # parses as DER SubjectPublicKeyInfo
    assert isinstance(key, rsa.RSAPublicKey)


def test_sign_device_payload_verifies_with_public_key() -> None:
    pem = generate_device_key()
    payload = "1793118877"
    signature = base64.b64decode(sign_device_payload(pem, payload))
    public = serialization.load_der_public_key(base64.b64decode(device_public_key(pem)))
    assert isinstance(public, rsa.RSAPublicKey)
    # Raises InvalidSignature if the scheme (PKCS#1 v1.5 / SHA-256 over the payload bytes) is wrong.
    public.verify(signature, payload.encode(), padding.PKCS1v15(), hashes.SHA256())
