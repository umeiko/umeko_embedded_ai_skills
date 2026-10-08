# Troubleshooting and safe recovery

## Trainer exits immediately

Check the outer launcher log, container log, and every rank's first exception. Frequent causes:

- environment script exited under `set -u` because a variable was undefined;
- host Python was used instead of the validated container;
- master or HCCL port collision;
- checkpoint/output directory already exists;
- data prefix points to host-only or container-only storage;
- a shell line continuation was lost, turning `--argument` into a separate command.

Run `bash -n`, but also inspect the rendered command. Syntax checks cannot detect a missing continuation when the resulting script remains valid shell.

## Shards load, NPU stays idle

`from_pretrained` progress is CPU-side. Determine whether the stall is configuration validation, NPU transfer, or first forward pass. Check HBM and add timestamps around those boundaries.

If file-backed page pinning is implicated, use the clone-to-anonymous-memory workaround in [environment.md](environment.md). Do not repeatedly start more replicas of a hanging loader.

## CPU-only script fails importing torch_npu/CANN

When a utility genuinely needs only CPU tensors, run it with:

```bash
TORCH_DEVICE_BACKEND_AUTOLOAD=0 python utility.py
```

Do not apply this blindly to NPU training; some stacks rely on backend autoload unless they explicitly import `torch_npu`.

## HBM allocated but no progress

HBM allocation alone is not health. Inspect AICore use, rank logs, rendezvous state, data-loader progress, and process stack. A service is healthy only after its health endpoint and a real inference request succeed.

## NPU error after an interrupted job

Identify remaining ranks in both host and container namespaces. Stop only processes owned by the current authorized run. Recheck ports and NPU state before retrying. Do not reboot a shared machine as the first recovery action.

If the device remains unhealthy after all owned processes exit, preserve:

- exact error and timestamp;
- framework/CANN/driver versions;
- `npu-smi` snapshot;
- relevant kernel/driver logs;
- last successful iteration and checkpoint.

Escalate service or host restart to the operator who owns that scope.

## Loss is healthy but quality collapses

Suspect the data contract before optimizer tuning:

- documents in one packed row can attend to each other;
- labels supervise prompt/source tokens;
- tokenizer differs between packing and inference;
- chat template differs between training and evaluation;
- source/target direction is wrong;
- pack-to-metadata audit assumed preserved order;
- the evaluation baseline came from different hardware/settings.

Loss can look excellent under every one of these failures.

## Direction/task seesaw

Count effective supervised target tokens and evaluate each task at every checkpoint. If one task improves while another regresses:

- verify sampler exposure rather than row counts;
- inspect source/style imbalance;
- measure per-task gradient cosine on a fixed diagnostic batch;
- prefer rebuilding the main-stage mixture over repeatedly annealing a converged small model.

Apply gradient-surgery methods only if the active distributed framework supports them reliably or a dedicated implementation has passed isolated correctness tests. Do not patch the optimizer core during a final production run.
