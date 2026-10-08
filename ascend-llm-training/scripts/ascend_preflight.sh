#!/usr/bin/env bash
# Read-only Ascend training preflight. It never stops processes or changes state.
set -Eeuo pipefail

WORK_DIR=${ASCEND_WORK_DIR:-$PWD}
CONTAINER=${ASCEND_CONTAINER:-}
MIN_FREE_GB=${ASCEND_MIN_FREE_GB:-100}
PROCESS_PATTERN=${ASCEND_PROCESS_PATTERN:-'torchrun|pretrain_gpt|posttrain_gpt|vllm|preprocess_data|convert_ckpt'}

section() { printf '\n[%s]\n' "$1"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

section identity
printf 'host=%s\n' "$(hostname)"
printf 'time=%s\n' "$(date -Is)"
printf 'work_dir=%s\n' "$WORK_DIR"

if [[ ! -d "$WORK_DIR" ]]; then
  printf 'ERROR: work directory does not exist: %s\n' "$WORK_DIR" >&2
  exit 2
fi

section storage
df -h "$WORK_DIR"
df -Pk "$WORK_DIR" | awk -v min_gb="$MIN_FREE_GB" '
  NR==2 {
    free_gb=$4/1024/1024
    printf "free_gb=%.1f required_gb=%s\n", free_gb, min_gb
    if (free_gb < min_gb) exit 3
  }' || {
    warn "free space is below ASCEND_MIN_FREE_GB=$MIN_FREE_GB"
    exit 3
  }

section memory
if command -v free >/dev/null 2>&1; then
  free -h
else
  warn "free command not found"
fi

section npu
if command -v npu-smi >/dev/null 2>&1; then
  npu-smi info
else
  warn "npu-smi not found; this may be a controller-only host"
fi

section matching_processes
if ps -eo pid,user,etime,cmd >/dev/null 2>&1; then
  matches=$(ps -eo pid,user,etime,cmd | grep -E "$PROCESS_PATTERN" | grep -v -E 'grep -E|ascend_preflight' || true)
  if [[ -n "$matches" ]]; then
    printf '%s\n' "$matches"
    warn "matching jobs exist; identify their owner before using devices or ports"
  else
    printf 'none\n'
  fi
else
  warn "process inventory is unavailable with this ps implementation"
fi

section container
if [[ -n "$CONTAINER" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    printf 'ERROR: ASCEND_CONTAINER is set but docker is unavailable\n' >&2
    exit 4
  fi
  docker inspect -f 'name={{.Name}} status={{.State.Status}} started={{.State.StartedAt}}' "$CONTAINER"
  docker exec "$CONTAINER" sh -lc 'printf "container_host=%s\n" "$(hostname)"; ps -eo pid,user,etime,cmd | head -20'
else
  printf 'ASCEND_CONTAINER is not set; container check skipped\n'
fi

section versions
if command -v python >/dev/null 2>&1; then python --version; fi
if command -v git >/dev/null 2>&1; then git --version; fi
printf 'PREFLIGHT_COMPLETE\n'
