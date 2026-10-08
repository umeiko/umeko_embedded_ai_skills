# Training and evaluation

## Run manifest

Write a manifest before launch. Include:

- experiment name and objective;
- base checkpoint path and hash/commit;
- dataset and pack hashes;
- tokenizer/template hashes;
- model architecture and precision;
- visible devices and DP/TP/PP;
- micro/global batch, sequence length, accumulation;
- optimizer, weight decay, clipping, LR schedule, warmup, seed;
- iterations/epochs, save and log intervals;
- master/HCCL ports;
- exact evaluation set and decoding fingerprint.

Refuse to write checkpoints into an existing run directory unless the request explicitly resumes that exact run and checkpoint/optimizer/RNG compatibility has been verified.

## Smoke test

Run 2–3 optimizer steps on an independent small pack. Check:

- data loader reads packed records;
- loss and gradient norm are finite;
- skipped and NaN iteration counts are zero;
- all ranks complete the same step;
- memory fits with expected headroom;
- the process exits cleanly and writes an explicit success marker.

Do not infer model quality from smoke loss.

## Full run

Use frequent logs early, then a practical interval. Save enough checkpoints to observe a curve instead of selecting only the last iteration. Keep data/pack immutable during a run.

For neat-packed instruction data, variable document layouts can make `micro_batch_size>1` invalid in some collators. Use MBS=1 until the installed loader is tested with multiple rows; reach the desired GBS with DP and accumulation.

Monitor loss, grad norm, learning rate, skipped/NaN counters, throughput, HBM, and checkpoint write time. Sudden loss changes after resume often indicate optimizer/RNG or data-index mismatch rather than new learning.

## Evaluation fingerprint

For every score, retain:

- model/checkpoint hash;
- tokenizer and chat-template hash;
- framework and hardware;
- evaluation data revision;
- batch size;
- greedy/beam/sampling parameters;
- prompt rendering mode;
- per-sentence predictions and their hash.

Batch size can affect deterministic beam output on accelerator backends. Treat it as part of the decoding configuration.

Compare candidates with a baseline anchor evaluated in the same run environment. Do not compare numbers from different accelerator generations or software stacks without re-running the anchor.

## Selection discipline

- Use greedy decoding for checkpoint selection when measuring learned model ability.
- Treat beam search as a deployment policy, not training gain.
- Select on a declared development set.
- Freeze checkpoint and decoding configuration before one-shot test evaluation.
- Require both aggregate metrics and regression slices; multilingual/bidirectional jobs can trade one direction for another.
- Use paired significance testing when point differences are small.

For small shared-parameter models, later fine-tuning can rotate capability between tasks instead of expanding it. Measure gradient conflict or direction-specific regression before spending more runs on post-training mixtures. Improving the main training corpus and sampling balance may be higher leverage than repeated short anneals.

## Quantization is a separate gate

Do not use training stability as proof of W8A8 safety. Inspect activation outliers and simulate the intended granularity:

- `max(abs(x)) / RMS(x)` by layer;
- channel-maximum imbalance;
- per-tensor, per-token, and per-channel quantization error;
- real calibration-set output quality.

If W8 is healthy but W8A8 collapses, first investigate activation scaling, SmoothQuant-style migration, or finer granularity. Do not automatically retrain the floating-point model to suppress useful outlier channels.
