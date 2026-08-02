# External reproducibility and maturity

The supported claim is **controlled maintainer-operated local production** on
Python 3.12 with locally installed FFmpeg/FFprobe, eSpeak, MFA, and explicitly
provisioned models. Windows, network/synchronised/FUSE filesystems, unattended
multi-user operation, stable Python API compatibility, and third-party support
are not currently supported claims.

Run the model-free fixture from a clean checkout:

```bash
uv sync --extra dev
uv run python scripts/run-fixture.py
uv run python scripts/audit-provenance.py
```

`uv.lock` is the sole Python dependency authority. Models are described in
`models.lock.json`; normal production never downloads them. Receipts retain
their own historical schema/version evidence. Project migration is explicit via
`audiobook-harness upgrade-project` and compatibility is inspected with
`audiobook-harness compatibility-audit`; neither command silently rewrites
media or approved evidence.
