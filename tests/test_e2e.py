"""Offline end-to-end coverage for source, attack, verifier, and report paths."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization

from attacker.scenarios import MODES, tamper
from tp.attacks import ALL_FAMILIES, make_attack
from tp.engine import TrustPipeline, build_report
from tp.provenance import Ground


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def _sample(index: int = 0):
    path = sorted(SAMPLES.glob("chip_*.npy"))[index]
    return np.load(path, allow_pickle=False), json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))


def _reset_ground(pipeline: TrustPipeline) -> None:
    pipeline.ground = Ground({pipeline.source.key_id: pipeline.source.public_key}, aoi_boxes=None)


def test_offline_path_runs_eight_scenarios_and_builds_report(tmp_path):
    chip, meta = _sample()
    pipeline = TrustPipeline("model")
    modes = ("passthrough", "pixels", "manifest_meta", "manifest_rehash", "resign", "replay", "strip", "stolen_key")
    assert set(modes) == set(MODES)
    key_path = tmp_path / "source_private.pem"
    key_path.write_bytes(pipeline.source._sk.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    replay_loot = {}
    outcomes = {}
    for mode in modes:
        _reset_ground(pipeline)
        packet = pipeline.acquire(chip, meta)
        loot = replay_loot if mode == "replay" else {}
        attacked = tamper(packet, mode, np.random.default_rng(31), family="inpaint_ns", severity="strong",
                          stolen_key_path=str(key_path), loot=loot)
        if mode == "replay":
            first = pipeline.process(attacked, kind=mode)
            assert first["status"] in {"TRUSTED", "SUSPICIOUS"}
            attacked = tamper(packet, mode, np.random.default_rng(32), loot=loot)
        result = pipeline.process(attacked, kind=mode)
        outcomes[mode] = result["status"]
        if mode in {"pixels", "manifest_meta", "manifest_rehash", "resign", "replay"}:
            assert result["status"] == "COMPROMISED", mode
        elif mode == "strip":
            assert result["status"] in {"SUSPICIOUS", "COMPROMISED"}
        elif mode == "stolen_key":
            assert result["evidence"]["provenance"] == "VALID"
            assert result["evidence"]["integrity"] == "PASS"
            assert result["status"] in {"SUSPICIOUS", "COMPROMISED"}
        else:
            assert result["status"] in {"TRUSTED", "SUSPICIOUS"}
        assert result["evidence"]["provenance"] in {"VALID", "INVALID", "UNKNOWN"}

    _reset_ground(pipeline)
    authentic = pipeline.process(pipeline.acquire(chip, meta), kind="none")
    report = build_report(authentic, meta)
    assert report["status"] in {"TRUSTED", "SUSPICIOUS"}
    assert len(report["report_sha256"]) == 64
    assert set(outcomes) == set(modes)


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_each_forgery_family_completes_signed_offline_pipeline_with_status(family):
    chip, meta = _sample()
    pipeline = TrustPipeline("model")
    donor = np.roll(chip, 37, axis=2)
    edited, mask, _record = make_attack(chip, donor, family, "strong", np.random.default_rng(2026), meta["offset"])
    assert edited.shape == (4, 256, 256) and edited.dtype == np.uint16
    assert np.any(mask)
    packet = pipeline.acquire(edited, meta)
    result = pipeline.process(packet, kind=f"family:{family}")
    assert result["status"] in {"TRUSTED", "SUSPICIOUS", "COMPROMISED"}
    assert result["evidence"]["provenance"] == "VALID"
    assert result["evidence"]["integrity"] == "PASS"
