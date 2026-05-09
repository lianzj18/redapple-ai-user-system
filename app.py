
import os, sys, json, secrets, sqlite3, hashlib, hmac, shutil, subprocess
from pathlib import Path
from typing import Optional
import httpx
from fastapi import FastAPI, Request, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

POSTGRESQL_PREPARED = True  # DATABASE_URL is reserved for future PostgreSQL migration; current demo uses SQLite by default.
BASE = Path(__file__).resolve().parent
DB = BASE / "redapple_users.db"
UPLOAD = BASE / "uploads" / "firmware"
CONFIG_UPLOAD = BASE / "uploads" / "configs"
UPLOAD.mkdir(parents=True, exist_ok=True)
CONFIG_UPLOAD.mkdir(parents=True, exist_ok=True)


MODEL_CATALOG = {
    "ollama-qwen-1.5b": {
        "display": "本地 Ollama - Qwen2.5 1.5B",
        "provider": "本地Ollama",
        "api_url": "http://127.0.0.1:11434/v1",
        "model_name": "qwen2.5:1.5b",
        "api_key": "ollama",
        "note": "适合本地测试，需要先安装 Ollama 并执行 ollama pull qwen2.5:1.5b"
    },
    "ollama-qwen-0.5b": {
        "display": "本地 Ollama - Qwen2.5 0.5B",
        "provider": "本地Ollama",
        "api_url": "http://127.0.0.1:11434/v1",
        "model_name": "qwen2.5:0.5b",
        "api_key": "ollama",
        "note": "更小更快，适合低配置电脑，需要先执行 ollama pull qwen2.5:0.5b"
    },
    "deepseek-chat": {
        "display": "DeepSeek - deepseek-chat",
        "provider": "DeepSeek",
        "api_url": "https://api.deepseek.com",
        "model_name": "deepseek-chat",
        "api_key": "",
        "note": "需要在后台环境变量 DEEPSEEK_API_KEY 中配置 API Key"
    },
    "deepseek-reasoner": {
        "display": "DeepSeek - deepseek-reasoner",
        "provider": "DeepSeek",
        "api_url": "https://api.deepseek.com",
        "model_name": "deepseek-reasoner",
        "api_key": "",
        "note": "需要在后台环境变量 DEEPSEEK_API_KEY 中配置 API Key"
    }
}


def resolve_model_api_key(model_key: str, saved_key: str = ""):
    item = MODEL_CATALOG.get(model_key)
    if not item:
        return saved_key or ""
    if item["provider"] == "DeepSeek":
        return saved_key or os.environ.get("DEEPSEEK_API_KEY", "")
    return item.get("api_key", "")


app = FastAPI(title="红苹果AI用户系统")
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "redapple-user-system-local-demo-change-me"))

CSS = """
:root{--red:#df2735;--bg:#f5f7fb;--text:#111827;--muted:#6b7280;--line:#e7eaf0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif;color:var(--text)}
.shell{display:grid;grid-template-columns:270px 1fr;min-height:100vh}.side{background:#fff;border-right:1px solid var(--line);padding:26px 20px;display:flex;flex-direction:column}
.brand{display:flex;gap:12px;align-items:center;margin-bottom:26px}.logo{font-size:38px}.brand h1{font-size:28px;color:var(--red);margin:0}.brand p{margin:2px 0 0;color:var(--muted);font-size:13px}
nav{display:flex;flex-direction:column;gap:8px}nav a{text-decoration:none;color:#374151;padding:14px 16px;border-radius:16px;font-weight:800}nav a.on,nav a:hover{background:#fff0f1;color:var(--red)}
.bottom{margin-top:auto;color:var(--muted);font-size:13px}.logout{display:block;color:var(--red);font-weight:800;margin-top:10px}
.main{padding:28px 34px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.top h2{margin:0;font-size:30px}.top p{margin:6px 0 0;color:var(--muted)}.userbox{background:#fff;border:1px solid var(--line);border-radius:16px;padding:12px 16px;font-weight:800}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px;margin-bottom:22px}.metric{background:#fff;border:1px solid var(--line);border-radius:22px;padding:22px}.metric b{font-size:34px}.metric p{margin:0;color:var(--muted);font-weight:800}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:22px;padding:22px;margin-bottom:20px}.panel h3{margin:0 0 16px;font-size:20px}.muted{color:var(--muted)}
input,select,textarea{width:100%;min-height:42px;border:1px solid var(--line);border-radius:12px;padding:0 12px;font-size:14px;background:#fff}textarea{padding:12px;min-height:120px}
button{height:42px;border:0;border-radius:12px;background:var(--red);color:white;font-weight:900;padding:0 18px;cursor:pointer}button.mini{height:30px;font-size:12px;padding:0 10px}
.formgrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;align-items:end}.formgrid5{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;align-items:end}.formcol{display:grid;gap:12px;max-width:820px}.formcol label{font-weight:800}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;background:#f8fafc;color:#6b7280;padding:12px}td{padding:12px;border-top:1px solid #edf0f5;vertical-align:middle}code{background:#f3f4f6;border-radius:6px;padding:4px 6px;word-break:break-all}.badge{background:#e0f2fe;color:#0369a1;border-radius:999px;padding:4px 8px;font-size:12px;font-weight:900}
.login{min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#fff5f6,#f5f7fb)}.card{width:420px;background:#fff;border:1px solid var(--line);border-radius:28px;padding:34px}.card h1{color:var(--red);margin:8px 0}.card form{display:grid;gap:12px}.err{background:#fee2e2;color:#991b1b;padding:10px;border-radius:10px;margin:10px 0}
.chat{height:510px;overflow:auto;background:#fbfcfe;border:1px solid #edf0f5;border-radius:18px;padding:16px}.msg{max-width:72%;padding:12px 16px;border-radius:16px;margin:12px 0;line-height:1.7}.user{margin-left:auto;background:#ffe8eb}.bot{background:#f3f4f6}.send{display:grid;grid-template-columns:1fr 96px;gap:12px;margin-top:12px}
.log,.out{background:#0f172a;color:#74f7d1;border-radius:18px;padding:16px;white-space:pre-wrap;min-height:220px;overflow:auto;font-family:Consolas,monospace}
.notice{background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;border-radius:16px;padding:14px;margin-bottom:18px;font-weight:800}

.summary-list{display:grid;gap:12px}
.summary-list div{background:#f8fafc;border-radius:14px;padding:14px;display:flex;justify-content:space-between;align-items:center}
.summary-list span{color:#6b7280;font-weight:800}
.summary-list b{font-size:28px}
.profile-box{background:#f8fafc;color:#111827;border:1px solid #edf0f5;border-radius:18px;padding:16px;min-height:220px;white-space:pre-wrap;line-height:1.8;font-family:'Microsoft YaHei',sans-serif}
.wide-panel{grid-column:1 / -1}


.model-select-form{display:grid;gap:14px}
.model-option{display:grid;grid-template-columns:28px 1fr;gap:12px;align-items:start;background:#f8fafc;border:1px solid #edf0f5;border-radius:16px;padding:16px;cursor:pointer}
.model-option input{width:18px;height:18px;min-height:auto;margin-top:4px}
.model-option b{font-size:16px}
.model-option p{margin:6px 0 0}


/* v1.5 UI simplified fixes */
.checkbox-line{display:flex!important;align-items:center;gap:8px;font-weight:800}
.checkbox-line input{width:18px!important;height:18px!important;min-height:auto!important}
.simple-current{background:#f8fafc;border:1px solid #edf0f5;border-radius:16px;padding:16px;font-weight:900}
.model-select-form{display:grid;gap:12px}
.model-option{display:grid;grid-template-columns:28px 1fr;gap:12px;align-items:center;background:#f8fafc;border:1px solid #edf0f5;border-radius:16px;padding:16px;cursor:pointer}
.model-option input{width:18px!important;height:18px!important;min-height:auto!important;margin:0}
.model-option b{font-size:16px}
.role-form{display:grid;gap:12px;max-width:900px}
.role-form label{font-weight:900}
.role-card-list{display:grid;gap:16px}
.role-card{border:1px solid #edf0f5;border-radius:18px;padding:16px;background:#fbfcfe}
.role-card-head{display:flex;justify-content:space-between;gap:12px;align-items:center}
.role-card-head h4{margin:0;font-size:18px}
.role-tags{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.role-tags span{background:#e0f2fe;color:#0369a1;border-radius:999px;padding:5px 10px;font-weight:900;font-size:13px}
.prompt-preview{background:#fff;border:1px solid #edf0f5;border-radius:14px;padding:12px;white-space:pre-wrap;line-height:1.7;max-height:160px;overflow:auto;font-family:'Microsoft YaHei',sans-serif}


.firmware-card{border:1px solid #edf0f5;border-radius:18px;padding:16px;margin:14px 0;background:#fbfcfe}
.firmware-card h4{margin:0 0 8px}

@media(max-width:1200px){.metrics{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}.formgrid,.formgrid5{grid-template-columns:1fr 1fr}}@media(max-width:820px){.shell{grid-template-columns:1fr}.side{display:none}.metrics,.formgrid,.formgrid5{grid-template-columns:1fr}}
"""

def h(p):
    salt = secrets.token_hex(16)
    d = hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), 200000)
    return f"pbkdf2$200000${salt}${d.hex()}"

def chk(stored, p):
    try:
        _, it, salt, hx = stored.split("$", 3)
        d = hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode(), int(it))
        return hmac.compare_digest(d.hex(), hx)
    except Exception:
        return False

def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def q1(sql, args=()):
    with con() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None

def qa(sql, args=()):
    with con() as c:
        return [dict(x) for x in c.execute(sql, args).fetchall()]

def ex(sql, args=()):
    with con() as c:
        cur = c.execute(sql, args); c.commit(); return cur.lastrowid

def log(uid, mod, txt, lvl="INFO"):
    ex("insert into logs(user_id,level,module,content) values(?,?,?,?)", (uid,lvl,mod,txt))

def init_db():
    with con() as c:
        cur = c.cursor()
        cur.executescript("""
        create table if not exists users(id integer primary key autoincrement,username text unique,password_hash text,display_name text,role text default 'user',created_at text default current_timestamp);
        create table if not exists devices(id integer primary key autoincrement,user_id integer,device_id text,device_name text,device_type text,chip text default 'esp32s3',port_hint text,token text,status text default '离线',created_at text default current_timestamp,unique(user_id,device_id));
        create table if not exists models(id integer primary key autoincrement,user_id integer,name text,model_key text,provider text,api_url text,model_name text,api_key text,is_default integer default 0,created_at text default current_timestamp);
        create table if not exists roles(id integer primary key autoincrement,user_id integer,name text,description text,system_prompt text,voice_setting text default '温柔女声',eye_setting text default '自然眨眼',language_setting text default '中文',is_default integer default 0,created_at text default current_timestamp);
        create table if not exists firmware_packages(id integer primary key autoincrement,user_id integer,name text,chip text,version text,description text,created_at text default current_timestamp);
        create table if not exists firmware_files(id integer primary key autoincrement,package_id integer,label text,flash_address text,file_path text,original_filename text,created_at text default current_timestamp);
        create table if not exists bindings(id integer primary key autoincrement,user_id integer,device_db_id integer,model_id integer,role_id integer,firmware_id integer,updated_at text default current_timestamp,unique(user_id,device_db_id));
        create table if not exists chats(id integer primary key autoincrement,user_id integer,role text,content text,created_at text default current_timestamp);
        create table if not exists user_profiles(id integer primary key autoincrement,user_id integer,profile_text text,source_message_count integer default 0,created_at text default current_timestamp);
        create table if not exists logs(id integer primary key autoincrement,user_id integer,level text,module text,content text,created_at text default current_timestamp);
        create table if not exists device_configs(id integer primary key autoincrement,user_id integer,device_db_id integer,config_json text,config_path text,created_at text default current_timestamp);
        """)

        # v1.2 migration: add role device-presentation settings if upgrading from older database
        for col, default_value in [
            ("voice_setting", "温柔女声"),
            ("eye_setting", "自然眨眼"),
            ("language_setting", "中文"),
        ]:
            try:
                cur.execute(f"alter table roles add column {col} text default '{default_value}'")
            except sqlite3.OperationalError:
                pass

        # v1.4 migration: add model_key
        try:
            cur.execute("alter table models add column model_key text")
        except sqlite3.OperationalError:
            pass

        if not cur.execute("select id from users where username='admin'").fetchone():
            cur.execute("insert into users(username,password_hash,display_name,role) values(?,?,?,?)", ("admin",h("redapple123"),"管理员","admin"))
            uid = cur.lastrowid
            cur.execute("insert into devices(user_id,device_id,device_name,device_type,chip,port_hint,token) values(?,?,?,?,?,?,?)", (uid,"toy-001","红苹果玩具001","AI聊天玩具","esp32s3","COM3","ra_"+secrets.token_urlsafe(24)))
            cur.execute("insert into models(user_id,name,model_key,provider,api_url,model_name,api_key,is_default) values(?,?,?,?,?,?,?,1)", (uid,"本地 Ollama - Qwen2.5 1.5B","ollama-qwen-1.5b","本地Ollama","http://127.0.0.1:11434/v1","qwen2.5:1.5b","ollama"))
            cur.execute("insert into roles(user_id,name,description,system_prompt,voice_setting,eye_setting,language_setting,is_default) values(?,?,?,?,?,?,?,1)", (uid,"默认助手","红苹果AI默认角色","你是红苹果AI，是一个友好、自然、适合AI聊天玩具的中文助手。不要自称第三方模型。","温柔女声","自然眨眼","中文"))
            cur.execute("insert into logs(user_id,level,module,content) values(?,?,?,?)", (uid,"INFO","system","红苹果AI用户系统初始化完成"))
        c.commit()

def current(request):
    uid = request.session.get("uid")
    return q1("select id,username,display_name,role from users where id=?", (uid,)) if uid else None

def need(request):
    u = current(request)
    return u

def page(title, active, user, body, subtitle="红苹果AI用户系统"):
    nav = [
        ("dashboard","/","▦ 总览"),("devices","/devices","🖥 设备管理"),("models","/models","⬡ 模型配置"),
        ("roles","/roles","👤 角色设置"),("firmware","/firmware","⚡ 固件烧录"),("logs","/logs","📄 日志中心"),("profile","/profile","👤 用户画像")
    ]
    links = "".join([f'<a class="{"on" if active==k else ""}" href="{href}">{txt}</a>' for k,href,txt in nav])
    return HTMLResponse(f"""<!doctype html><html><head><meta charset='utf-8'><title>红苹果AI用户系统</title><style>{CSS}</style></head><body>
    <div class='shell'><aside class='side'><div class='brand'><div class='logo'>🍎</div><div><h1>红苹果AI</h1><p>用户系统</p></div></div><nav>{links}</nav>
    <div class='bottom'>当前用户：{user['display_name']}<a class='logout' href='/logout'>退出登录</a></div></aside>
    <main class='main'><header class='top'><div><h2>{title}</h2><p>{subtitle}</p></div><div class='userbox'>👤 {user['display_name']}</div></header>{body}</main></div>
    <script>function copyText(t){{navigator.clipboard.writeText(t);alert('已复制')}} function esc(t){{let d=document.createElement('div');d.textContent=t;return d.innerHTML}}</script></body></html>""")

@app.on_event("startup")
def startup():
    init_db()


@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "redapple-ai-user-system"}

@app.get("/login")
def login_page(request: Request, username: str = ""):
    default_user = username or ""
    default_pwd = ""
    hint = "默认管理员：admin / redapple123"
    return HTMLResponse(f"""<html><head><meta charset='utf-8'><style>{CSS}</style></head><body class='login'><div class='card'><div style='font-size:48px'>🍎</div><h1>红苹果AI</h1><p>用户系统</p><form method='post' action='/login'><label>用户名</label><input name='username' value='{default_user}' placeholder='请输入用户名'><label>密码</label><input name='password' type='password' value='{default_pwd}' placeholder='请输入密码'><button>登录</button></form><p class='muted'>{hint}</p><p><a href='/register'>注册新用户</a></p></div></body></html>""")

@app.post("/login")
def login(request: Request, username: str=Form(...), password: str=Form(...)):
    u = q1("select * from users where username=?", (username,))
    if not u or not chk(u["password_hash"], password):
        return HTMLResponse(f"<html><head><style>{CSS}</style></head><body class='login'><div class='card'><div class='err'>用户名或密码错误</div><p>请检查你输入的是注册的新用户名和密码，或者使用管理员账号。</p><a href='/login'>返回登录</a></div></body></html>")
    request.session["uid"] = u["id"]
    log(u["id"],"auth",f"用户 {username} 登录")
    return RedirectResponse("/",302)

@app.get("/register")
def reg_page():
    return HTMLResponse(f"""<html><head><meta charset='utf-8'><style>{CSS}</style></head><body class='login'><div class='card'><h1>注册红苹果AI</h1><p class='muted'>注册成功后，请使用你刚创建的用户名和密码登录。</p><form method='post'><label>用户名</label><input name='username' placeholder='请输入用户名'><label>密码</label><input name='password' type='password' placeholder='请输入密码，至少6位'><button>注册</button></form><p><a href='/login'>返回登录</a></p></div></body></html>""")

@app.post("/register")
def reg(username: str=Form(...), password: str=Form(...)):
    username = username.strip()
    if not username:
        return HTMLResponse(f"<html><head><style>{CSS}</style></head><body class='login'><div class='card'><div class='err'>用户名不能为空</div><a href='/register'>返回</a></div></body></html>")
    if len(password) < 6:
        return HTMLResponse(f"<html><head><style>{CSS}</style></head><body class='login'><div class='card'><div class='err'>密码至少6位</div><a href='/register'>返回</a></div></body></html>")
    try:
        # display_name 自动使用 username，不再要求用户填写昵称
        uid = ex("insert into users(username,password_hash,display_name) values(?,?,?)", (username,h(password),username))
        ex("insert into roles(user_id,name,description,system_prompt,voice_setting,eye_setting,language_setting,is_default) values(?,?,?,?,?,?,?,1)", (uid,"默认助手","默认角色","你是红苹果AI，是一个友好、自然、适合AI聊天玩具的中文助手。不要自称第三方模型。","温柔女声","自然眨眼","中文"))
        ex("insert into models(user_id,name,model_key,provider,api_url,model_name,api_key,is_default) values(?,?,?,?,?,?,?,1)", (uid,"本地 Ollama - Qwen2.5 1.5B","ollama-qwen-1.5b","本地Ollama","http://127.0.0.1:11434/v1","qwen2.5:1.5b","ollama"))
        log(uid, "auth", "新用户注册成功：" + username)
        return RedirectResponse(f"/login?username={username}",302)
    except Exception as e:
        return HTMLResponse(f"<html><head><style>{CSS}</style></head><body class='login'><div class='card'><div class='err'>注册失败：{e}</div><a href='/register'>返回</a></div></body></html>")

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login",302)

@app.get("/")
def dashboard(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    uid=u["id"]
    ds=qa("select * from devices where user_id=?",(uid,))
    ms=qa("select * from models where user_id=?",(uid,))
    rs=qa("select * from roles where user_id=?",(uid,))
    fs=qa("select * from firmware_packages where user_id=?",(uid,))
    logs=qa("select * from logs where user_id=? order by id desc limit 8",(uid,))
    profiles=qa("select * from user_profiles where user_id=? order by id desc limit 1",(uid,))
    bindings=qa("select * from bindings where user_id=?",(uid,))

    latest_profile = profiles[0]["profile_text"] if profiles else "暂无用户画像。进入“用户画像”页面后，可根据历史聊天记录生成。"
    bound_count = len(bindings)

    log_text = "\n".join([f"{x['created_at']} [{x['level']}] {x['module']} - {x['content']}" for x in logs]) or "暂无日志。"

    body=f"""
    <section class='metrics'>
      <div class='metric'><p>当前用户ID</p><b>{u["id"]}</b></div>
      <div class='metric'><p>设备数量</p><b>{len(ds)}</b></div>
      <div class='metric'><p>模型配置</p><b>{len(ms)}</b></div>
      <div class='metric'><p>角色数量</p><b>{len(rs)}</b></div>
    </section>

    <section class='grid2'>
      <div class='panel'>
        <h3>设备配置概况</h3>
        <div class='summary-list'>
          <div><span>已添加设备</span><b>{len(ds)}</b></div>
          <div><span>已绑定设备配置</span><b>{bound_count}</b></div>
          <div><span>固件包数量</span><b>{len(fs)}</b></div>
        </div>
      </div>

      <div class='panel'>
        <h3>最近用户画像</h3>
        <pre class='profile-box'>{latest_profile}</pre>
      </div>

      <div class='panel wide-panel'>
        <h3>最近日志</h3>
        <pre class='log'>{log_text}</pre>
      </div>
    </section>
    """
    return page("总览","dashboard",u,body,"用户设备、模型、角色、固件和画像概况")

@app.get("/devices")
def devices(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    uid=u["id"]
    ds=qa("select * from devices where user_id=? order by id desc",(uid,))
    ms=qa("select * from models where user_id=? order by is_default desc,id desc",(uid,))
    rs=qa("select * from roles where user_id=? order by is_default desc,id desc",(uid,))
    fs=qa("select * from firmware_packages where user_id=? order by id desc",(uid,))
    bs={b["device_db_id"]:b for b in qa("select * from bindings where user_id=?",(uid,))}
    rows=""
    for d in ds:
        b=bs.get(d["id"],{})
        mo="".join([f"<option value='{m['id']}' {'selected' if b.get('model_id')==m['id'] else ''}>{m['name']}</option>" for m in ms])
        ro="".join([f"<option value='{r['id']}' {'selected' if b.get('role_id')==r['id'] else ''}>{r['name']} / {r.get('voice_setting') or '温柔女声'} / {r.get('language_setting') or '中文'}</option>" for r in rs])
        fw="".join([f"<option value='{f['id']}' {'selected' if b.get('firmware_id')==f['id'] else ''}>{f['name']}</option>" for f in fs])
        rows += f"<tr><td>{d['device_id']}</td><td>{d['device_name']}</td><td>{d['chip']}</td><td><code>{d['token']}</code><button class='mini' onclick=\"copyText('{d['token']}')\">复制</button></td><td><form method='post' action='/devices/bind' class='formgrid'><input type='hidden' name='device_db_id' value='{d['id']}'><select name='model_id'><option value='0'>模型</option>{mo}</select><select name='role_id'><option value='0'>角色</option>{ro}</select><select name='firmware_id'><option value='0'>固件</option>{fw}</select><button class='mini'>保存</button></form></td></tr>"
    body=f"""<div class='panel'><h3>添加设备</h3><form class='formgrid5' method='post' action='/devices/create'><input name='device_id' placeholder='设备ID' required><input name='device_name' placeholder='设备名称' required><input name='device_type' value='AI聊天玩具'><select name='chip'><option value='esp32s3'>ESP32-S3</option><option value='esp32'>ESP32</option><option value='esp32c3'>ESP32-C3</option></select><input name='port_hint' placeholder='COM3'><button>添加</button></form></div><div class='panel'><h3>设备列表</h3><table><tr><th>设备ID</th><th>名称</th><th>芯片</th><th>Token</th><th>绑定设置</th></tr>{rows}</table></div>"""
    return page("设备管理","devices",u,body,"添加设备，并为设备绑定模型、角色和固件")

@app.post("/devices/create")
def device_create(request: Request, device_id:str=Form(...), device_name:str=Form(...), device_type:str=Form(...), chip:str=Form(...), port_hint:str=Form("")):
    u=need(request); 
    if not u: return RedirectResponse("/login",302)
    ex("insert into devices(user_id,device_id,device_name,device_type,chip,port_hint,token) values(?,?,?,?,?,?,?)",(u["id"],device_id,device_name,device_type,chip,port_hint,"ra_"+secrets.token_urlsafe(24)))
    log(u["id"],"device",f"添加设备 {device_id}")
    return RedirectResponse("/devices",302)

@app.post("/devices/bind")
def bind(request: Request, device_db_id:int=Form(...), model_id:int=Form(0), role_id:int=Form(0), firmware_id:int=Form(0)):
    u=need(request); 
    if not u: return RedirectResponse("/login",302)
    old=q1("select id from bindings where user_id=? and device_db_id=?",(u["id"],device_db_id))
    vals=(model_id or None, role_id or None, firmware_id or None)
    if old: ex("update bindings set model_id=?,role_id=?,firmware_id=?,updated_at=current_timestamp where id=?",(*vals,old["id"]))
    else: ex("insert into bindings(user_id,device_db_id,model_id,role_id,firmware_id) values(?,?,?,?,?)",(u["id"],device_db_id,*vals))
    return RedirectResponse("/devices",302)

@app.get("/models")
def models(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    current = q1("select * from models where user_id=? order by is_default desc,id desc limit 1",(u["id"],))
    rows = ""
    for key, item in MODEL_CATALOG.items():
        checked = "checked" if current and (current.get("model_key") == key or current.get("model_name") == item["model_name"]) else ""
        rows += (
            f"<label class='model-option'>"
            f"<input type='radio' name='model_key' value='{key}' {checked}>"
            f"<div><b>{item['display']}</b></div>"
            f"</label>"
        )

    current_text = "尚未选择模型"
    if current:
        current_text = f"{current['name']}"

    body=f"""
    <div class='panel'>
      <h3>选择模型</h3>
      <form method='post' action='/models/select' class='model-select-form'>
        {rows}
        <button type='submit'>保存选择</button>
      </form>
    </div>

    <div class='panel'>
      <h3>当前模型</h3>
      <div class='simple-current'>{current_text}</div>
    </div>
    """
    return page("模型配置","models",u,body,"选择当前使用的大模型")


@app.post("/models/select")
def model_select(request: Request, model_key:str=Form(...)):
    u=need(request)
    if not u: return RedirectResponse("/login",302)

    item = MODEL_CATALOG.get(model_key)
    if not item:
        return HTMLResponse("模型不存在", status_code=400)

    uid = u["id"]
    api_key = resolve_model_api_key(model_key)

    ex("update models set is_default=0 where user_id=?", (uid,))
    old = q1("select id from models where user_id=? and model_key=?", (uid, model_key))

    if old:
        ex(
            "update models set name=?,provider=?,api_url=?,model_name=?,api_key=?,is_default=1 where id=?",
            (item["display"], item["provider"], item["api_url"], item["model_name"], api_key, old["id"])
        )
    else:
        ex(
            "insert into models(user_id,name,model_key,provider,api_url,model_name,api_key,is_default) values(?,?,?,?,?,?,?,1)",
            (uid, item["display"], model_key, item["provider"], item["api_url"], item["model_name"], api_key)
        )

    log(uid, "model", "切换默认模型：" + item["display"])
    return RedirectResponse("/models",302)


@app.get("/roles")
def roles(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    rs=qa("select * from roles where user_id=? order by is_default desc,id desc",(u["id"],))
    cards=""
    for r in rs:
        default_badge = "<span class='badge'>默认</span>" if r["is_default"] else ""
        cards += (
            f"<div class='role-card'>"
            f"<div class='role-card-head'><h4>{r['name']} {default_badge}</h4>"
            f"<form method='post' action='/roles/{r['id']}/default'><button class='mini'>设为默认</button></form></div>"
            f"<p class='muted'>{r['description'] or ''}</p>"
            f"<div class='role-tags'>"
            f"<span>声音：{r.get('voice_setting') or '温柔女声'}</span>"
            f"<span>眼睛：{r.get('eye_setting') or '自然眨眼'}</span>"
            f"<span>语言：{r.get('language_setting') or '中文'}</span>"
            f"</div>"
            f"<pre class='prompt-preview'>{(r['system_prompt'] or '')}</pre>"
            f"</div>"
        )

    body=f"""<div class='panel formcol'><h3>添加角色</h3>
    <form class='role-form' method='post' action='/roles/create'>
      <label>角色名称</label>
      <input name='name' placeholder='例如 儿童陪伴助手 / 知识问答助手' required>

      <label>角色说明</label>
      <input name='description' placeholder='简要说明这个角色适合什么场景'>

      <label>声音设置</label>
      <select name='voice_setting' id='voiceSetting' onchange='toggleCustomVoice()'>
        <option value='温柔女声'>温柔女声</option>
        <option value='活泼女声'>活泼女声</option>
        <option value='沉稳男声'>沉稳男声</option>
        <option value='儿童音色'>儿童音色</option>
        <option value='机器人音色'>机器人音色</option>
        <option value='自定义声音'>自定义声音</option>
      </select>

      <div id='customVoiceWrap' style='display:none'>
        <label>自定义声音名称</label>
        <input name='custom_voice' id='customVoice' placeholder='例如 小苹果姐姐 / 温柔妈妈 / 科普老师'>
      </div>

      <label>眼睛设置</label>
      <select name='eye_setting'>
        <option value='自然眨眼'>自然眨眼</option>
        <option value='微笑眼'>微笑眼</option>
        <option value='好奇眼'>好奇眼</option>
        <option value='安静聆听'>安静聆听</option>
        <option value='思考动画'>思考动画</option>
        <option value='睡眠模式'>睡眠模式</option>
      </select>

      <label>语言设置</label>
      <select name='language_setting'>
        <option value='中文'>中文</option>
        <option value='英文'>英文</option>
        <option value='中英双语'>中英双语</option>
        <option value='儿童中文'>儿童中文</option>
        <option value='简洁中文'>简洁中文</option>
      </select>

      <label>System Prompt</label>
      <textarea name='system_prompt'>你是红苹果AI，是一个友好、自然、适合AI聊天玩具的中文助手。不要自称第三方模型。</textarea>

      <label class='checkbox-line'><input type='checkbox' name='is_default' value='1'> 设为默认角色</label>
      <button>保存</button>
    </form></div>

    <div class='panel'><h3>角色列表</h3>
      <div class='role-card-list'>{cards}</div>
    </div>

    <script>
    function toggleCustomVoice(){{
      const sel=document.getElementById('voiceSetting');
      const wrap=document.getElementById('customVoiceWrap');
      wrap.style.display = sel.value === '自定义声音' ? 'block' : 'none';
    }}
    </script>
    """
    return page("角色设置","roles",u,body,"设置角色、声音、眼睛和语言")

@app.post("/roles/create")
def role_create(
    request: Request,
    name:str=Form(...),
    description:str=Form(""),
    system_prompt:str=Form(...),
    voice_setting:str=Form("温柔女声"),
    custom_voice:str=Form(""),
    eye_setting:str=Form("自然眨眼"),
    language_setting:str=Form("中文"),
    is_default:int=Form(0)
):
    u=need(request)
    if not u: return RedirectResponse("/login",302)

    if voice_setting == "自定义声音" and custom_voice.strip():
        voice_setting = "自定义声音：" + custom_voice.strip()

    if is_default:
        ex("update roles set is_default=0 where user_id=?",(u["id"],))
    ex(
        "insert into roles(user_id,name,description,system_prompt,voice_setting,eye_setting,language_setting,is_default) values(?,?,?,?,?,?,?,?)",
        (u["id"],name,description,system_prompt,voice_setting,eye_setting,language_setting,is_default)
    )
    return RedirectResponse("/roles",302)

@app.post("/roles/{rid}/default")
def role_default(request: Request, rid:int):
    u=need(request); 
    if not u: return RedirectResponse("/login",302)
    ex("update roles set is_default=0 where user_id=?",(u["id"],)); ex("update roles set is_default=1 where user_id=? and id=?",(u["id"],rid))
    return RedirectResponse("/roles",302)

@app.get("/firmware")
def firmware(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    uid=u["id"]

    ps=qa("select * from firmware_packages where user_id=? order by id desc",(uid,))
    ds=qa("select * from devices where user_id=? order by id desc",(uid,))
    configs=qa("select dc.*, d.device_name, d.device_id from device_configs dc left join devices d on dc.device_db_id=d.id where dc.user_id=? order by dc.id desc limit 10",(uid,))

    pkgopts="".join([f"<option value='{p['id']}'>{p['name']} / {p['version']}</option>" for p in ps])
    devopts="".join([f"<option value='{d['id']}'>{d['device_name']} / {d['chip']} / {d['port_hint'] or '未设置串口'}</option>" for d in ds])

    cards=""
    for p in ps:
        fs=qa("select * from firmware_files where package_id=?",(p["id"],))
        frows="".join([f"<tr><td>{f['label']}</td><td>{f['flash_address']}</td><td>{f['original_filename']}</td></tr>" for f in fs])
        cards += f"<div class='firmware-card'><h4>{p['name']} <span class='badge'>{p['version']}</span></h4><p>{p['description'] or ''}</p><table><tr><th>标签</th><th>地址</th><th>文件</th></tr>{frows}</table></div>"

    cfg_rows=""
    for c in configs:
        cfg_rows += f"<tr><td>{c['created_at']}</td><td>{c['device_name'] or c['device_id']}</td><td><code>{c['config_path']}</code></td></tr>"

    body=f"""
    <div class='notice'>⚠ 固件相关流程分为两步：第一步根据当前设备设置生成固件配置；第二步选择固件包和串口一键烧录。云端部署时，一键烧录仍需在连接开发板的本地电脑运行。</div>

    <section class='grid2'>
      <div class='panel'>
        <h3>一、根据设置生成固件配置</h3>
        <p class='muted'>系统会读取设备绑定的模型、角色、声音、眼睛、语言、Token 和 WebSocket 地址，生成设备配置 JSON。</p>
        <form id='configForm' class='formcol'>
          <label>选择设备</label>
          <select name='device_db_id'>{devopts}</select>
          <button type='button' onclick='generateConfig()'>生成固件配置</button>
        </form>
        <pre class='out' id='configOutput'>等待生成配置。</pre>
      </div>

      <div class='panel'>
        <h3>二、一键烧录固件</h3>
        <p class='muted'>选择固件包、设备串口后调用 esptool 烧录。配置文件会同时保存在本地，可后续嵌入固件或由设备启动后拉取。</p>
        <form class='formcol' id='flashForm'>
          <label>选择设备</label>
          <select name='device_db_id'>{devopts}</select>
          <label>选择固件包</label>
          <select name='package_id'>{pkgopts}</select>
          <label>串口</label>
          <input name='port' placeholder='例如 COM3' required>
          <label>波特率</label>
          <input name='baud' value='460800'>
          <label class='checkbox-line'><input type='checkbox' name='erase_first' value='1'> 烧录前先擦除 Flash</label>
          <button type='button' onclick='flashFw()'>一键烧录</button>
        </form>
        <pre class='out' id='flashOutput'>等待烧录。</pre>
      </div>
    </section>

    <div class='panel'>
      <h3>创建固件包</h3>
      <form class='formgrid' method='post' action='/firmware/package'>
        <input name='name' placeholder='固件包名称，例如 ESP32-S3 小智基础固件'>
        <select name='chip'><option value='esp32s3'>ESP32-S3</option><option value='esp32'>ESP32</option><option value='esp32c3'>ESP32-C3</option></select>
        <input name='version' value='v1.0.0'>
        <input name='description' placeholder='说明'>
        <button>创建</button>
      </form>
    </div>

    <div class='panel'>
      <h3>上传固件文件</h3>
      <form class='formgrid5' method='post' enctype='multipart/form-data' action='/firmware/upload'>
        <select name='package_id'>{pkgopts}</select>
        <input name='label' placeholder='app / bootloader / partition'>
        <input name='flash_address' value='0x10000'>
        <input type='file' name='firmware_file'>
        <button>上传</button>
      </form>
      <p class='muted'>常见地址：bootloader 0x0，partition-table 0x8000，app 0x10000。请以固件说明为准。</p>
    </div>

    <div class='panel'>
      <h3>最近生成的配置</h3>
      <table><tr><th>时间</th><th>设备</th><th>配置文件</th></tr>{cfg_rows}</table>
    </div>

    <div class='panel'>
      <h3>固件包列表</h3>
      {cards}
    </div>

    <script>
    async function generateConfig(){{
      let fd=new FormData(document.getElementById('configForm'));
      let o=document.getElementById('configOutput');
      o.textContent='正在根据设备设置生成配置...';
      let r=await fetch('/firmware/config/generate',{{method:'POST',body:fd}});
      let d=await r.json();
      if(d.ok){{
        o.textContent='配置生成成功：\\n' + d.path + '\\n\\n' + JSON.stringify(d.config,null,2);
      }}else{{
        o.textContent='配置生成失败：' + d.error;
      }}
    }}

    async function flashFw(){{
      let fd=new FormData(document.getElementById('flashForm'));
      let o=document.getElementById('flashOutput');
      o.textContent='正在烧录，请勿拔线...';
      let r=await fetch('/firmware/flash',{{method:'POST',body:fd}});
      let d=await r.json();
      o.textContent=(d.ok?'烧录成功\\n\\n':'烧录失败\\n\\n')+d.output;
    }}
    </script>
    """
    return page("固件烧录","firmware",u,body,"根据设置生成固件配置，并执行一键烧录")


@app.post("/firmware/config/generate")
def firmware_config_generate(request: Request, device_db_id:int=Form(...)):
    u=need(request)
    if not u:
        return JSONResponse({"ok":False,"error":"未登录"}, status_code=401)
    uid=u["id"]

    d=q1("select * from devices where id=? and user_id=?",(device_db_id,uid))
    if not d:
        return JSONResponse({"ok":False,"error":"设备不存在或无权限"})

    b=q1("select * from bindings where user_id=? and device_db_id=?",(uid,device_db_id))
    model = None
    role = None
    firmware = None

    if b and b.get("model_id"):
        model=q1("select * from models where id=? and user_id=?",(b["model_id"],uid))
    if not model:
        model=q1("select * from models where user_id=? order by is_default desc,id desc limit 1",(uid,))

    if b and b.get("role_id"):
        role=q1("select * from roles where id=? and user_id=?",(b["role_id"],uid))
    if not role:
        role=q1("select * from roles where user_id=? order by is_default desc,id desc limit 1",(uid,))

    if b and b.get("firmware_id"):
        firmware=q1("select * from firmware_packages where id=? and user_id=?",(b["firmware_id"],uid))

    host=request.headers.get("host","127.0.0.1:8000")
    proto=request.headers.get("x-forwarded-proto", "http")
    ws_scheme="wss" if proto == "https" else "ws"
    ws_url=f"{ws_scheme}://{host}/xiaozhi/v1/"

    config={
        "brand":"RedAppleAI",
        "device":{
            "database_id":d["id"],
            "device_id":d["device_id"],
            "device_name":d["device_name"],
            "device_type":d["device_type"],
            "chip":d["chip"],
            "token":d["token"],
            "websocket_url":ws_url
        },
        "model":{
            "name":model["name"] if model else "",
            "provider":model["provider"] if model else "",
            "api_url":model["api_url"] if model else "",
            "model_name":model["model_name"] if model else ""
        },
        "role":{
            "name":role["name"] if role else "",
            "description":role["description"] if role else "",
            "system_prompt":role["system_prompt"] if role else "",
            "voice_setting":role.get("voice_setting") if role else "",
            "eye_setting":role.get("eye_setting") if role else "",
            "language_setting":role.get("language_setting") if role else ""
        },
        "firmware":{
            "package_name":firmware["name"] if firmware else "",
            "version":firmware["version"] if firmware else "",
            "chip":firmware["chip"] if firmware else d["chip"]
        }
    }

    filename=f"redapple_config_u{uid}_d{device_db_id}_{secrets.token_hex(6)}.json"
    path=CONFIG_UPLOAD / filename
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2), encoding="utf-8")

    ex("insert into device_configs(user_id,device_db_id,config_json,config_path) values(?,?,?,?)",(uid,device_db_id,json.dumps(config,ensure_ascii=False),str(path)))
    log(uid,"firmware","生成设备固件配置："+d["device_id"])
    return {"ok":True,"config":config,"path":str(path)}



@app.post("/firmware/package")
def fw_pkg(request: Request, name:str=Form(...), chip:str=Form("esp32s3"), version:str=Form("v1.0.0"), description:str=Form("")):
    u=need(request); 
    if not u: return RedirectResponse("/login",302)
    ex("insert into firmware_packages(user_id,name,chip,version,description) values(?,?,?,?,?)",(u["id"],name,chip,version,description))
    return RedirectResponse("/firmware",302)

@app.post("/firmware/upload")
def fw_upload(request: Request, package_id:int=Form(...), label:str=Form(...), flash_address:str=Form(...), firmware_file:UploadFile=File(...)):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    p=q1("select * from firmware_packages where id=? and user_id=?",(package_id,u["id"]))
    if not p: return JSONResponse({"ok":False,"error":"无权限"})
    suffix=Path(firmware_file.filename).suffix or ".bin"
    path=UPLOAD / f"u{u['id']}_p{package_id}_{secrets.token_hex(8)}{suffix}"
    with path.open("wb") as f: shutil.copyfileobj(firmware_file.file, f)
    ex("insert into firmware_files(package_id,label,flash_address,file_path,original_filename) values(?,?,?,?,?)",(package_id,label,flash_address,str(path),firmware_file.filename))
    return RedirectResponse("/firmware",302)

@app.post("/firmware/flash")
def fw_flash(request: Request, device_db_id:int=Form(...), package_id:int=Form(...), port:str=Form(...), baud:str=Form("460800"), erase_first:int=Form(0)):
    u=need(request)
    if not u: return JSONResponse({"ok":False,"output":"未登录"})
    if os.environ.get("DISABLE_FLASH", "0") == "1":
        return JSONResponse({
            "ok": False,
            "output": "当前部署环境已禁用本地串口烧录。云端网站无法访问用户电脑 USB 串口，请使用本地烧录助手或在连接开发板的本机运行。"
        })
    d=q1("select * from devices where id=? and user_id=?",(device_db_id,u["id"]))
    p=q1("select * from firmware_packages where id=? and user_id=?",(package_id,u["id"]))
    fs=qa("select * from firmware_files where package_id=? order by id",(package_id,))
    if not d or not p or not fs: return JSONResponse({"ok":False,"output":"设备、固件包或文件不存在"})
    latest_cfg=q1("select * from device_configs where user_id=? and device_db_id=? order by id desc limit 1",(u["id"],device_db_id))
    cfg_note = "已找到最近生成的设备配置：" + latest_cfg["config_path"] if latest_cfg else "未找到该设备最近生成的配置。建议先点击“生成固件配置”。"
    chip=d["chip"] or p["chip"] or "esp32s3"
    cmds=[]
    if erase_first: cmds.append([sys.executable,"-m","esptool","--chip",chip,"--port",port,"--baud",baud,"erase_flash"])
    write=[sys.executable,"-m","esptool","--chip",chip,"--port",port,"--baud",baud,"write_flash","-z"]
    for f in fs: write += [f["flash_address"], f["file_path"]]
    cmds.append(write)
    out=[cfg_note]; ok=True
    for cmd in cmds:
        out.append(">>> "+" ".join(cmd))
        try:
            r=subprocess.run(cmd,cwd=str(BASE),capture_output=True,text=True,timeout=300)
            out += [r.stdout,r.stderr]
            if r.returncode != 0: ok=False; break
        except Exception as e:
            ok=False; out.append(str(e)); break
    log(u["id"],"firmware",f"烧录 {d['device_id']} -> {'成功' if ok else '失败'}")
    return JSONResponse({"ok":ok,"output":"\n".join(out)})

async def call_model(uid, msg):
    m=q1("select * from models where user_id=? order by is_default desc,id desc limit 1",(uid,))
    r=q1("select * from roles where user_id=? order by is_default desc,id desc limit 1",(uid,))
    if not m: raise Exception("尚未配置模型")
    if not r: raise Exception("尚未配置角色")
    api=(m["api_url"] or "").rstrip("/")
    model=m["model_name"]; key = m["api_key"] or ""
    if (m["provider"] or "") == "DeepSeek":
        key = key or os.environ.get("DEEPSEEK_API_KEY", "")
    if not key and "ollama" in (m["provider"] or "").lower():
        key = "ollama"
    sys_prompt = (
        (r["system_prompt"] or "")
        + f"\n\n当前角色设备表现设置：声音={r.get('voice_setting') or '温柔女声'}；眼睛={r.get('eye_setting') or '自然眨眼'}；语言={r.get('language_setting') or '中文'}。"
        + "请根据语言设置调整回答语言；声音和眼睛设置主要用于设备端表现，不需要在回答中主动说明。"
    )
    url = api if api.endswith("/chat/completions") else api + "/chat/completions"
    headers={"Content-Type":"application/json","Authorization":"Bearer "+key}
    payload={"model":model,"messages":[{"role":"system","content":sys_prompt},{"role":"user","content":msg}],"stream":False,"temperature":0.7}
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        resp=await client.post(url,headers=headers,json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

@app.get("/chat")
def chat(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    msgs=qa("select * from chats where user_id=? order by id desc limit 50",(u["id"],))
    msgs=list(reversed(msgs))
    divs="".join([f"<div class='msg {'user' if m['role']=='user' else 'bot'}'>{m['content']}</div>" for m in msgs])
    body=f"""<div class='panel'><div class='chat' id='chat'>{divs}</div><div class='send'><input id='inp' placeholder='请输入消息'><button onclick='send()'>发送</button></div></div><script>
    async function send(){{let i=document.getElementById('inp'),c=document.getElementById('chat'),t=i.value.trim();if(!t)return;c.innerHTML+=`<div class='msg user'>${{esc(t)}}</div>`;i.value='';let r=await fetch('/api/chat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{message:t}})}});let d=await r.json();c.innerHTML+=`<div class='msg bot'>${{esc(d.reply||d.error)}}</div>`;c.scrollTop=c.scrollHeight}}
    </script>"""
    return page("聊天测试","chat",u,body,"使用当前默认模型和默认角色测试回复")

@app.post("/api/chat")
async def api_chat(request: Request):
    u=need(request)
    if not u: return JSONResponse({"error":"未登录"},401)
    data=await request.json()
    msg=(data.get("message") or "").strip()
    if not msg: return {"reply":"请输入消息"}
    ex("insert into chats(user_id,role,content) values(?,?,?)",(u["id"],"user",msg))
    try: reply=await call_model(u["id"],msg)
    except Exception as e: reply="调用模型失败："+str(e)
    ex("insert into chats(user_id,role,content) values(?,?,?)",(u["id"],"assistant",reply))
    return {"reply":reply}

@app.get("/logs")
def logs_page(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    rows = qa("select * from logs where user_id=? order by id desc limit 300", (u["id"],))
    trs = "".join([
        f"<tr><td>{r['created_at']}</td><td><span class='badge'>{r['level']}</span></td><td>{r['module']}</td><td>{r['content']}</td></tr>"
        for r in rows
    ])
    body = f"""
    <div class='panel'>
      <h3>日志中心</h3>
      <table>
        <tr><th>时间</th><th>级别</th><th>模块</th><th>内容</th></tr>
        {trs}
      </table>
    </div>
    """
    return page("日志中心","logs",u,body,"查看系统、设备、模型、角色和固件操作日志")


@app.get("/profile")
def profile_page(request: Request):
    u=need(request)
    if not u: return RedirectResponse("/login",302)
    uid = u["id"]
    profiles = qa("select * from user_profiles where user_id=? order by id desc limit 10", (uid,))
    msg_count = q1("select count(*) as c from chats where user_id=?", (uid,))["c"]

    latest = profiles[0]["profile_text"] if profiles else "暂无用户画像。请先产生一些聊天记录，再点击生成。"
    rows = "".join([
        f"<tr><td>{p['created_at']}</td><td>{p['source_message_count']}</td><td>{p['profile_text'][:160]}...</td></tr>"
        for p in profiles
    ])

    body = f"""
    <div class='panel'>
      <h3>生成用户画像</h3>
      <p class='muted'>当前聊天记录数量：{msg_count} 条。系统会根据当前用户的聊天记录，调用默认模型生成画像。</p>
      <button onclick='genProfile()'>根据聊天记录生成用户画像</button>
      <pre class='profile-box' id='profileBox'>{latest}</pre>
    </div>

    <div class='panel'>
      <h3>历史画像</h3>
      <table>
        <tr><th>生成时间</th><th>使用记录数</th><th>画像摘要</th></tr>
        {rows}
      </table>
    </div>

    <script>
    async function genProfile(){{
      let box=document.getElementById('profileBox');
      box.textContent='正在生成用户画像，请稍候...';
      let r=await fetch('/api/profile/generate',{{method:'POST'}});
      let d=await r.json();
      if(d.ok){{box.textContent=d.profile; alert('用户画像生成成功');}}
      else{{box.textContent=d.error||'生成失败'; alert(d.error||'生成失败');}}
    }}
    </script>
    """
    return page("用户画像","profile",u,body,"根据聊天记录生成用户兴趣、偏好、场景和服务建议")


@app.post("/api/profile/generate")
async def generate_profile(request: Request):
    u=need(request)
    if not u: return JSONResponse({"ok":False,"error":"未登录"},401)
    uid = u["id"]

    msgs = qa("select role,content,created_at from chats where user_id=? order by id desc limit 80", (uid,))
    msgs = list(reversed(msgs))
    if not msgs:
        return {"ok":False, "error":"暂无聊天记录，无法生成用户画像。"}

    lines = []
    for m in msgs:
        role = "用户" if m["role"] == "user" else "助手"
        content = (m["content"] or "").replace("\\n", " ").strip()
        if content:
            lines.append(f"{role}：{content}")
    transcript = "\\n".join(lines)

    prompt = (
        "请根据以下聊天记录生成一份用户画像。要求：\\n"
        "1. 使用中文；\\n"
        "2. 只基于聊天记录，不要编造；\\n"
        "3. 不要做疾病诊断、政治倾向、宗教身份等敏感推断；\\n"
        "4. 输出包含：总体画像、主要兴趣、表达风格、互动偏好、可能使用场景、后续服务建议。\\n\\n"
        "聊天记录：\\n" + transcript
    )

    try:
        profile = await call_model(uid, prompt)
        ex("insert into user_profiles(user_id,profile_text,source_message_count) values(?,?,?)", (uid, profile, len(msgs)))
        log(uid, "profile", f"生成用户画像，使用聊天记录 {len(msgs)} 条")
        return {"ok":True, "profile":profile}
    except Exception as e:
        log(uid, "profile", "生成用户画像失败："+str(e), "ERROR")
        return {"ok":False, "error":"生成用户画像失败："+str(e)}


@app.websocket("/xiaozhi/v1/")
async def ws(websocket: WebSocket):
    await websocket.accept()
    auth=websocket.headers.get("authorization","")
    token=auth.replace("Bearer","").strip()
    d=q1("select * from devices where token=?",(token,))
    if not d:
        await websocket.send_json({"type":"error","message":"invalid token"})
        await websocket.close(); return
    try:
        while True:
            txt=await websocket.receive_text()
            if '"hello"' in txt:
                await websocket.send_json({"type":"hello","transport":"websocket","session_id":secrets.token_hex(16)})
            else:
                await websocket.send_json({"type":"tts","state":"sentence_start","text":"红苹果AI已收到设备消息。"})
    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    if "--init-db" in sys.argv:
        init_db()
        print("数据库初始化完成：", DB)
