"""Regenerate the checked-in synthetic speech corpus on macOS."""

from __future__ import annotations

from array import array
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile
import wave

from app.ai.eval_asr.runner import load_fixtures

ROOT = Path(__file__).parent
NOISY_IDS = {"noisy-mandarin-welding", "noisy-english-scaffold"}


def _add_site_like_noise(path: Path) -> None:
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        frames = source.readframes(params.nframes)
    random_source = random.Random(path.name)
    samples = array("h")
    samples.frombytes(frames)
    sample_rate = params.framerate
    for index, sample in enumerate(samples):
        machinery_hum = 450 * math.sin(2 * math.pi * 90 * index / sample_rate)
        clank_period = max(1, round(sample_rate * 0.7))
        clank = 2200 * (1 - (index % clank_period) / 320) if index % clank_period < 320 else 0
        noisy_sample = sample + round(
            random_source.gauss(0, 700) + machinery_hum + clank
        )
        samples[index] = max(-32768, min(32767, noisy_sample))
    mixed = samples.tobytes()
    with wave.open(str(path), "wb") as destination:
        destination.setparams(params)
        destination.writeframes(mixed)


def main() -> None:
    fixtures_path = ROOT / "fixtures.json"
    raw = json.loads(fixtures_path.read_text(encoding="utf-8"))
    fixtures = {item["id"]: item for item in raw}
    output = ROOT / "audio"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="safeloop-asr-") as temporary:
        temporary_path = Path(temporary)
        for fixture_id, fixture in fixtures.items():
            voice = "Tingting" if fixture["hint_locale"] == "zh-CN" else "Karen"
            aiff_path = temporary_path / f"{fixture_id}.aiff"
            wav_path = output / f"{fixture_id}.wav"
            subprocess.run(
                [
                    "/usr/bin/say",
                    "-v",
                    voice,
                    "-r",
                    "155",
                    "-o",
                    str(aiff_path),
                    fixture["reference"],
                ],
                check=True,
            )
            subprocess.run(
                [
                    "/usr/bin/afconvert",
                    "-f",
                    "WAVE",
                    "-d",
                    "LEI16@16000",
                    str(aiff_path),
                    str(wav_path),
                ],
                check=True,
            )
            if fixture_id in NOISY_IDS:
                _add_site_like_noise(wav_path)
    load_fixtures()


if __name__ == "__main__":
    main()
