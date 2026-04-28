#!/usr/bin/env python3
"""Pre-download and validate the faster-whisper STT model used by FRIDAY."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ConfigManager  # noqa: E402


def _config_value(key, default):
    config = ConfigManager(str(PROJECT_ROOT / "config.yaml"))
    config.load()
    return config.get(key, default)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download FRIDAY's faster-whisper model into the local Hugging Face cache."
    )
    parser.add_argument(
        "--model",
        default=os.getenv("FRIDAY_WHISPER_MODEL") or _config_value("voice.stt_model", "base.en"),
        help="faster-whisper model name or local path. Default: config voice.stt_model.",
    )
    parser.add_argument(
        "--compute-type",
        default=os.getenv("FRIDAY_WHISPER_COMPUTE_TYPE") or _config_value("voice.stt_compute_type", "int8"),
        help="CTranslate2 compute type. Default: config voice.stt_compute_type.",
    )
    parser.add_argument(
        "--download-root",
        default=os.getenv("FRIDAY_WHISPER_DOWNLOAD_ROOT") or _config_value("voice.stt_download_root", None),
        help="Optional model cache directory. Default: config voice.stt_download_root or Hugging Face cache.",
    )
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=int(
            os.getenv("FRIDAY_WHISPER_CPU_THREADS")
            or _config_value("voice.stt_cpu_threads", max(1, min(8, os.cpu_count() or 1)))
        ),
        help="CPU threads to use while validating model load. Default: config voice.stt_cpu_threads.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"Preparing faster-whisper model: {args.model}")
    print(f"Compute type: {args.compute_type}")
    if args.download_root:
        print(f"Download root: {args.download_root}")
    else:
        print("Download root: default Hugging Face cache")

    from faster_whisper import WhisperModel

    WhisperModel(
        args.model,
        device="cpu",
        compute_type=args.compute_type,
        cpu_threads=args.cpu_threads,
        download_root=args.download_root,
    )

    print("STT model is downloaded and loadable.")


if __name__ == "__main__":
    main()
