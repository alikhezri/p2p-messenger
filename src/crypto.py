from typing import Dict, Tuple
from Crypto.Hash import SHA256
from Crypto.Signature import PKCS1_v1_5
from Crypto.Cipher import PKCS1_OAEP
from Crypto.PublicKey import RSA
import base64

RSA_LENGTH = 2048

def generate_keys() -> Tuple[RSA.RsaKey, RSA.RsaKey]:
    private_key = RSA.generate(RSA_LENGTH)
    public_key = private_key.publickey()

    return public_key, private_key


def encrypt_bytes(payload: bytes, key: RSA.RsaKey) -> bytes:
    cipher = PKCS1_OAEP.new(key)
    return cipher.encrypt(payload)


def decrypt_bytes(enc_payload: bytes, key: RSA.RsaKey) -> bytes:
    cipher = PKCS1_OAEP.new(key)
    return cipher.decrypt(enc_payload)


def load_key(key: str) -> RSA.RsaKey:
    key = base64.b64decode(key)
    return RSA.importKey(key)


def serialize_key(key: RSA.RsaKey) -> str:
    key = base64.b64encode(key.exportKey("DER")).decode("utf-8")
    return key


def sign(message: Dict, private_key: RSA.RsaKey) -> str:
    digest = SHA256.new()
    digest.update(str(message).encode("utf-8"))
    signer = PKCS1_v1_5.new(private_key)
    sig = signer.sign(digest)

    return base64.b64encode(sig).decode("utf-8")


def verify(message: Dict, sig: str, key) -> None:
    digest = SHA256.new()
    digest.update(str(message).encode("utf-8"))
    verifier = PKCS1_v1_5.new(key)
    verified = verifier.verify(digest, base64.b64decode(sig))

    return verified
