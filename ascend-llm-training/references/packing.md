# Packed instruction data

## Production rule

Use the framework's official tokenizer and packing implementation for production. A custom packer can produce plausible loss while allowing unrelated documents to attend to each other or misaligning labels with the tokenizer.

For a MindSpeed-LLM style instruction workflow, the important contract is conceptually:

```bash
python preprocess_data.py \
  --input "$TRAIN_JSONL" \
  --tokenizer-name-or-path "$TOKENIZER_DIR" \
  --output-prefix "$PACK_PREFIX" \
  --handler-name AlpacaStyleInstructionHandler \
  --tokenizer-type PretrainedFromHF \
  --prompt-type "$PROMPT_TYPE" \
  --seq-length "$SEQ_LENGTH" \
  --pack --neat-pack
```

Match the exact flags to the installed framework revision. Record the command, code revision, input hash, tokenizer hashes, output hashes, and any template source revision.

## Structural gates

Audit the full pack, not only a few decoded rows:

1. Nonzero document/attention segment IDs in each packed row are exactly consecutive `1..K`.
2. Summing `max(segment_id)` across rows equals the number of input training samples.
3. Prompt, instruction, and source tokens have ignored labels; only the intended assistant target and required terminator are supervised.
4. Each segment has one contiguous supervision interval adjacent to the assistant boundary.
5. Padding carries no supervision.
6. Empty targets, NULs, disallowed control characters, and forbidden supervised token IDs are zero.
7. The target terminator matches the tokenizer/template contract.
8. Random decoded rows cover both directions/tasks and major sources.

Run content/language/refusal heuristics as report-and-review gates, not as blind deletion rules. A translated sentence can legitimately contain words that resemble refusal phrases.

## Order-independent mapping

Neat packing commonly sorts, buckets, or greedily reorders samples. Never join packed segment number `n` to JSONL row `n` unless the packer explicitly guarantees that order.

Use one of these approaches:

- emit a sidecar carrying stable sample IDs through the packer;
- replay the exact packing index;
- decode each supervised target and compare a fingerprint/multiset against expected targets;
- include direction/source markers whose identity is verified from decoded content.

Require exact expected/actual multiset equality: missing=0, extra=0. A positional audit can be completely wrong while all token-level structure still looks healthy.

## Dataset balance

Count supervised target tokens after the final template/tokenizer transformation. Row balance is insufficient when one direction has systematically longer targets.

Report separately:

- unique corpus rows and target tokens by direction/task/source;
- static dataset share;
- sampler weight or repeated exposure;
- expected effective supervised-token share during training.

If the instruction dataset loader supports only one packed prefix, do not assume that standard Megatron blend syntax will work. Validate multi-dataset support in the active loader, or build a deterministic mixed pack whose effective exposure can be audited.

## Smoke pack

Create a dedicated small pack rather than truncating a production `.bin` file. Include all task directions, long and short examples, special symbols, and at least one multi-document packed row. Keep its output separate from the full run.
