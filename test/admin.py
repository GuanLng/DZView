# Admin dashboard (ASCII only, UTF-8)
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import os

try:
    from .metrics import get_totals
    from .proxy import allowed_domains
except ImportError:
    from metrics import get_totals
    from proxy import allowed_domains

router = APIRouter()
ADMIN_KEY_ENV = "ADMIN_API_KEY"
SESSION_KEY = "admin_session_key"
_active_sessions = set()


def _get_expected_key() -> str | None:
    """Get the expected API key from the environment."""
    return os.getenv(ADMIN_KEY_ENV) or None


def _has_valid_session(request: Request) -> bool:
    """Check if the request has a valid session."""
    token = request.cookies.get(SESSION_KEY)
    return bool(token and token in _active_sessions)


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    expected = _get_expected_key()
    if not expected:
        # No key configured -> auto redirect to admin
        return RedirectResponse("/admin", status_code=302)
    html = """<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>登录后台</title>
<style>body{font-family:Arial,sans-serif;background:#f5f7fa;padding:40px;color:#333}form{max-width:340px;margin:0 auto;background:#fff;padding:22px26px;border-radius:10px;box-shadow:02px6px rgba(0,0,0,.08);display:flex;flex-direction:column;gap:14px}h1{font-size:22px;margin:004px}input{padding:10px12px;border:1px solid #d1d5db;border-radius:6px;font-size:14px}button{padding:10px12px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}button:hover{background:#1d4ed8}.msg{min-height:18px;font-size:13px}.err{color:#c0392b}.ok{color:#2e7d32}.footer{margin-top:30px;font-size:11px;color:#777;text-align:center}</style></head><body>
<form id='loginForm'>
 <h1>管理员登录</h1>
 <p style='font-size:12px;color:#555;margin:0'>请输入配置的 API Key以访问管理后台。</p>
 <input id='apiKeyInput' type='password' placeholder='API Key'>
 <button type='submit'>登录</button>
 <div id='msg' class='msg'></div>
</form>
<div class='footer'>Py-Proxy ©2024</div>
<script>
async function doLogin(e){e.preventDefault();const k=document.getElementById('apiKeyInput').value.trim();if(!k){setMsg('请输入 Key','err');return;}const r=await fetch('/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k})});if(r.status===200){setMsg('登录成功','ok');setTimeout(()=>{location.href='/admin';},400);}else{setMsg('登录失败 ('+r.status+')','err');}}
function setMsg(t,c){const el=document.getElementById('msg');el.className='msg '+(c||'');el.textContent=t;}
document.getElementById('loginForm').addEventListener('submit',doLogin);
</script></body></html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/admin/login")
async def admin_login(request: Request):
    expected = _get_expected_key()
    if not expected:
        return JSONResponse({"detail": "No API key configured"}, status_code=400)
    data = await request.json()
    provided = (data.get("key") or "").strip()
    if provided != expected:
        return JSONResponse({"detail": "Invalid key"}, status_code=401)
    # Create session token (here just the key, could be random)
    _active_sessions.add(provided)
    resp = JSONResponse({"detail": "ok"})
    resp.set_cookie(SESSION_KEY, provided, httponly=True, secure=False, max_age=3600, samesite="Lax")
    return resp


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    expected = _get_expected_key()
    if expected and not _has_valid_session(request):
        return RedirectResponse("/admin/login", status_code=302)

    allowed_html = ''.join(f"<li><code>{d}</code></li>" for d in allowed_domains) or "<li><em>未配置 (默认全允许)</em></li>"

    html = """<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>管理后台</title>
<style>body{font-family:Arial,sans-serif;background:#f5f7fa;padding:28px;color:#333}h1{margin:0018px}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px}.card{background:#fff;border:1px solid #e1e4e8;border-radius:10px;padding:18px;box-shadow:02px4px rgba(0,0,0,.05)}table{width:100%;border-collapse:collapse;font-size:13px}th,td{border:1px solid #e1e4e8;padding:6px8px;text-align:left}th{background:#f1f5f9}.footer{margin-top:40px;font-size:12px;color:#777;text-align:center}code{background:#f1f5f9;padding:2px4px;border-radius:4px}button.logout{padding:6px10px;border:none;border-radius:6px;background:#ef4444;color:#fff;cursor:pointer;margin-top:16px}button.logout:hover{background:#dc2626}.muted{color:#666;font-size:12px;margin-top:4px}</style></head><body>
<h1>Py-Proxy 管理后台</h1>
<div class='grid'>
 <div class='card'>
 <h2>总体流量</h2>
 <div id='totals'>加载中...</div>
 <div id='rates' class='muted'>速率: 加载中...</div>
 <div class='muted' id='uptime'></div>
 </div>
 <div class='card'>
 <h2>域名统计</h2>
 <table id='domainTable'>
 <thead><tr><th>域名</th><th>请求数</th><th>上行</th><th>下行</th><th>总字节</th></tr></thead>
 <tbody><tr><td colspan='5'>加载中...</td></tr></tbody>
 </table>
 </div>
 <div class='card'>
 <h2>允许域名</h2>
 <ul>__ALLOWED__</ul>
 </div>
 <div class='card'>
 <h2>速率限制</h2>
 <p><em>未启用</em></p>
 </div>
</div>
<form method='post' action='/admin/logout'>
 <button type='submit' class='logout'>退出登录</button>
</form>
<div class='footer'>Py-Proxy ©2024</div>
<script>
function fmtBytes(b){if(!b)return'0 B';const k=1024,s=['B','KB','MB','GB','TB'];const i=Math.floor(Math.log(b)/Math.log(k));const v=b/Math.pow(k,i);return v.toFixed(v>=100?0:v>=10?1:2)+' '+s[i];}
function fmtKBps(bps){return (bps/1024).toFixed(bps>=102400?0:bps>=10240?1:2)+' KB/s';}
function loadMetrics(){fetch('/metrics/traffic').then(r=>r.json()).then(m=>{document.getElementById('totals').innerHTML='上行: <strong>'+fmtBytes(m.total_up_bytes)+'</strong><br>下行: <strong>'+fmtBytes(m.total_down_bytes)+'</strong><br>总计: <strong>'+fmtBytes(m.total_bytes)+'</strong><br>请求数: <strong>'+m.total_requests+'</strong>';document.getElementById('rates').innerHTML='上行速率: '+fmtKBps(m.rates.up_bps)+' | 下行速率: '+fmtKBps(m.rates.down_bps)+' (窗口 '+m.window_seconds+'s)';document.getElementById('uptime').innerHTML='运行时间: '+Math.floor(m.uptime_seconds)+' 秒';const tbody=document.querySelector('#domainTable tbody');const entries=Object.entries(m.domain_stats);if(!entries.length){tbody.innerHTML='<tr><td colspan="5"><em>暂无数据</em></td></tr>';return;}tbody.innerHTML=entries.map(([d,st])=>'<tr><td>'+d+'</td><td>'+st.requests+'</td><td>'+fmtBytes(st.up_bytes)+'</td><td>'+fmtBytes(st.down_bytes)+'</td><td>'+fmtBytes(st.up_bytes+st.down_bytes)+'</td></tr>').join('');});}
loadMetrics();setInterval(loadMetrics,2000);
</script>
</body></html>"""

    html = html.replace("__ALLOWED__", allowed_html)
    return HTMLResponse(content=html, status_code=200)


@router.post('/admin/logout')
async def admin_logout(request: Request):
    token = request.cookies.get(SESSION_KEY)
    if token and token in _active_sessions:
        _active_sessions.discard(token)
    resp = RedirectResponse('/admin/login', status_code=302)
    resp.delete_cookie(SESSION_KEY)
    return resp


@router.get('/admin/data')
async def admin_data(request: Request):
    expected = _get_expected_key()
    if expected and not _has_valid_session(request):
        return JSONResponse({'detail': 'Not authenticated'}, status_code=401)
    totals = await get_totals()
    return JSONResponse({'allowed_domains': allowed_domains, 'traffic': totals, 'rate_limit': {'max_requests_per_minute': None}})
