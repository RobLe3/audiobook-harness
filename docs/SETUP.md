# Setup

Requires Python 3.11 or 3.12 and a supported desktop operating system.

`python scripts/setup.py --interactive` asks before installing system packages,
Python dependencies, model weights, or MFA. `--yes` accepts prompts only when
combined with the desired explicit options; it never downloads models during a
production command.

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
