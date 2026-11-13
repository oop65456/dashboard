"""Encrypts the data published to GitHub Pages, so only someone with your passphrase can read it.

GitHub Pages sites on a free account are public. The page itself is harmless, but the market data and
headlines come from free plans for personal use (Twelve Data: "internal non-display usage only"), so
they are published encrypted: AES-256-GCM with a key made from your passphrase (PBKDF2-SHA256,
250,000 rounds). Your browser decrypts them after you type the passphrase (built-in WebCrypto).
Files are gzip-compressed before encrypting, so they also download faster on a phone.
"""
import base64
import gzip
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 250_000


def b64(b):
    return base64.b64encode(b).decode("ascii")


def salt_for(repo):
    """The salt doesn't need to be secret, only the same on the PC, on GitHub Actions and in the browser."""
    return f"signal-dashboard/v1/{repo.lower()}".encode()


def derive_key(passphrase, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(passphrase.encode())


def encrypt(key, data):
    """bytes -> small JSON-able dict {iv, data}. A fresh random IV every time, as AES-GCM requires."""
    iv = os.urandom(12)
    return {"v": 1, "iv": b64(iv), "data": b64(AESGCM(key).encrypt(iv, gzip.compress(data, 9), None))}


def decrypt(key, blob):
    """The reverse of encrypt (used by the tests; the browser does this in JavaScript)."""
    iv, ct = base64.b64decode(blob["iv"]), base64.b64decode(blob["data"])
    return gzip.decompress(AESGCM(key).decrypt(iv, ct, None))
