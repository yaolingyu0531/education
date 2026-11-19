"""建议生成与人工确认：规则引擎打底，本地模型可选。

红线（任一命中即拒绝生成或降级为人工）：
- 缺行为实例
- 命中敏感属性（家庭背景、性别、户籍等）
- 检索不到依据
- 置信度低于阈值
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

from . import core, kb

SENSITIVE = [
    "家庭背景", "家境", "父母", "家长职业", "性别", "户籍", "民族", "宗教",
    "身体健康", "病史", "心理疾病", "贫困", "低保",
]
BANNED_OUTPUT = ["该学生能力差", "智力", "性格缺陷", "不适合学习", "建议处分", "挂科", "不及格"]

ADVICE_PATH = lambda: os.path.join(core.path_of("runtime"), "advice.json")


def load_advice() -> Dict[str, Any]:
    path = ADVICE_PATH()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_advice(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(ADVICE_PATH()), exist_ok=True)
    tmp = ADVICE_PATH() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, ADVICE_PATH())


def _llm_generate(prompt: str) -> Dict[str, Any]:
    cfg = core.CONFIG.get("llm", {})
    if not cfg.get("enabled"):
        return {"used": False, "reason": "llm_disabled"}
    url = cfg["base_url"].rstrip("/") + "/api/generate"
    body = json.dumps({
        "model": cfg["model"], "prompt": prompt, "stream": False,
        "format": "json", "think": False, "options": {"temperature": 0.2, "num_predict": 512},
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", 120)) as resp:
            data = json.loads(resp.read())
        return {"used": True, "text": data.get("response", ""), "model": cfg["model"]}
    except Exception as exc:  # noqa: BLE001
        # 失败不静默降级：把原因带回，由调用方决定是否转人工
        return {"used": False, "reason": f"llm_error: {type(exc).__name__}", "detail": str(exc)[:200]}


LLM_PROMPT = """你是实习反馈整理助手。只整理事实与建议，不评价学生本人，不给学生定性或评分。

课程：{course}
岗位任务：{task}
观察记录：
{observations}

请输出 JSON，格式为：
{{"suggestions":[{{"action":"具体到动作的改进建议","evidence_index":1,"owner":"专业组/任课教师/企业导师"}}]}}

要求：
1. 最多 3 条；
2. 每条建议必须引用一条观察记录的编号（evidence_index），不得编造记录；
3. action 必须能落到具体动作上，不要写"加强沟通""提高能力"这类空话；
4. 只输出 JSON，不要输出其他文字。"""


def _llm_suggestions(course: str, task: str, observations: List[str]) -> Dict[str, Any]:
    """调用模型并校验：建议必须引用真实存在的观察记录，否则丢弃。"""
    obs_lines = "\n".join(f"O{i}: {o}" for i, o in enumerate(observations, 1))
    prompt = LLM_PROMPT.format(course=course or "（未提供）", task=task or "（未提供）",
                               observations=obs_lines)
    result = _llm_generate(prompt)
    if not result.get("used"):
        return {"ok": False, "reason": result.get("reason", "llm_unused"), "suggestions": []}

    try:
        raw = result["text"].strip()
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start >= 0 else {}
    except json.JSONDecodeError as exc:
        return {"ok": False, "reason": f"parse_error: {exc}", "suggestions": []}

    out, rejected = [], 0
    for item in (data.get("suggestions") or [])[:3]:
        action = str(item.get("action", "")).strip()
        try:
            idx = int(item.get("evidence_index", 0))
        except (TypeError, ValueError):
            idx = 0
        if not action or not (1 <= idx <= len(observations)):
            rejected += 1
            continue
        if any(bad in action for bad in BANNED_OUTPUT):
            rejected += 1
            continue
        out.append({
            "action": action,
            "evidence": observations[idx - 1],
            "evidence_index": idx,
            "owner": str(item.get("owner") or "专业组"),
        })
    return {"ok": bool(out), "model": result.get("model"), "suggestions": out,
            "rejected": rejected, "raw_len": len(result.get("text", ""))}


def draft(actor: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    student = str(payload.get("student", "")).strip()
    course = str(payload.get("course", "")).strip()
    task = str(payload.get("task", "")).strip()
    observations = [str(o).strip() for o in payload.get("observations", []) if str(o).strip()]

    blockers: List[str] = []
    if not student:
        blockers.append("缺少学生标识")
    if not observations:
        blockers.append("缺少行为实例：不能凭印象给建议（红线）")
    joined = " ".join(observations)
    hit_sensitive = [w for w in SENSITIVE if w in joined or w in task]
    if hit_sensitive:
        blockers.append("涉及敏感属性：" + "、".join(hit_sensitive) + "（不得用于能力推断）")

    query = " ".join(x for x in (course, task, joined, "岗位任务 行为实例 改进建议") if x)
    ctx = kb.retrieve_context(query, k=4)
    if not ctx["chunks"]:
        blockers.append("知识库无相关依据，停止自动建议")

    llm = {"used": False, "reason": "blocked_before_llm"} if blockers else {"used": False}

    confidence = 0.35
    confidence += 0.20 if observations else 0
    confidence += 0.10 if len(observations) >= 2 else 0
    confidence += 0.15 if task else 0
    confidence += 0.10 if len(ctx["chunks"]) >= 2 else 0
    confidence += 0.05 if course else 0
    confidence = round(min(confidence, 0.95), 2)

    threshold = core.CONFIG["thresholds"]["advice_confidence_min"]
    suggestions: List[Dict[str, Any]] = []

    if not blockers:
        model_try = _llm_suggestions(course, task, observations)
        if model_try.get("ok"):
            for s in model_try["suggestions"]:
                link = _match_link(ctx, task or course)
                suggestions.append({
                    "action": s["action"],
                    "evidence": s["evidence"],
                    "course_link": link.get("course"),
                    "fact_refs": ctx["facts"][:3],
                    "owner": s.get("owner") or link.get("owner", "专业组"),
                    "source_chunks": [c["id"] for c in ctx["chunks"][:2]],
                    "generated_by": model_try.get("model") or "llm",
                })
            llm = {"used": True, "model": model_try.get("model"),
                   "rejected": model_try.get("rejected", 0)}
            confidence = round(min(confidence + 0.05, 0.95), 2)
        else:
            # 模型不可用或输出不合规：回落规则引擎，并把原因记录在案（不静默）
            llm = {"used": False, "fallback": "rule",
                   "reason": model_try.get("reason", "no_valid_suggestion")}
            for idx, obs in enumerate(observations[:3], 1):
                link = _match_link(ctx, task or course)
                suggestions.append({
                    "action": f"围绕「{task or '岗位任务'}」安排针对性练习，并复核一次同类动作",
                    "evidence": obs,
                    "course_link": link.get("course"),
                    "fact_refs": ctx["facts"][:3],
                    "owner": link.get("owner", "专业组"),
                    "source_chunks": [c["id"] for c in ctx["chunks"][:2]],
                    "generated_by": "rule",
                })

    if blockers:
        status = "blocked"
    elif confidence < threshold:
        status = "needs_human"
    else:
        status = "pending_confirmation"

    record = {
        "id": "adv_" + uuid.uuid4().hex[:12],
        "created_at": core.now(),
        "created_by": actor,
        "student": student,
        "course": course,
        "task": task,
        "observations": [core.mask(o) for o in observations],
        "status": status,
        "confidence": confidence,
        "threshold": threshold,
        "blockers": blockers,
        "suggestions": suggestions,
        "citations": {
            "facts": ctx["facts"][:6],
            "chunks": [{"id": c["id"], "path": c["path"], "heading": c.get("heading")} for c in ctx["chunks"]],
            "related": ctx["related"],
        },
        "llm": {k: v for k, v in llm.items() if k != "text"},
        "review": None,
    }
    store = load_advice()
    store[record["id"]] = record
    save_advice(store)
    core.append_event("advice.drafted", {"id": record["id"], "status": status, "confidence": confidence}, actor)
    core.audit("advice.draft", actor, "", {"id": record["id"], "status": status,
                                           "blockers": blockers, "facts": ctx["facts"][:6]})
    return record


def _match_link(ctx: Dict[str, Any], needle: str) -> Dict[str, str]:
    for n in ctx.get("related", []):
        if n.get("type") in ("requirement", "opportunity"):
            return {"course": n.get("label", "")[:60], "owner": "专业组"}
    return {}


def confirm(actor: str, role: str, advice_id: str, decision: str, note: str = "") -> Dict[str, Any]:
    store = load_advice()
    record = store.get(advice_id)
    if not record:
        raise KeyError(advice_id)
    if record["created_by"] == actor and role != "admin":
        raise PermissionError("本人签核：起草人不能确认自己的建议")
    if record["status"] not in ("pending_confirmation", "needs_human"):
        raise ValueError(f"当前状态不可确认：{record['status']}")
    if decision not in ("approve", "reject"):
        raise ValueError("decision 必须是 approve 或 reject")

    record["status"] = "approved" if decision == "approve" else "rejected"
    record["review"] = {"by": actor, "role": role, "at": core.now(),
                        "decision": decision, "note": core.mask(note)}
    store[advice_id] = record
    save_advice(store)
    core.append_event("advice.confirmed", {"id": advice_id, "decision": decision}, actor)
    core.audit("advice.confirm", actor, role, {"id": advice_id, "decision": decision, "note": note})
    return record


def export_rows() -> List[Dict[str, Any]]:
    rows = []
    for r in sorted(load_advice().values(), key=lambda x: x["created_at"], reverse=True):
        rows.append({
            "id": r["id"], "student": r["student"], "course": r["course"], "task": r["task"],
            "status": r["status"], "confidence": r["confidence"],
            "blockers": "；".join(r["blockers"]),
            "reviewer": (r.get("review") or {}).get("by", ""),
        })
    return rows
