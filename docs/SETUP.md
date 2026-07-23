# Setup

Requires Python 3.11 or 3.12 and a supported desktop operating system.

`python scripts/setup.py --interactive` asks before installing system packages,
the optional ASR verification stack plus pinned model weights, or MFA. The core
package supports project creation and analysis without installing Whisper/PyTorch;
`--download-models` installs the verification extra automatically. `--yes`
accepts prompts only when combined with the desired explicit options; it never
downloads models during a production command.

## System tools

FFmpeg/FFprobe and eSpeak NG are required. The setup adapter supports Homebrew,
APT, DNF, Pacman, and Winget. If package IDs change, install the tools manually
and run `audiobook-harness doctor`.

## Alignment

MFA is intentionally separate from the Python virtual environment. Install
micromamba or mamba, then select the MFA option. Its models are stored under
`.tools/mfa-root`; set `MFA_ROOT_DIR` when using a custom location.

## Offline production

After setup, use `scripts/run` on POSIX systems or the venv executable on
Windows. These commands set Hugging Face/Transformers offline flags. The model
lock records source URLs and hashes; do not replace weights without updating and
reviewing it.

## Container smoke test

The harness is local-first rather than a published container runtime, but the
repository includes a **local onboarding smoke image**. It confirms that a clean
Linux container can install the Python package and required system tools, create
a project, and analyse a terse-dialogue sample through the contextual-performance
guard. It deliberately does **not**
download Kokoro, Whisper, or MFA models, and the `.dockerignore` prevents local
manuscripts, generated audio, environments, model caches, and Git history from
entering the build context.

```bash
docker build --no-cache -f Dockerfile.smoke -t audiobook-harness:smoke .
docker run --rm --network none audiobook-harness:smoke
```

A full generation/verification run additionally needs the explicit, pinned model
download and a locally installed MFA profile; it is intentionally not hidden in
the smoke image.
