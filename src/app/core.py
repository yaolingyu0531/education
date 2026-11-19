"""核心：配置、口令、令牌、权限、事件存储、审计链。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_config() -> Dict[str, Any]:
    path = os.path.join(BASE, "config.json")
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


CONFIG = load_config()


def path_of(key: str) -> str:
    raw = CONFIG["paths"][key]
    return raw if os.path.isabs(raw) else os.path.join(BASE, raw)


def ensure_dirs() -> None:
    for key in ("docs", "runtime"):
        os.makedirs(path_of(key), exist_ok=True)


# --------------------------------------------------------------------- 口令
def hash_password(password: str, salt: str | None = None) -> Dict[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return {"salt": salt, "hash": digest.hex(), "algo": "pbkdf2-sha256-120k"}


def verify_password(password: str, record: Dict[str, str]) -> bool:
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(record["salt"]), 120_000)
    return hmac.compare_digest(calc.hex(), record["hash"])


# --------------------------------------------------------------------- 用户
def users_path() -> str:
    return os.path.join(path_of("runtime"), "users.json")


def load_users() -> Dict[str, Dict[str, Any]]:
    path = users_path()
    if not os.path.exists(path):
        seed = {
            "admin": {"role": "admin", "name": "系统管理员", "password": "admin123"},
            "coordinator": {"role": "coordinator", "name": "产教融合负责人（顾明岚）", "password": "coord123"},
            "teacher": {"role": "teacher", "name": "实习指导教师（林亦舟）", "password": "teacher123"},
            "reviewer": {"role": "reviewer", "name": "教学质量负责人（傅景）", "password": "review123"},
            "student": {"role": "student", "name": "学生（演示）", "password": "student123"},
        }
        data = {}
        for user, meta in seed.items():
            data[user] = {
                "role": meta["role"],
                "name": meta["name"],
                "credential": hash_password(meta["password"]),
                "created_at": now(),
            }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_users(users: Dict[str, Dict[str, Any]]) -> None:
    with open(users_path(), "w", encoding="utf-8") as fh:
        json.dump(users, fh, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------- 令牌
SESSIONS: Dict[str, Dict[str, Any]] = {}


def issue_token(username: str, role: str, ttl: int = 8 * 3600) -> str:
    token = secrets.token_urlsafe(24)
    SESSIONS[token] = {"user": username, "role": role, "exp": time.time() + ttl}
    return token


def resolve_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    sess = SESSIONS.get(token)
    if not sess:
        return None
    if sess["exp"] < time.time():
        SESSIONS.pop(token, None)
        return None
    return sess


# --------------------------------------------------------------------- 权限
def can(role: str, action: str) -> bool:
    """默认拒绝；命中 deny 立即拒绝；再查 allow。"""
    matrix = CONFIG["rbac"]
    if action in matrix.get("deny", {}).get(role, []):
        return False
    return action in matrix.get("allow", {}).get(role, [])


def permissions_of(role: str) -> List[str]:
    return sorted(CONFIG["rbac"].get("allow", {}).get(role, []))


# --------------------------------------------------------------------- 事件
def events_path() -> str:
    return os.path.join(path_of("runtime"), "events.jsonl")


def append_event(kind: str, payload: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
    event = {
        "id": "evt_" + uuid.uuid4().hex[:12],
        "at": now(),
        "kind": kind,
        "actor": actor,
        "payload": payload,
    }
    ensure_dirs()
    with open(events_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(limit: int = 200) -> List[Dict[str, Any]]:
    path = events_path()
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out[-limit:][::-1]


# --------------------------------------------------------------------- 审计
def audit_path() -> str:
    return os.path.join(path_of("runtime"), "audit.jsonl")


def _canonical(record: Dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


AUDIT_LOCK = threading.Lock()


def audit(action: str, actor: str, role: str, detail: Dict[str, Any]) -> Dict[str, Any]:
    """追加一条审计记录。全程加锁：读末条哈希与写入必须原子，
    否则并发请求会拿到同一个 prev，导致链分叉。"""
    with AUDIT_LOCK:
        ensure_dirs()
        prev = ""
        path = audit_path()
        if os.path.exists(path):
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 4096))
                tail = fh.read().decode("utf-8", "ignore").strip().splitlines()
                if tail:
                    try:
                        prev = json.loads(tail[-1]).get("hash", "")
                    except json.JSONDecodeError:
                        prev = ""
        record = {
            "at": now(),
            "action": action,
            "actor": actor,
            "role": role,
            "detail": detail,
            "prev": prev,
        }
        record["hash"] = hashlib.sha256((prev + _canonical(record)).encode()).hexdigest()
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def read_audit(limit: int = 200) -> List[Dict[str, Any]]:
    path = audit_path()
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[-limit:][::-1]


def verify_audit() -> Dict[str, Any]:
    with AUDIT_LOCK:
        rows = list(reversed(read_audit(limit=100000)))
    prev = ""
    for idx, row in enumerate(rows):
        if row.get("prev", "") != prev:
            return {"ok": False, "broken_at": idx, "reason": "prev 指针不连续", "records": len(rows)}
        expect = hashlib.sha256((prev + _canonical(row)).encode()).hexdigest()
        if expect != row.get("hash"):
            return {"ok": False, "broken_at": idx, "reason": "记录内容被改动", "records": len(rows)}
        prev = row["hash"]
    return {"ok": True, "records": len(rows)}


# --------------------------------------------------------------------- 脱敏
import re

PHONE = re.compile(r"\b1[3-9]\d{9}\b")
IDCARD = re.compile(r"\b\d{17}[\dxX]\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
NAME_HINT = re.compile(r"(同学|学生)[:：]?\s*[\u4e00-\u9fa5]{2,4}")


def mask(text: str) -> str:
    text = PHONE.sub("[手机号]", text)
    text = IDCARD.sub("[证件号]", text)
    text = EMAIL.sub("[邮箱]", text)
    return text
