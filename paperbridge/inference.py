"""Bounded unquantized KV reuse; model weights and prompts are unchanged."""
from itertools import takewhile
import time

PREFILL_BLOCK = 512
MAX_PREFIX_TOKENS = 4096
ALLOCATOR_CACHE_BYTES = 512 * 1024 * 1024


def reusable_prefix(current, previous, block=PREFILL_BLOCK):
    # Keep a final input token for MLX to compute the next-token logits.
    common = sum(1 for _ in takewhile(lambda pair: pair[0] == pair[1], zip(current[:-1], previous)))
    # Reuse only complete prefill blocks, preserving their computation shape.
    return common // block * block


class PromptReuse:
    """One bounded prompt, with no generated answer or earlier-paper suffix."""
    def __init__(self):
        self.cache = None
        self.tokens = []
        self.stream = None
        self.stats = {"generation_calls": 0, "prompt_tokens": 0, "reused_prompt_tokens": 0,
                      "generation_seconds": 0.0, "peak_mlx_bytes": 0,
                      "prefill_block": PREFILL_BLOCK, "kv_quantization": False}

    def clear(self):
        self.cache = None
        self.tokens = []

    def generate(self, model, tokenizer, prompt, max_tokens):
        import mlx.core as mx
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler
        from mlx_lm.models.cache import KVCache, make_prompt_cache, trim_prompt_cache

        add_special = tokenizer.bos_token is None or not prompt.startswith(tokenizer.bos_token)
        ids = tokenizer.encode(prompt, add_special_tokens=add_special)
        if self.stream is None:
            # One explicit stream can be used serially across BabelDOC's worker
            # threads and synchronized by its main thread during resource release.
            self.stream = mx.new_thread_unsafe_stream(mx.default_device())
        reuse = reusable_prefix(ids, self.tokens) if self.cache else 0
        if not reuse:
            self.cache = make_prompt_cache(model)
        else:
            trim_prompt_cache(self.cache, self.cache[0].offset - reuse)
        # Only ordinary, non-quantized Qwen KV caches support this retention
        # policy. Other architectures safely generate from the complete prompt.
        supported = bool(self.cache) and all(isinstance(c, KVCache) for c in self.cache)
        if not supported:
            self.clear()
            reuse = 0
        started = time.perf_counter()
        try:
            result = generate(model, tokenizer, prompt=ids[reuse:], max_tokens=max_tokens,
                              sampler=make_sampler(temp=0.0), verbose=False,
                              prefill_step_size=PREFILL_BLOCK, prompt_cache=self.cache,
                              stream=self.stream)
            self.stats["generation_calls"] += 1
            self.stats["prompt_tokens"] += len(ids)
            self.stats["reused_prompt_tokens"] += reuse
            self.stats["generation_seconds"] += time.perf_counter() - started
            self.stats["peak_mlx_bytes"] = max(self.stats["peak_mlx_bytes"], mx.get_peak_memory())
            if supported:
                keep = min(len(ids) - 1, MAX_PREFIX_TOKENS) // PREFILL_BLOCK * PREFILL_BLOCK
                if keep:
                    trim_prompt_cache(self.cache, self.cache[0].offset - keep)
                    with mx.stream(self.stream):
                        for c in self.cache:
                            # trim() changes offsets only. Materialize short arrays
                            # so long responses do not retain their backing buffers.
                            c.keys = mx.contiguous(c.keys[..., :keep, :])
                            c.values = mx.contiguous(c.values[..., :keep, :])
                        mx.eval([c.state for c in self.cache])
                    self.tokens = ids[:keep]
                else:
                    self.clear()
            return result
        except Exception:
            # A partially evaluated cache must never reach the next request.
            self.clear()
            raise
