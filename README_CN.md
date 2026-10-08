# Umeko 嵌入式 AI Skills

[English](README.md)

这里收录可复用的 Codex skills，覆盖嵌入式 AI、模型工程和媒体制作。每个一级目录都是可独立安装、独立使用的 skill。

## Skills

| Skill | 用途 |
|---|---|
| [`ascend-llm-training`](ascend-llm-training/) | 在华为昇腾 NPU 上准备数据、打包、启动、监控、评测和排查 LLM 训练。适用于 CANN、`torch_npu`、MindSpeed-LLM 与 Megatron-LM，包含文档隔离打包、HCCL 多卡任务、`safetensors` 传输卡死、同机评测和激活量化诊断等实战经验。 |
| [`narrated-demo-video`](narrated-demo-video/) | 用真实界面录制、分段 TTS、字幕、音乐、特效和 FFmpeg 时间线制作可复现的讲解视频。 |

## 安装

克隆仓库，把需要的 skill 复制或软链接到 Codex skills 目录：

```bash
git clone https://github.com/umeiko/umeko_embedded_ai_skills.git
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R umeko_embedded_ai_skills/ascend-llm-training "${CODEX_HOME:-$HOME/.codex}/skills/"
```

如果 Codex 没有立即发现新 skill，请重启或重新加载。之后可以显式调用：

```text
请使用 $ascend-llm-training 审计并启动这个 MindSpeed-LLM SFT 任务。
```

## 仓库约定

- `SKILL.md`：必需的入口与工作流。
- `agents/openai.yaml`：可选的界面元数据。
- `references/`：仅在相关场景下加载的详细说明。
- `scripts/`：可复用的小工具，避免反复手写大段命令。

公开内容会主动排除私有主机、凭据、内部路径、私有模型或数据集名称以及未发布指标。
