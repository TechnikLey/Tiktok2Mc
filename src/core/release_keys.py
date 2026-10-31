"""Release signing key material (Stufe-1 Ed25519 manifest signing).

The release workflow (``build.py``) signs ``manifest.json`` releases with the
private Ed25519 key (CI secret ``T2M_SIGNING_PRIVATE_KEY``, raw hex). The
matching public key is shipped **in code** — the updater binary must verify
manifests against a key it trusts, never against key material delivered
together with the update itself.

Key generation (done once; regenerate only with a coordinated rotation):

    python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import \\
        Ed25519PrivateKey; k = Ed25519PrivateKey.generate(); \\
        print(k.public_key().public_bytes_raw().hex())"

The private key never enters this repository — it lives in CI secrets and
in the maintainer's local ``signing/`` directory (gitignored).
"""

from __future__ import annotations

from typing import Final

# Ed25519 public key (raw, hex). Rotating this value invalidates every
# release signed before the rotation — coordinate with a version bump and
# a fresh release chain.
RELEASE_SIGNING_PUBLIC_KEY: Final[str] = (
    "aff98a5da11b8fd3a95086154e8aedc8a189a06d9183b5ead2deda7dcd5f3f1d"
)
