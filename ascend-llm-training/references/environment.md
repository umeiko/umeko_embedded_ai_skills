# Environment and launch boundary

## Preflight inventory

Before mutation, capture:

- hostname and time zone;
- NPU model, health, HBM, AICore utilization, and process view;
- free disk/inodes on data, checkpoint, and cache volumes;
- container/runtime state and mounted paths;
- active trainer, evaluator, inference-service, and preprocessing processes;
- framework, CANN, driver, `torch`, `torch_npu`, tokenizer, and model revisions.

Use all three views—host processes, container processes, and `npu-smi`. Container namespaces can make a valid NPU PID invisible or misleading from the host.

`scripts/ascend_preflight.sh` is read-only. Set `ASCEND_WORK_DIR` and optionally `ASCEND_CONTAINER`:

```bash
ASCEND_WORK_DIR=/workspace/experiment \
ASCEND_CONTAINER=training-container \
bash scripts/ascend_preflight.sh
```

An occupied device is a reason to identify the owner, not authorization to terminate it.

## Prefer the validated container

If packing/training was validated inside a container, run it there. A host Python may find the source tree while missing the matching CANN libraries, compiler flags, or `torch_npu` build.

With `set -u`, initialize variables before sourcing vendor environment scripts that append to them:

```bash
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
export PYTHONPATH="${PYTHONPATH:-}"
source "${ASCEND_ENV_SCRIPT:?set ASCEND_ENV_SCRIPT}"
```

Prefer a task-local Python overlay for one model's custom Transformers code instead of upgrading the shared training environment. Global dependency upgrades can silently break packing, checkpoint conversion, or existing models.

## Ports and distributed state

Every concurrent experiment needs a unique rendezvous port and HCCL base port. Record both in the run manifest. Before reusing a failed run's ports, confirm no trainer or child rank survives.

Keep DP/TP/PP explicit. A validated small-model baseline often uses TP=1 and PP=1 so each rank has a full model, but do not copy that topology to a model that does not fit per device.

## File-backed checkpoint transfer hang

Some CANN/driver/filesystem combinations can stall while pinning file-backed `mmap` pages from sharded safetensors. The process may show:

- all shards reported as loaded;
- low NPU memory and zero AICore use;
- a CPU process still alive;
- no first forward pass or health response.

First exclude ordinary causes: insufficient HBM, incompatible dtype/config, missing CANN libraries, and another job on the device. If the stall occurs specifically at `model.to("npu")`, materialize storage before transfer:

```python
with torch.no_grad():
    for parameter in model.parameters():
        parameter.data = parameter.data.clone()
    for buffer in model.buffers():
        buffer.data = buffer.data.clone()

model = model.to("npu:0")
```

This doubles host-side memory temporarily. Check RAM first, retain a numerical probe, and apply it as a documented compatibility workaround rather than hiding the failure.

## Background launch

Use an output log outside the container command and make the run independent of SSH. Immediately verify:

1. launcher still exists;
2. all expected ranks exist;
3. HBM increased on the intended devices;
4. iteration logs advance;
5. loss/grad values are finite.

Do not equate a returned PID, detached-container success, or allocated HBM with a healthy training loop.
