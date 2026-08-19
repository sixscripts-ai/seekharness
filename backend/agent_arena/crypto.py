from cryptography.fernet import Fernet, InvalidToken

# Prefix format stored inside the ciphertext so we can support key rotation:
#   <key_id>:<fernet-token>
# ``VERSION_SEP`` is never produced by Fernet's url-safe base64 alphabet, so
# splitting is unambiguous. ``v1`` is the implicit default for ciphertexts
# written before versioning existed (no prefix present).
_VERSION_SEP = ":"
_DEFAULT_VERSION = "v1"


def new_key() -> bytes:
    return Fernet.generate_key()


def _apply_version(version: str, token: str) -> str:
    return f"{version}{_VERSION_SEP}{token}" if version else token


def encrypt_key(plaintext: str, key: bytes, version: str = _DEFAULT_VERSION) -> str:
    token = Fernet(key).encrypt(plaintext.encode()).decode()
    return _apply_version(version, token)


def decrypt_key(token: str, key: bytes) -> str:
    # Peek at an optional version id before the separator; the decryption key
    # is still supplied by the caller so rotation is handled at the call site
    # via a multi-key lookup (see providers._fernet_keys()).
    _stripped = token
    if _VERSION_SEP in token:
        head, _stripped = token.split(_VERSION_SEP, 1)
        if head not in (_DEFAULT_VERSION, "v1", "v2", "master", "rotated"):
            # Unknown explicit version marker — fail rather than guess.
            raise ValueError("Unknown key version")
    try:
        return Fernet(key).decrypt(_stripped.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid key or tampered ciphertext") from exc


def mask_key(plaintext: str) -> str:
    if len(plaintext) <= 8:
        return "*" * len(plaintext)
    return f"{plaintext[:4]}{'*' * 8}{plaintext[-4:]}"
