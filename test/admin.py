# Admin dashboard (ASCII only, UTF-8)
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
import os

try:
    from .metrics import get_totals
    from .proxy import allowed_domains
except ImportError:
    from metrics import get_totals
    from proxy import allowed_domains

router = APIRouter()
ADMIN_KEY_ENV = "ADMIN_API_KEY"

@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    html = """<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>Py-Proxy 管理后台</title>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
:root { --bg:#f5f7fa; --card:#ffffff; --border:#e1e4e8; --text:#2d3748; --accent:#2563eb; --danger:#d32f2f; --ok:#2e7d32; }
*{box-sizing:border-box;margin:0;padding:0;font-family:"Segoe UI",Arial,sans-serif;}
body{background:var(--bg);color:var(--text);padding:28px;}
header{margin-bottom:24px;}
h1{font-size:26px;font-weight:600;}
.small{font-size:12px;color:#606f7b;margin-top:4px;}
.container{max-width:1100px;margin:0 auto;}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px;}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px;box-shadow:02px4px rgba(0,0,0,0.05);display:flex;flex-direction:column;gap:10px;}
.card h2{font-size:18px;margin-bottom:4px;}
.actions{display:flex;align-items:center;gap:8px;margin-top:10px;}
input[type=password]{padding:8px10px;border:1px solid var(--border);border-radius:6px;font-size:14px;width:220px;}
button{padding:8px14px;font-size:14px;border:none;border-radius:6px;cursor:pointer;background:var(--accent);color:#fff;transition:.2s;}
button:hover{background:#1d4ed8;}
button.secondary{background:#64748b;}
button.secondary:hover{background:#4b5563;}
.msg{margin-top:6px;font-size:13px;min-height:18px;}
.msg.ok{color:var(--ok);} .msg.err{color:var(--danger);} .badge{display:inline-block;padding:3px8px;background:var(--accent);color:#fff;border-radius:14px;font-size:12px;font-weight:500;}
pre,code{background:#f0f2f5;padding:4px6px;border-radius:4px;font-size:12px;}
ul{list-style:disc;padding-left:20px;}
.footer{margin-top:40px;font-size:12px;color:#828282;text-align:center;}
.skeleton{background:#e2e8f0;height:14px;width:100%;border-radius:4px;animation:pulse1.4s infinite ease-in-out;}
@keyframes pulse{0%{opacity:.6}50%{opacity:1}100%{opacity:.6}}
.table{width:100%;border-collapse:collapse;font-size:13px;}
.table td,.table th{border:1px solid var(--border);padding:6px8px;}
</style></head><body>
<div class='container'>
<header>
 <h1>Py-Proxy 管理后台</h1>
 <p class='small'>提供对代理运行状态的查看。设置的环境变量: <code>ADMIN_API_KEY</code> (留空则开放访问)。</p>
</header>
<div class='card' style='margin-bottom:24px;'>
 <h2>认证</h2>
 <p style='font-size:13px;'>输入 API Key 后点击“加载”获取数据。若后台未配置则无需输入。</p>
 <div class='actions'>
 <input id='keyInput' type='password' placeholder='输入 API Key'>
 <button id='loadBtn'>加载</button>
 <button id='clearBtn' class='secondary'>清除</button>
 </div>
 <div id='msg' class='msg'></div>
</div>
<div class='grid'>
 <div class='card'>
 <h2>流量统计</h2>
 <div id='stats'><div class='skeleton'></div><div class='skeleton' style='width:70%;margin-top:6px;'></div></div>
 </div>
 <div class='card'>
 <h2>允许域名</h2>
 <ul id='allowList' style='max-height:220px;overflow:auto'><li class='skeleton' style='list-style:none;height:14px;width:60%;'></li></ul>
 </div>
 <div class='card'>
 <h2>速率限制</h2>
 <div id='rateLimit'><div class='skeleton' style='width:40%;'></div></div>
 </div>
</div>
<div class='card' style='margin-top:24px;'>
 <h2>调试接口</h2>
 <table class='table'>
 <tr><th>接口</th><th>说明</th></tr>
 <tr><td><code>/proxy/&lt;url&gt;</code></td><td>代理访问目标 URL</td></tr>
 <tr><td><code>/metrics/traffic</code></td><td>JSON 流量统计</td></tr>
 <tr><td><code>/admin/data</code></td><td>管理数据 (需 Key)</td></tr>
 </table>
</div>
<div class='footer'>Py-Proxy ?2024 | 管理视图</div>
</div>
<script>
function fmtBytes(b){if(!b)return'0 B';const k=1024,s=['B','KB','MB','GB','TB'];const i=Math.floor(Math.log(b)/Math.log(k));const v=b/Math.pow(k,i);return v.toFixed(v>=100?0:v>=10?1:2)+' '+s[i];}
function esc(t){return t.replace(/[&<>\"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;','\'':'&#39;'}[m]));}
function setMsg(text,type){const el=document.getElementById('msg');el.className='msg'+(type?(' '+type):'');el.textContent=text;}
async function load(){const key=document.getElementById('keyInput').value.trim(); if(key){localStorage.setItem('adminKey',key);} else {localStorage.removeItem('adminKey');}
 setMsg('正在加载...','');
 const headers={}; const stored=localStorage.getItem('adminKey'); if(stored) headers['X-API-Key']=stored;
 try { const url='/admin/data'+(stored?('?key='+encodeURIComponent(stored)):''); const r=await fetch(url,{headers}); if(!r.ok){ setMsg('认证失败或服务未配置密钥 (状态码 '+r.status+')','err'); return; } const data=await r.json(); setMsg('加载成功','ok');
 document.getElementById('stats').innerHTML='上行: <strong>'+fmtBytes(data.traffic.total_up_bytes)+'</strong> | 下行: <strong>'+fmtBytes(data.traffic.total_down_bytes)+'</strong> | 总计: <strong>'+fmtBytes(data.traffic.total_bytes)+'</strong>';
 document.getElementById('allowList').innerHTML = data.allowed_domains.length? data.allowed_domains.map(d=>'<li><code>'+esc(d)+'</code></li>').join('') : '<li><em>(未配置白名单, 默认全部允许)</em></li>';
 document.getElementById('rateLimit').innerHTML = data.rate_limit.max_requests_per_minute? '<span class="badge">'+data.rate_limit.max_requests_per_minute+' req/min</span>' : '<em>未启用</em>';
 } catch(e){ setMsg('请求异常: '+e,'err'); console.error(e); }
}
function clearKey(){localStorage.removeItem('adminKey'); document.getElementById('keyInput').value=''; setMsg('已清除密钥','');
 document.getElementById('stats').textContent='未加载'; document.getElementById('allowList').innerHTML=''; document.getElementById('rateLimit').textContent='未加载';}
const stored=localStorage.getItem('adminKey'); if(stored){ document.getElementById('keyInput').value=stored; }
// 自动尝试加载一次（如果已存储密钥）
if(stored){ load(); }
//绑定事件
 document.getElementById('loadBtn').addEventListener('click',load);
 document.getElementById('clearBtn').addEventListener('click',clearKey);
</script></body></html>"""
    return HTMLResponse(content=html, status_code=200)


def _check_api_key(request: Request) -> bool:
    expected = os.getenv(ADMIN_KEY_ENV)
    if not expected:
        return True
    provided = request.headers.get('X-API-Key') or request.query_params.get('key')
    return provided == expected

@router.get('/admin/data')
async def admin_data(request: Request):
    if not _check_api_key(request):
        return JSONResponse({'detail': 'Invalid or missing API key'}, status_code=401)
    totals = await get_totals()
    return JSONResponse({'allowed_domains': allowed_domains, 'traffic': totals, 'rate_limit': {'max_requests_per_minute': None}})
