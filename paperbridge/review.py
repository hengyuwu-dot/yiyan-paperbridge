"""Reading states reflect concrete warnings, never blanket human approval."""
from .glossary import contextual_glossary, terms_for
from .document_context import active_document_terms
from .translation_audit import audit_translation, negation_missing


INFORMATIONAL = (
    "数值、引文和公式标记检查已通过",
    "续接原文联合理解，分别排回原位置",
    "长段落经逐句翻译通过完整性检查",
    "专业名词经可见词表复译",
    "列表符号或脚注编号由程序保留",
    "固定名词或计数短语直接映射",
    "用户已修改；科学含义请继续对照原文",
)


def issue_notes(segment, audit=None):
    notes = []
    for note in segment.get("notes", []):
        if note == "原文含否定或限制，请核对是否漏译" and not negation_missing(segment.get("source", ""), segment.get("translation", "")):
            continue
        if note.startswith("自动复核疑点：") and audit is not None:
            continue  # Recompute against the current wording and glossary.
        if note.startswith(INFORMATIONAL):
            if "未通过" not in note:
                continue
            note = note[note.index("；联合复核未通过") + 1:] if "；联合复核未通过" in note else note
        if note.startswith(("请核对未译英文：", "可能有未译英文：")):
            from .translation_audit import english_residues
            residues = english_residues(segment.get("source", ""), segment.get("translation", ""))
            if not residues:
                continue
            note = "可能有未译英文：" + "、".join(residues)[:200]
        notes.append(note)
    if audit is not None:
        notes += ["自动检查提示：" + item["message"] for item in audit]
    return list(dict.fromkeys(notes))


def has_issues(segment, audit=None):
    return segment.get("status") == "failed" or bool(issue_notes(segment, audit))


def reading_segments(job, selected=None):
    settings = job.get("settings", {})
    glossary = active_document_terms(job, terms_for(settings.get("domain", "general"), settings.get("glossary", "")))
    scope = settings.get("pages", "").replace("，", ",").replace(" ", "")
    chosen = set()
    for part in scope.split(",") if scope else []:
        bounds = part.split("-")
        if all(b.isdigit() for b in bounds) and 1 <= len(bounds) <= 2:
            chosen.update(range(int(bounds[0]), min(int(bounds[-1]), job.get("page_count", 300)) + 1))
    result = []
    for segment in job["segments"] if selected is None else selected:
        effective = contextual_glossary(segment.get("source", ""), glossary, settings.get("domain"), segment.get("formula_hints"))
        audit = audit_translation(segment.get("source", ""), segment["translation"], effective) if segment.get("translation") and segment.get("status") != "preserved" else []
        missing = (job.get("status") == "complete" and segment.get("status") != "preserved"
                   and not segment.get("translation") and (not scope or segment.get("page") in chosen))
        if missing:
            audit = [{"code": "missing_translation", "message": "本次翻译范围内仍有未译出的段落，软件可重试翻译"}]
        notes = issue_notes(segment, audit)
        flagged = segment.get("status") == "failed" or bool(notes)
        status = segment.get("status", "pending")
        if missing:
            status = "failed"
        if status in {"translated", "review"} and segment.get("translation"):
            status = "review" if flagged else "translated"
        result.append({**segment, "status": status, "notes": notes, "has_issues": flagged, "translation_audit": audit})
    return result


def completion_message(count):
    return f"翻译与排版已完成，自动检查有 {count} 段提示，可一键复查" if count else "翻译与排版已完成，可以阅读中文译文"
