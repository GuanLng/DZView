# Py-Proxy (DZView 内置 FastAPI代理服务)

一个基于 FastAPI 的轻量级 HTTP/HTTPS代理与监控后台，提供域名白名单、安全防护、流量统计与速率限制（Rate Limit）等功能。适合内网穿透二次封装、调试抓包、受控数据访问等场景。

## 功能特点
- 多方法代理: GET / POST / PUT / DELETE / PATCH / HEAD / OPTIONS
- 域名允许列表 (正则模式) 防止任意外部请求
- 阻止访问私有网段 (10.x /172.16-31 /192.168 /127.0.0.0/8 等)
- 全局流量与域名请求统计 (上行 / 下行 /速率 / 最近窗口平均)
- 管理后台页面 (无需前置构建，纯 HTML + JS)
- 可配置速率限制 (按 IP、按域名固定时间窗口)
- 响应自动添加 RateLimit相关头 (启用后)
-统一错误码与提示 (403/413/429/502/504/500)

##目录结构简述
```
main.py 应用入口 (FastAPI 实例)
proxy.py 核心代理与速率限制逻辑
admin.py 管理后台 HTML及配置接口
metrics.py 流量统计与速率计算
security.py 域名匹配 / 私网判断
static/ 前端静态页面 (可选)
```

## 快速启动
```bash
pip install -r test/py_proxy.egg-info/requires.txt
python test/main.py # 或 uvicorn test.main:app --reload
```
访问：
- 根路径 `/` 自动跳转到 `/static/index.html`（若存在）
- 管理后台 `/admin`（如设置了 ADMIN_API_KEY 则需登录）

## 环境变量
|变量名 |说明 | 示例 |
|--------|------|------|
| ALLOWED_DOMAINS |逗号分隔的正则表达式列表 (为空则全部允许) | `^example\\.com$,^api\\.foo\\.org$` |
| ADMIN_API_KEY | 管理后台访问密钥 (为空则免登录) | `my-secret-key` |

> 注意：`ALLOWED_DOMAINS` 中每一项将被 `re.compile`，请使用合法正则。

##主要接口
| 路径 | 方法 |说明 |
|------|------|------|
| `/proxy/{target}` | 任意 |代理转发 (target 可为完整 URL 或域名路径) |
| `/metrics/traffic` | GET | 当前流量统计 JSON |
| `/metrics/traffic/reset` | POST | 重置统计计数 |
| `/admin/login` | GET/POST | 后台登录页与登录提交 |
| `/admin` | GET | 后台页面 (HTML) |
| `/admin/rate_limit` | GET | 获取速率限制配置与当前窗口计数 |
| `/admin/rate_limit/update` | POST | 更新速率限制配置 |

### Rate Limit 更新示例
```bash
curl -X POST http://localhost:8000/admin/rate_limit/update \
 -H "Content-Type: application/json" \
 -d '{"enabled": true, "window_seconds":60, "max_requests_per_ip":100, "max_requests_per_domain":250}'
```
返回示例：
```json
{
 "config": {
 "enabled": true,
 "window_seconds":60,
 "max_requests_per_ip":100,
 "max_requests_per_domain":250,
 "reset_epoch":1730000000
 },
 "usage": {
 "enabled": true,
 "window_id":28833333,
 "window_seconds":60,
 "reset_epoch":1730000000,
 "counts_ip": {"127.0.0.1":3},
 "counts_domain": {"example.com":2},
 "max_requests_per_ip":100,
 "max_requests_per_domain":250
 }
}
```
响应头 (启用时)：
```
X-RateLimit-Limit-IP:100
X-RateLimit-Remaining-IP:97
X-RateLimit-Limit-Domain:250
X-RateLimit-Remaining-Domain:248
X-RateLimit-Reset:1730000000
```

###429 情况
超过限制时：
```
HTTP/1.1429 Rate limit exceeded
{"detail": "Rate limit exceeded"}
```

## 安全提示
- 建议生产环境务必设置 `ADMIN_API_KEY`。
- 如需更复杂速率策略（滑动窗口 /令牌桶 / Redis 集群共享），需扩展当前 `proxy.py` 实现。
- 添加 HTTPS终端请使用反向代理 (Nginx/Caddy) 或配置 Uvicorn SSL。

## 开发调试
```bash
uvicorn test.main:app --reload --port8000
```
代码风格可选用 ruff：
```bash
pip install ruff
ruff check .
```

## 常见问题
1.速率限制未生效：确认管理后台已勾选“启用”并保存。
2. 域名被拒绝：检查是否匹配正则；打印日志查看 `Domain not allowed` 信息。
3. 大响应被阻断：默认最大响应100MB，可在 `proxy.py` 修改 `MAX_RESPONSE_SIZE`。

## 后续规划
- WebSocket 实时推送替换轮询
- 滑动窗口/令牌桶限流
- 请求历史与错误分布可视化
- 配置持久化 (JSON / SQLite)

## License
MIT (如果未声明请根据仓库实际许可调整)。
