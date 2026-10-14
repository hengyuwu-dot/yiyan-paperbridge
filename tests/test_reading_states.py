import copy

from fastapi.testclient import TestClient

from paperbridge.review import has_issues, reading_segments
from paperbridge.translation_audit import english_residues


def segment(sid, **updates):
    return {"id": sid, "page": 1, "source": "We measure a 5 kpc radius.",
            "translation": "我们测得半径为5 kpc。", "status": "review", "exported": True,
            "notes": ["数值、引文和公式标记检查已通过；科学含义仍需人工核对"], **updates}


def test_legacy_review_is_not_a_problem_and_all_reading_apis_agree(monkeypatch):
    import paperbridge.app as api
    good = segment("good")
    failed = segment("failed", status="failed", translation="", notes=[], reason="公式标记缺失")
    edited = segment("edited", status="edited", source="The length is related to the size.",
                     translation="长度与尺寸成正比。", notes=[])
    job = {"id": "a" * 32, "status": "complete", "settings": {"domain": "general", "glossary": ""},
           "message": "全文段落排版已生成；请查看覆盖率与待核对内容", "segments": [good, failed, edited]}
    original = copy.deepcopy(job)
    monkeypatch.setattr(api, "jobs", {job["id"]: job})
    with TestClient(api.app) as client:
        base = f"/api/documents/{job['id']}"
        summary = client.get(base).json()
        rows = client.get(base + "/segments").json()
        issues = client.get(base + "/issues").json()
    assert summary["review_count"] == summary["issue_count"] == issues["count"] == 2
    assert rows[0]["status"] == "translated" and not rows[0]["notes"] and not rows[0]["has_issues"]
    assert rows[1]["status"] == "failed" and rows[1]["has_issues"]
    assert rows[2]["status"] == "edited" and rows[2]["has_issues"]
    assert "relation" in issues["issues"][1]["audit_codes"]
    assert "待核对" not in summary["message"]
    assert job == original  # Display normalization never rewrites user records.


def test_success_notes_do_not_retry_every_paragraph_but_fallback_and_layout_do():
    good = segment("good", notes=["续接原文联合理解，分别排回原位置；数值与公式标记检查通过，译意仍需核对",
                                   "长段落经逐句翻译通过完整性检查，请核对段内衔接"])
    assert not has_issues(good, [])
    assert has_issues(segment("bad", notes=[good["notes"][0] + "；联合复核未通过，采用已通过检查的初译"]), [])
    assert has_issues(segment("layout", notes=["PDF 中未确认完整译文，请核对版面"]), [])
    assert has_issues(segment("polish", notes=["复核未通过，使用已通过数值检查的初译"]), [])
    assert has_issues(segment("math"), [{"code": "markers", "message": "公式标记缺失"}])
    assert has_issues(segment("unknown", notes=["未知检查警告"]), [])


def test_legacy_negation_notes_are_rechecked_without_hiding_real_omissions():
    warning = "原文含否定或限制，请核对是否漏译"
    corrected = segment("corrected", source="It is not a detection.", translation="这并非一次探测。", notes=[warning])
    still_missing = segment("missing", source="It is not a detection.", translation="这是一次探测。", notes=[warning])
    assert not has_issues(corrected, [])
    assert has_issues(still_missing, [])


def test_named_literals_and_formula_subscripts_are_not_untranslated_prose():
    assert not english_residues("Zel’dovich & Novikov 1967", "见 Zel’dovich & Novikov 1967。")
    assert not english_residues("We use lenstronomy and pandas.", "我们采用 lenstronomy 和 pandas。")
    assert not english_residues("The radius is 5 kpc.", "半径为5 kpc。")
    assert not english_residues("The flux is {v1}model and {v2}sub.", "通量为{v1} model和{v2} sub。")
    assert not english_residues("Quadruply-imaged quasars (quads).", "四重成像类星体（quads）。")
    assert english_residues("We use a model.", "我们采用 model。") == ["model"]
    assert english_residues("The model is parameterized.", "该模型 parameterize。") == ["parameterize"]
    assert english_residues("We use data.", "我们采用 lenstronomy。") == ["lenstronomy"]
    assert english_residues("This allows us to measure the flux.", "这允许 us 测量 flux。") == ["us", "flux"]


def test_glossary_changes_recheck_edited_text_and_stale_audit_notes():
    row = segment("term", status="edited", source="The light curve is measured.", translation="测量了光变曲线。",
                  notes=["自动复核疑点：旧规则疑点"])
    job = {"settings": {"domain": "general", "glossary": "light curve = 光变曲线"}, "segments": [row]}
    assert not reading_segments(job)[0]["has_issues"]
    job["document_term_overrides"] = "light curve = 光度变化曲线"
    changed = reading_segments(job)[0]
    assert changed["status"] == "edited" and changed["has_issues"]
    assert any(i["code"] == "terminology" for i in changed["translation_audit"])
    assert all("旧规则" not in note for note in changed["notes"])


def test_missing_translation_is_flagged_only_after_completion_in_selected_pages():
    job = {"status": "running", "page_count": 3, "settings": {"pages": "1-2"},
           "segments": [segment("pending", status="pending", translation="", notes=[]),
                        segment("outside", page=3, status="pending", translation="", notes=[]),
                        segment("literal", status="preserved", translation="", notes=[])]}
    assert not any(s["has_issues"] for s in reading_segments(job))
    job["status"] = "complete"
    rows = reading_segments(job)
    assert rows[0]["has_issues"] and rows[0]["status"] == "failed"
    assert not rows[1]["has_issues"] and not rows[2]["has_issues"]
