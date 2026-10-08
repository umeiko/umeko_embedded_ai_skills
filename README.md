# Umeko Embedded AI Skills

[中文说明](README_CN.md)

Reusable Codex skills for embedded AI, model engineering, and media production. Each top-level skill directory is self-contained and can be installed independently.

## Skills

| Skill | Purpose |
|---|---|
| [`ascend-llm-training`](ascend-llm-training/) | Prepare, pack, launch, monitor, evaluate, and debug LLM training on Huawei Ascend NPUs with CANN, `torch_npu`, MindSpeed-LLM, or Megatron-LM. Includes field-tested guidance for document-isolated packing, HCCL jobs, `safetensors` transfer hangs, same-hardware evaluation, and activation-quantization diagnostics. |
| [`narrated-demo-video`](narrated-demo-video/) | Build reproducible narrated demo videos from real UI recording, segmented TTS, subtitles, music, effects, and FFmpeg timelines. |

## Install

Clone the repository and copy or symlink the skill you need into your Codex skills directory:

```bash
git clone https://github.com/umeiko/umeko_embedded_ai_skills.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R umeko_embedded_ai_skills/ascend-llm-training "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Restart or reload Codex if the new skill is not discovered immediately. You can then invoke it explicitly:

```text
Use $ascend-llm-training to audit and launch this MindSpeed-LLM SFT run.
```

## Repository conventions

- `SKILL.md`: required entry point and workflow.
- `agents/openai.yaml`: optional UI metadata.
- `references/`: details loaded only when relevant.
- `scripts/`: reusable helpers that can be run without copying large code blocks.

Public content intentionally excludes private hosts, credentials, internal paths, proprietary model or dataset names, and unpublished metrics.
