"""FastAPI 应用：接口层。"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import advice as advice_mod
from . import core, kb

app = FastAPI(title="学习支持与辅导协作 MVP", version=core.CONFIG["service"]["version"])


# ------------------------------------------------------------------ 鉴权
def current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    sess = core.resolve_token(token)
    if not sess:
        raise HTTPException(status_code=401, detail={"error": "unauthorized", "message": "缺少或无效的令牌"})
    return {"user": sess["user"], "role": sess["role"], "token": token}


def require(action: str):
    def dep(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
        if not core.can(user["role"], action):
            core.audit("rbac.denied", user["user"], user["role"], {"action": action})
            raise HTTPException(status_code=403,
                                detail={"error": "forbidden", "message": f"角色 {user['role']} 无权限：{action}"})
        return user
    return dep


class LoginIn(BaseModel):
    username: str
    password: str


class AdviceIn(BaseModel):
    student: str
    course: str = ""
    task: str = ""
    observations: List[str] = Field(default_factory=list)


class ConfirmIn(BaseModel):
    decision: str
    note: str = ""


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str
    name: str = ""


@app.post("/auth/login")
def login(body: LoginIn) -> Dict[str, Any]:
    users = core.load_users()
    meta = users.get(body.username)
    if not meta or not core.verify_password(body.password, meta["credential"]):
        core.audit("auth.failed", body.username, "", {"reason": "bad_credential"})
        raise HTTPException(status_code=401, detail={"error": "bad_credential", "message": "用户名或口令错误"})
    token = core.issue_token(body.username, meta["role"])
    core.audit("auth.login", body.username, meta["role"], {"name": meta["name"]})
    return {"token": token, "username": body.username, "role": meta["role"], "name": meta["name"],
            "permissions": core.permissions_of(meta["role"])}


@app.get("/me")
def me(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    meta = core.load_users().get(user["user"], {})
    return {"username": user["user"], "role": user["role"], "name": meta.get("name", ""),
            "permissions": core.permissions_of(user["role"])}


@app.get("/health")
def health() -> Dict[str, Any]:
    try:
        idx = kb.load_index()
        graph = kb.load_graph()
        return {"ok": True, "chunks": len(idx["chunks"]), "graph": graph.stats(),
                "version": core.CONFIG["service"]["version"]}
    except FileNotFoundError:
        return {"ok": False, "reason": "索引未构建，请先运行 scripts/build_index.py"}


@app.get("/kb/search")
def kb_search(q: str = Query(..., min_length=1), k: int = 6,
              user: Dict[str, Any] = Depends(require("kb:search"))) -> Dict[str, Any]:
    hits = kb.search(q, max(1, min(k, 20)))
    core.audit("kb.search", user["user"], user["role"], {"q": q, "hits": len(hits)})
    return {"query": q, "hits": hits}


@app.get("/kb/context")
def kb_context(q: str, user: Dict[str, Any] = Depends(require("kb:search"))) -> Dict[str, Any]:
    return kb.retrieve_context(q)


@app.get("/graph/stats")
def graph_stats(user: Dict[str, Any] = Depends(require("graph:read"))) -> Dict[str, Any]:
    return kb.load_graph().stats()


@app.get("/graph/node/{nid}")
def graph_node(nid: str, user: Dict[str, Any] = Depends(require("graph:read"))) -> Dict[str, Any]:
    node = kb.load_graph().node(nid)
    if not node:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return node


@app.get("/graph/neighbors/{nid}")
def graph_neighbors(nid: str, depth: int = 1,
                    user: Dict[str, Any] = Depends(require("graph:read"))) -> Dict[str, Any]:
    return kb.load_graph().neighbors(nid, depth)


@app.get("/wiki")
def wiki(user: Dict[str, Any] = Depends(require("graph:read"))) -> Dict[str, Any]:
    pages = kb.load_graph().wiki()
    return {"count": len(pages), "pages": pages}


@app.post("/advice")
def create_advice(body: AdviceIn, user: Dict[str, Any] = Depends(require("advice:draft"))) -> Dict[str, Any]:
    return advice_mod.draft(user["user"], body.model_dump())


@app.get("/advice")
def list_advice(user: Dict[str, Any] = Depends(require("advice:read"))) -> Dict[str, Any]:
    store = advice_mod.load_advice()
    rows = sorted(store.values(), key=lambda x: x["created_at"], reverse=True)
    return {"count": len(rows), "items": rows}


@app.get("/advice/{aid}")
def get_advice(aid: str, user: Dict[str, Any] = Depends(require("advice:read"))) -> Dict[str, Any]:
    rec = advice_mod.load_advice().get(aid)
    if not rec:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return rec


@app.post("/advice/{aid}/confirm")
def confirm_advice(aid: str, body: ConfirmIn,
                   user: Dict[str, Any] = Depends(require("advice:confirm"))) -> Dict[str, Any]:
    try:
        return advice_mod.confirm(user["user"], user["role"], aid, body.decision, body.note)
    except KeyError:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    except PermissionError as exc:
        core.audit("advice.confirm_denied", user["user"], user["role"], {"id": aid, "reason": str(exc)})
        raise HTTPException(status_code=403, detail={"error": "self_sign_denied", "message": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": "invalid_state", "message": str(exc)})


@app.get("/audit")
def read_audit(limit: int = 100,
               user: Dict[str, Any] = Depends(require("audit:read"))) -> Dict[str, Any]:
    return {"records": core.read_audit(limit)}


@app.get("/audit/verify")
def audit_verify(user: Dict[str, Any] = Depends(require("audit:read"))) -> Dict[str, Any]:
    return core.verify_audit()


@app.get("/events")
def events(limit: int = 50, user: Dict[str, Any] = Depends(require("audit:read"))) -> Dict[str, Any]:
    return {"events": core.read_events(limit)}


@app.get("/llm/status")
def llm_status(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    cfg = core.CONFIG.get("llm", {})
    info: Dict[str, Any] = {"enabled": cfg.get("enabled"), "model": cfg.get("model"),
                            "base_url": cfg.get("base_url"), "reachable": False, "models": []}
    try:
        with urllib.request.urlopen(cfg["base_url"].rstrip("/") + "/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        names = [m.get("name", "") for m in data.get("models", [])]
        info["reachable"] = True
        info["models"] = names
        info["model_present"] = any((cfg.get("model") or "").split(":")[0] in n for n in names)
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return info


@app.get("/stats")
def stats(user: Dict[str, Any] = Depends(current_user)) -> Dict[str, Any]:
    store = advice_mod.load_advice()
    by_status: Dict[str, int] = {}
    for rec in store.values():
        by_status[rec["status"]] = by_status.get(rec["status"], 0) + 1
    return {"advice_total": len(store), "by_status": by_status,
            "graph": kb.load_graph().stats(), "chunks": len(kb.load_index()["chunks"]),
            "audit": core.verify_audit()}


@app.get("/admin/users")
def list_users(user: Dict[str, Any] = Depends(require("admin:users"))) -> Dict[str, Any]:
    users = core.load_users()
    return {"users": [{"username": k, "role": v["role"], "name": v.get("name", ""),
                       "created_at": v.get("created_at", "")} for k, v in users.items()]}


@app.post("/admin/users")
def create_user(body: CreateUserIn, user: Dict[str, Any] = Depends(require("admin:users"))) -> Dict[str, Any]:
    users = core.load_users()
    if body.username in users:
        raise HTTPException(status_code=409, detail={"error": "exists"})
    if body.role not in core.CONFIG["rbac"]["allow"]:
        raise HTTPException(status_code=422, detail={"error": "unknown_role"})
    users[body.username] = {"role": body.role, "name": body.name or body.username,
                            "credential": core.hash_password(body.password), "created_at": core.now()}
    core.save_users(users)
    core.audit("admin.user_created", user["user"], user["role"], {"username": body.username, "role": body.role})
    return {"ok": True, "username": body.username, "role": body.role}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(core.BASE, "web", "index.html"))


@app.exception_handler(Exception)
def unhandled(_request, exc: Exception) -> JSONResponse:  # noqa: ANN001
    return JSONResponse(status_code=500, content={"error": "internal", "message": str(exc)[:300]})


@app.on_event("startup")
def _startup() -> None:
    core.ensure_dirs()
