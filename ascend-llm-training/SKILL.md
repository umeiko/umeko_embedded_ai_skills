---
name: ascend-llm-training
description: Plan, launch, monitor, and debug LLM pretraining or supervised fine-tuning on Huawei Ascend NPUs with CANN, torch_npu, MindSpeed-LLM, or Megatron-LM. Use for containerized multi-card training, packed instruction datasets, HCCL jobs, checkpoint evaluation, and Ascend-specific loading failures; not for CUDA-only workflows.
---

# Ascend LLM Training

Run Ascend training as a reproducible pipeline, not as a one-off shell command. Preserve data lineage, environment fingerprints, launch arguments, checkpoints, predictions, and failure evidence so another operator can resume or audit the run.

## Route the task

- For host/container setup, NPU inventory, CANN environment loading, ports, and model-loading hangs, read [environment.md](references/environment.md).
- For instruction data, document isolation, neat packing, supervision masks, and order-independent audits, read [packing.md](references/packing.md).
- For smoke tests, full training, checkpoint selection, and deterministic evaluation, read [training-and-evaluation.md](references/training-and-evaluation.md).
- For common failure signatures and safe recovery, read [troubleshooting.md](references/troubleshooting.md).

## Required workflow

1. **Discover the real environment.** Identify the validated container or virtual environment, framework revision, tokenizer/model paths, visible devices, free disk, running jobs, and ownership boundaries. Run `scripts/ascend_preflight.sh` when a shell is available. Do not stop unknown processes or reboot a shared host merely because an NPU looks occupied.
2. **Freeze the experiment contract.** Record base checkpoint, data and tokenizer hashes, architecture flags, DP/TP/PP, sequence length, micro/global batch sizes, optimizer, LR schedule, seed, HCCL/master ports, save cadence, and evaluation configuration before the full run.
3. **Audit data before expensive compute.** Use the framework's official preprocessing path for production data. Verify document isolation, target-only supervision, segment/sample conservation, target tails, empty/NUL/control-character gates, and content hashes. Treat positional metadata joins as invalid when the packer can reorder samples.
4. **Run a small independent smoke test.** Use a separate tiny pack and output directory for 2–3 optimizer steps. Require finite loss and gradient norm, zero skipped/NaN iterations, successful data loading, and an explicit success marker. A smoke test validates plumbing, not model quality.
5. **Launch the full job recoverably.** Use a unique run directory and ports. Refuse to overwrite checkpoints. Launch independently of the SSH session, then verify the actual trainer process, NPU utilization, and advancing iteration logs. Command submission or `docker exec -d` success is not evidence that training started.
6. **Evaluate with a same-environment anchor.** Convert/evaluate candidates and the baseline on the same host, framework, tokenizer, batch size, and decoding settings. Select checkpoints on the declared development set; touch an untouched test set only after weights and decoding are frozen.
7. **Close the loop.** Write a machine-readable selection decision, retain failed-run evidence, and leave no unexplained accelerator processes. Do not promote a checkpoint merely because one direction, one metric, or beam search improved.

## Non-obvious invariants

- A message such as `Loading checkpoint shards: 100%` only proves CPU-side file loading. Confirm the model reached the NPU with memory/utilization or a real forward pass.
- File-backed safetensors pages can hang during host-to-NPU transfer on some stacks. Materializing parameters and buffers into anonymous CPU memory with `clone()` before `.to("npu")` is a valid diagnostic/workaround; verify numerical equality and memory headroom first.
- For packed instruction SFT, use `micro_batch_size=1` unless the active collator is proven to support multiple variable document-boundary layouts. Build the global batch through data parallelism and accumulation.
- Balance multilingual or bidirectional training by **supervised target tokens**, not row counts. Report static corpus balance separately from effective sampler exposure.
- Weight-only INT8 success does not imply W8A8 safety. Activation outliers can leave W8 nearly lossless while destroying activation-quantized inference; diagnose activation scales independently from training stability.
- Keep pure-CPU utilities from accidentally importing an unavailable NPU backend by setting `TORCH_DEVICE_BACKEND_AUTOLOAD=0` when appropriate. Do not set it for jobs that actually need automatic NPU integration unless the stack explicitly imports `torch_npu` itself.

## Safety and scope

Use placeholders or environment variables in reusable scripts. Never publish host addresses, usernames, private mount paths, SSH keys, access tokens, internal model names, dataset identities, or proprietary metrics. External uploads, service restarts, process termination, and repository pushes require the user's authorization for that specific scope.
