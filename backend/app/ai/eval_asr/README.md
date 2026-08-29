# SafeLoop ASR evaluation

This corpus is deliberately separate from pytest and is blocked when `CI` is set. It contains
ten short, checked-in 16 kHz PCM fixtures covering clean Mandarin, clean English,
Mandarin/English code-switching, and speech mixed with deterministic machinery hum, broadband
noise, and impact sounds. The voices are synthetic, so a later field-recorded corpus should
supplement rather than replace these repeatable regression fixtures.

With Vertex credentials and `VERTEX_PROJECT_ID` configured, run from `backend/`:

```sh
python -m app.ai.eval_asr
```

The command uses Vertex AI in the configured `asia-southeast1` region and reports per-case
character and word error rates. For this small synthetic baseline, investigate clean Mandarin
CER above 15% or noisy Mandarin CER above 30%; do not treat those thresholds as a production
acceptance study.

To compare the explicitly approved global Gemini 3.5 Transcribe Live preview, run:

```sh
python -m app.ai.eval_asr --provider live
```

The live harness paces each fixture as 16 kHz microphone PCM and is intentionally slower than
the synchronous evaluation.

To check only the scoring and fixture plumbing without a network call:

```sh
python -m app.ai.eval_asr --provider stub
```

Regenerate the synthetic audio on macOS with:

```sh
python -m app.ai.eval_asr.generate_fixtures
```
