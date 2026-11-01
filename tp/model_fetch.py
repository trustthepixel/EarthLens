"""Fetch public Hugging Face model files when the local runtime needs them."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download
from tp.settings import get_setting

MODEL_FILES = ('detector.onnx', 'config.json', 'golden.npz')


class ModelUnavailable(RuntimeError):
    """Raised when a complete runtime model cannot be prepared."""


def resolve_model_repo() -> str:
    """Resolve the model repository from deployment configuration."""
    configured = get_setting('HF_MODEL_REPO')
    if not configured:
        raise ModelUnavailable('HF_MODEL_REPO is not configured. Set it to the public model repository.')
    return configured


def _nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _validate_config(config_path: Path) -> None:
    try:
        config: Any = json.loads(config_path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelUnavailable('The downloaded config.json could not be read.') from exc
    if not isinstance(config, dict) or not isinstance(config.get('calibration'), dict):
        raise ModelUnavailable("The downloaded config.json is incomplete: expected a 'calibration' object.")


def ensure_model(local: str | Path = 'model') -> Path:
    """Ensure all three runtime model artifacts exist and config is usable.

    Existing non-empty files are preserved. Public files are downloaded only for
    missing or empty paths; no Hugging Face authentication is requested.
    """
    directory = Path(local)
    directory.mkdir(parents=True, exist_ok=True)
    missing = [filename for filename in MODEL_FILES if not _nonempty(directory / filename)]
    repo = resolve_model_repo() if missing else ""
    current_file = "model artifacts"
    try:
        for filename in missing:
            current_file = filename
            target = directory / filename
            cached = Path(hf_hub_download(repo_id=repo, filename=filename, repo_type='model', etag_timeout=10))
            if not _nonempty(cached):
                raise OSError('Downloaded file is empty.')
            temporary = target.with_name(target.name + '.download')
            try:
                shutil.copyfile(cached, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
    except Exception as exc:
        if not all(_nonempty(directory / filename) for filename in MODEL_FILES):
            if not repo:
                raise ModelUnavailable('HF_MODEL_REPO is not configured.') from exc
            raise ModelUnavailable(
                f"Could not fetch '{current_file}' from the configured Hugging Face repository "
                f"({type(exc).__name__}). Check network access, proxy settings, and HF_MODEL_REPO."
            ) from exc
    _validate_config(directory / 'config.json')
    return directory


def main() -> int:
    try:
        directory = ensure_model()
    except ModelUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f'Model files are ready in {directory.as_posix()}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
