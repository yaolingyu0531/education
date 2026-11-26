# API 调用示例

> 所有请求 `Content-Type: application/json`；除登录与健康检查外都需要 `Authorization: Bearer <token>`。

## 1. 登录

```bash
curl -X POST http://127.0.0.1:8010/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"teacher","password":"teacher123"}'
```

```json
{"token":"<32位令牌>","username":"teacher","role":"teacher","permissions":["advice:draft",...]}
```

## 2. 检索业务文档

```bash
curl "http://127.0.0.1:8010/kb/search?q=%E6%8D%A2%E5%B2%97%20%E5%8F%8D%E9%A6%88&k=3" \
  -H "Authorization: Bearer $TOKEN"
```

返回里每条命中带 `path`（出处文件）、`heading`（小节）与 `facts`（`education-fNN` 证据编号）。

## 3. 起草建议

```bash
curl -X POST http://127.0.0.1:8010/advice \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "student": "S-042",
    "course": "机电一体化·设备维护",
    "task": "设备点检与交接",
    "observations": ["6 月 3 日点检表漏填润滑项", "交接班记录未签名，次日重复停机"]
  }'
```

```json
{
  "id": "adv_xxx",
  "status": "pending_confirmation",
  "confidence": 0.95,
  "suggestions": [
    {"action": "点检表填写润滑项后再复核一次", "evidence": "6 月 3 日点检表漏填润滑项",
     "generated_by": "qwen3:4b", "fact_refs": ["f10", "f42"]}
  ],
  "llm": {"used": true, "model": "qwen3:4b", "rejected": 0}
}
```

缺行为实例时会返回 `status: "blocked"` 与 `blockers` 列表，不生成任何建议。

## 4. 人工确认

```bash
curl -X POST http://127.0.0.1:8010/advice/adv_xxx/confirm \
  -H "Authorization: Bearer $REVIEWER_TOKEN" -H "Content-Type: application/json" \
  -d '{"decision":"approve","note":"依据充分"}'
```

起草人确认自己的建议会得到 `403 self_sign_denied`。

## 5. 审计校验

```bash
curl http://127.0.0.1:8010/audit/verify -H "Authorization: Bearer $TOKEN"
# {"ok": true, "records": 24}
```
