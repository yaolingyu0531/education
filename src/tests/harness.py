"""Harness：逐用例隔离的端到端冒烟测试（确定性断言，不依赖模型）。

用法：
    .venv\\Scripts\\python.exe tests\\harness.py [--base http://127.0.0.1:8010]

退出码 0 表示全部通过。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8010"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(ROOT, "data", "runtime", "audit.jsonl")

if "--base" in sys.argv:
    BASE = sys.argv[sys.argv.index("--base") + 1]

PASS, FAIL = [], []


def request(method, path, token=None, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


def login(user, pwd):
    status, data = request("POST", "/auth/login", body={"username": user, "password": pwd})
    assert status == 200, f"login {user} -> {status} {data}"
    return data["token"], data["role"]


def main():
    print(f"目标服务：{BASE}\n")

    print("[1] 健康检查与知识库就绪")
    status, health = request("GET", "/health")
    check("health 200", status == 200, str(health))
    check("索引已构建", bool(health and health.get("ok")), str(health))
    check("切片数 > 100", (health or {}).get("chunks", 0) > 100, str((health or {}).get("chunks")))

    print("[2] 登录与角色")
    t_teacher, r_teacher = login("teacher", "teacher123")
    t_reviewer, r_reviewer = login("reviewer", "review123")
    t_student, r_student = login("student", "student123")
    t_admin, r_admin = login("admin", "admin123")
    check("教师角色", r_teacher == "teacher")
    check("质量负责人角色", r_reviewer == "reviewer")
    check("令牌互不相同", len({t_teacher, t_reviewer, t_student, t_admin}) == 4)

    print("[3] 检索：换岗错发相关依据")
    status, hits = request("GET", "/kb/search?q=" + urllib.parse.quote("换岗 反馈 发错 旧导师"), t_teacher)
    check("检索 200", status == 200)
    check("返回命中", bool(hits and hits.get("hits")), str(hits)[:120])
    if hits and hits.get("hits"):
        first = hits["hits"][0]
        check("命中带原文出处", bool(first.get("path")), str(first)[:120])
        print(f"        首条命中：{first['path']} · {first['heading'][:30]}")

    print("[4] 生成建议：有行为实例")
    status, advice = request("POST", "/advice", t_teacher, {
        "student": "S-042", "course": "机电一体化·设备维护", "task": "设备点检与交接",
        "observations": ["6 月 3 日点检表漏填润滑项", "交接班记录未签名，次日重复停机"],
    })
    check("生成 200", status == 200, str(advice)[:160])
    check("状态为待确认", advice and advice.get("status") == "pending_confirmation", str(advice and advice.get("status")))
    check("产出建议条目", bool(advice and advice.get("suggestions")), str(advice and len(advice.get("suggestions", []))))
    check("带证据引用", bool(advice and advice.get("citations", {}).get("facts")), str(advice and advice.get("citations")))
    check("置信度达阈值", (advice or {}).get("confidence", 0) >= 0.55, str((advice or {}).get("confidence")))
    advice_id = (advice or {}).get("id")

    print("[5] 红线：缺行为实例")
    status, blocked = request("POST", "/advice", t_teacher, {
        "student": "S-043", "course": "机电一体化", "task": "沟通能力", "observations": [],
    })
    check("被拦截", blocked and blocked.get("status") == "blocked", str(blocked)[:160])
    check("拦截原因含红线", any("行为实例" in b for b in (blocked or {}).get("blockers", [])), str(blocked))

    print("[6] 红线：敏感属性")
    status, sens = request("POST", "/advice", t_teacher, {
        "student": "S-044", "course": "机电一体化", "task": "团队协作",
        "observations": ["家庭背景较差导致沟通不畅"],
    })
    check("敏感属性被拦截", sens and sens.get("status") == "blocked", str(sens)[:160])

    print("[7] 权限：本人签核被拒")
    status, resp = request("POST", f"/advice/{advice_id}/confirm", t_teacher, {"decision": "approve"})
    check("教师确认自己被拒（403）", status == 403, f"{status} {resp}")

    print("[8] 权限：学生越权起草被拒")
    status, resp = request("POST", "/advice", t_student, {"student": "S-001", "observations": ["x"]})
    check("学生起草被拒（403）", status == 403, f"{status} {resp}")

    print("[9] 权限：审计日志仅审核方可读")
    status, resp = request("GET", "/audit", t_teacher)
    check("教师读审计被拒（403）", status == 403, f"{status}")
    status, audit = request("GET", "/audit", t_reviewer)
    check("审核方可读审计（200）", status == 200 and audit.get("records"), str(status))

    print("[10] 人工确认")
    status, confirmed = request("POST", f"/advice/{advice_id}/confirm", t_reviewer,
                                {"decision": "approve", "note": "依据充分"})
    check("审核方确认成功", status == 200 and confirmed.get("status") == "approved", f"{status} {str(confirmed)[:120]}")
    check("记录确认人", (confirmed or {}).get("review", {}).get("by") == "reviewer")

    print("[11] 审计链完整性")
    status, verify = request("GET", "/audit/verify", t_reviewer)
    check("链校验通过", bool(verify and verify.get("ok")), str(verify))
    records = (verify or {}).get("records", 0)
    check("审计记录 ≥ 8 条", records >= 8, str(records))

    print("[12] 篡改检测（临时副本，测完还原）")
    backup = AUDIT + ".bak"
    shutil.copy2(AUDIT, backup)
    try:
        with open(AUDIT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": "1970-01-01T00:00:00+00:00", "action": "tamper",
                                 "actor": "intruder", "role": "admin", "detail": {},
                                 "prev": "x", "hash": "y"}, ensure_ascii=False) + "\n")
        status, broken = request("GET", "/audit/verify", t_reviewer)
        check("篡改被检出", broken is not None and broken.get("ok") is False, str(broken))
    finally:
        shutil.move(backup, AUDIT)

    print("[13] 管理员：用户与权限")
    status, users = request("GET", "/admin/users", t_admin)
    check("管理员可列用户", status == 200 and len(users.get("users", [])) >= 5, str(status))
    status, resp = request("GET", "/admin/users", t_reviewer)
    check("非管理员被拒（403）", status == 403, str(status))

    print("[14] 图谱与 Wiki")
    status, stats = request("GET", "/graph/stats", t_teacher)
    check("图谱统计可用", status == 200 and stats.get("nodes", 0) > 20, str(stats))
    status, wiki = request("GET", "/wiki", t_teacher)
    check("Wiki 页面可列", status == 200 and wiki.get("count", 0) > 10, str(status))

    total = len(PASS) + len(FAIL)
    print(f"\n{'='*52}\n通过 {len(PASS)}/{total}")
    if FAIL:
        print("失败用例：")
        for f in FAIL:
            print("  -", f)
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (供 quote 使用)
    sys.exit(main())
