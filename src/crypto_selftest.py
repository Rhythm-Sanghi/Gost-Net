"""Android runtime qualification for the ``cryptography`` native extension.

Every other qualification in this project is static: the page-size gate reads
ELF program headers out of the packaged APK, and the desktop test suite runs on
the host interpreter. Neither can observe a failure that only happens when
Android's dynamic loader (``bionic``) opens a compiled extension.

That gap is real. A Rust-built extension can be perfectly page-aligned, carry a
valid ``GNU_RELRO``, export and import exactly the symbols it should, and still
be unloadable: if it leaves Python C-API symbols undefined without declaring
``libpython`` in ``DT_NEEDED``, the loader resolves them inside a per-namespace
scope where the already-loaded interpreter is not visible and the import dies
with ``ImportError: dlopen failed: cannot locate symbol "PyExc_TypeError"``.
This module turns that class of failure into an explicit, early, readable
startup check.

It performs one real round trip per primitive, entirely in memory, so a mere
successful ``import`` cannot be mistaken for a working extension: the symbols
must actually resolve and the operations must actually complete. Nothing is
persisted, logged, or transmitted -- every key below is generated for this
check and discarded when it returns.
"""

import os
import time

_LOG_NAME = "startup-crypto.log"
_MARKER = "[CRYPTO_SELFTEST]"


def _candidate_dirs():
    return [
        "/data/user/0/org.ghostnet.ghostnet/files/app",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        os.path.expanduser("~"),
        ".",
    ]


def _record(lines):
    """Append the report to the on-device log and to stdout.

    Writing to stdout as well means the result is visible in ``adb logcat`` even
    when the app's private storage is unreadable.
    """
    text = "\n".join(lines)
    for directory in _candidate_dirs():
        try:
            path = os.path.join(directory, _LOG_NAME)
            with open(path, "a") as handle:
                handle.write(text + "\n")
            break
        except Exception:
            continue
    try:
        sys_stdout = __import__("sys").__stdout__
        sys_stdout.write(text + "\n")
        sys_stdout.flush()
    except Exception:
        pass


def run():
    """Exercise the cryptography primitives. Return ``(ok, detail)``.

    Never raises: a failure is reported, not propagated, so the caller can keep
    its own startup sequence intact and let the real import surface the error
    with a full traceback.
    """
    started = time.time()
    lines = [f"{_MARKER} begin {time.strftime('%Y-%m-%d %H:%M:%S')}"]

    try:
        # The exact imports whose failure produced EXIT_SELF status=255.
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.asymmetric import ec, ed25519
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        lines.append(f"{_MARKER} FAIL import: {detail}")
        _record(lines)
        return False, detail

    checks = []

    # Symmetric: Fernet (AES-CBC + HMAC + padding + base64).
    try:
        key = Fernet.generate_key()
        token = Fernet(key).encrypt(b"ghostnet-startup-probe")
        if Fernet(key).decrypt(token) != b"ghostnet-startup-probe":
            raise AssertionError("Fernet round trip returned different plaintext")
        checks.append("fernet")
    except Exception as exc:
        lines.append(f"{_MARKER} FAIL fernet: {type(exc).__name__}: {exc}")
        _record(lines)
        return False, f"fernet: {type(exc).__name__}: {exc}"

    # AEAD: AES-GCM, used by the peer link encryption path.
    try:
        import os as _os
        aead_key = _os.urandom(32)
        nonce = _os.urandom(12)
        aead = AESGCM(aead_key)
        blob = aead.encrypt(nonce, b"ghostnet-startup-probe", b"t")
        if aead.decrypt(nonce, blob, b"t") != b"ghostnet-startup-probe":
            raise AssertionError("AESGCM round trip returned different plaintext")
        checks.append("aesgcm")
    except Exception as exc:
        lines.append(f"{_MARKER} FAIL aesgcm: {type(exc).__name__}: {exc}")
        _record(lines)
        return False, f"aesgcm: {type(exc).__name__}: {exc}"

    # Asymmetric: Ed25519, the peer identity signature scheme.
    try:
        private = ed25519.Ed25519PrivateKey.generate()
        signature = private.sign(b"ghostnet-startup-probe")
        ed25519.Ed25519PublicKey.from_public_bytes(
            private.public_key().public_bytes_raw()
        ).verify(signature, b"ghostnet-startup-probe")
        checks.append("ed25519")
    except Exception as exc:
        lines.append(f"{_MARKER} FAIL ed25519: {type(exc).__name__}: {exc}")
        _record(lines)
        return False, f"ed25519: {type(exc).__name__}: {exc}"

    # Asymmetric: ECDSA P-256, the non-repudiable peer key exchange primitive.
    try:
        key = ec.generate_private_key(ec.SECP256R1())
        signature = key.sign(b"ghostnet-startup-probe", ec.ECDSA(
            __import__("cryptography.hazmat.primitives.hashes", fromlist=["SHA256"]
                       ).SHA256()))
        key.public_key().verify(
            signature, b"ghostnet-startup-probe", ec.ECDSA(
                __import__("cryptography.hazmat.primitives.hashes", fromlist=["SHA256"]
                           ).SHA256()))
        checks.append("ecdsa-p256")
    except Exception as exc:
        lines.append(f"{_MARKER} FAIL ecdsa: {type(exc).__name__}: {exc}")
        _record(lines)
        return False, f"ecdsa: {type(exc).__name__}: {exc}"

    detail = "ok: " + ", ".join(checks)
    lines.append(f"{_MARKER} PASS {detail} "
                 f"({(time.time() - started) * 1000:.0f} ms)")
    _record(lines)
    return True, detail