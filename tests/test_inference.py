from paperbridge.inference import PromptReuse, reusable_prefix, MAX_PREFIX_TOKENS


def test_prefix_reuse_requires_identical_tokens_and_complete_blocks():
    old = [5] * 1024 + [6] * 512
    assert reusable_prefix([5] * 900 + [7], old) == 512
    assert reusable_prefix([5] * 1024 + [7], old) == 1024
    assert reusable_prefix([8] + old, old) == 0
    # A complete identical prompt still needs one final token for logits.
    assert reusable_prefix([5] * 1024, old) == 512
    assert reusable_prefix([5] * 511, old) == 0


def test_cache_release_keeps_only_performance_counts():
    reuse = PromptReuse()
    reuse.cache = [object()]
    reuse.tokens = [5] * MAX_PREFIX_TOKENS
    reuse.stats["generation_calls"] = 3
    reuse.clear()
    assert reuse.cache is None and reuse.tokens == []
    assert reuse.stats["generation_calls"] == 3


def test_unloaded_translator_does_not_import_gpu_runtime():
    from paperbridge.translator import LocalTranslator
    local = LocalTranslator()
    local.inference.tokens = [10] * 512
    local.unload()
    assert local.model is None and local.tokenizer is None
    assert local.inference.tokens == []


def test_layout_disables_native_statistics_before_resource_setup(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import paperbridge.layout_runtime as runtime
    events = []
    native = SimpleNamespace(disable_telemetry_events=lambda:events.append("disabled"))
    const = SimpleNamespace(CACHE_FOLDER=None,TIKTOKEN_CACHE_FOLDER=None)
    monkeypatch.setitem(sys.modules,"onnxruntime",native)
    monkeypatch.setitem(sys.modules,"babeldoc.const",const)
    monkeypatch.setattr(runtime,"CACHE",tmp_path)
    runtime.initialize()
    assert events == ["disabled"]
    assert const.CACHE_FOLDER == tmp_path
    assert const.TIKTOKEN_CACHE_FOLDER.is_dir()
