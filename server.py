# -*- coding: utf-8 -*-
"""
课表总览管理 - 本地后端
数据存在同目录 data.db (SQLite)。
"""
import os
import re
import json
import gzip
import hmac
import html
import time
import sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, g, send_from_directory, abort, Response, redirect, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data.db")
SOURCES_DIR = os.path.join(BASE_DIR, "sources")
PASSWORD_FILE = os.path.join(BASE_DIR, "password.txt")
KEY_FILE = os.path.join(BASE_DIR, ".session_key")

DEFAULT_PASSWORD = "change-me"  # 首次使用请设置 password.txt 或修改这里


def _read_or_make_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            k = f.read().strip()
        if k:
            return k
    k = os.urandom(24).hex()
    with open(KEY_FILE, "w") as f:
        f.write(k)
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    return k


def get_password():
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE) as f:
            p = f.read().strip()
        if p:
            return p
    return DEFAULT_PASSWORD


app = Flask(__name__, static_folder=None)
app.secret_key = _read_or_make_key()
app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_NAME"] = "sched_sess"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = False  # 局域网 HTTP 也要能收会话；公网 HTTPS 仍会发送

_fails = {}


@app.before_request
def gate():
    """登录后按身份放行；学号身份只读，整体密钥身份可维护数据。"""
    if request.path in ("/login", "/logout", "/api/health", "/calendar.ics"):
        return
    if not session.get("auth"):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "未登录"}), 401
        return redirect("/login")
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and session.get("role") == "viewer":
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "只读身份不能修改，请让负责人操作"}), 403
        return redirect("/")


def current_user():
    return {
        "name": session.get("name") or "负责人",
        "role": session.get("role") or "admin",
        "no": session.get("no") or "",
    }


LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>课表总览 · 登录</title><script>try{history.scrollRestoration="manual"}catch(e){}</script>
<style>
:root{--bg:#faf9f7;--card:#fff;--fg:#1c1c1e;--muted:#767676;--bd:#e2e0dc;--err:#b23a2c}
@media (prefers-color-scheme: dark){:root{--bg:#0f0f10;--card:#161617;--fg:#ededed;--muted:#8a8a8a;--bd:#2b2b2e;--err:#e07a6c}}
*{box-sizing:border-box}
html{overflow-y:scroll;scrollbar-gutter:stable;height:100%}
body{margin:0;min-height:100vh;min-height:100svh;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;padding:clamp(64px,12vh,120px) 16px 32px;padding-top:clamp(64px,12svh,120px);background:var(--bg);color:var(--fg);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
form{width:min(340px,86vw);background:var(--card);border:1px solid var(--bd);border-radius:2px;padding:26px 24px}
h1{font-size:15px;font-weight:600;margin:0 0 6px;letter-spacing:.02em}
p{font-size:12px;color:var(--muted);margin:0 0 16px;line-height:1.7}
label{display:block;font-size:11px;color:var(--muted);margin:12px 0 5px}
.label-row{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:12px 0 5px}
.label-row label{margin:0}
.caps{font-size:10px;color:var(--muted);min-width:44px;text-align:right;letter-spacing:.02em;white-space:nowrap}
.caps.on{color:var(--fg);font-weight:600}
input{width:100%;padding:9px 10px;font-size:13px;line-height:1.4;border:1px solid var(--bd);border-radius:2px;background:transparent;color:var(--fg);font-family:inherit;outline:none}
input:focus{border-color:var(--fg)}
.pw-wrap{position:relative}
.pw-wrap input{padding-right:52px}
.eye{position:absolute;right:1px;top:1px;bottom:1px;width:46px;margin:0;padding:0;border:0;border-left:1px solid var(--bd);border-radius:0;background:transparent;color:var(--muted);font-size:11px;font-family:inherit;cursor:pointer}
.eye:hover{color:var(--fg)}
button[type=submit]{margin-top:16px;width:100%;padding:9px;font-size:13px;border:1px solid var(--fg);border-radius:2px;background:var(--fg);color:var(--card);cursor:pointer;font-family:inherit}
.err{color:var(--err);font-size:12px;line-height:1.5;min-height:1.5em;margin-top:10px}
.err.ok{color:#2e6b4f}
.err.hint{color:var(--muted)}

</style></head>
<body><form method="post" action="/login">
<h1>课表总览</h1>
<p>只填学号：看课表，只读。<br>只填整体密钥：负责人登录。<br>学号 + 整体密钥：对应管理员登录。</p>
<label for="no">学号（查看用，可留空）</label>
<input id="no" name="no" type="text" placeholder="例如 20251106221" autocomplete="username">
<div class="label-row"><label for="pw">整体密钥（维护用，可留空）</label><span class="caps" id="caps">小写</span></div>
<div class="pw-wrap"><input id="pw" name="pw" type="password" placeholder="整体密钥（只读可留空）" autocomplete="current-password"><button type="button" class="eye" id="eye" aria-label="显示密码">显示</button></div>
<button type="submit">进入</button>
<div class="err" id="err">ERR</div>
</form>
<script>
(function(){
  var no=document.getElementById('no'), pw=document.getElementById('pw');
  var eye=document.getElementById('eye'), caps=document.getElementById('caps');
  function updateCaps(e){var on=!!(e.getModifierState&&e.getModifierState('CapsLock')); caps.textContent=on?'大写锁定':'小写'; caps.classList.toggle('on',on);}
  ['keydown','keyup','focus'].forEach(function(ev){pw.addEventListener(ev,updateCaps);});
  no.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();pw.focus();status.textContent='已到密码框：可留空按 Enter 进入';status.classList.remove('ok');status.classList.add('hint');}});
  pw.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();var f=document.querySelector('form');if(f.requestSubmit){f.requestSubmit();}else{f.submit();}}});
  eye.addEventListener('click',function(){var showing=pw.type==='text';pw.type=showing?'password':'text';eye.textContent=showing?'显示':'隐藏';eye.setAttribute('aria-label',showing?'显示密码':'隐藏密码');pw.focus();});
  var form=document.querySelector('form'), status=document.getElementById('err'), submit=form.querySelector('button[type=submit]');
  form.addEventListener('submit',function(e){
    e.preventDefault();
    status.textContent='登录中…'; status.classList.remove('ok'); status.classList.add('hint'); submit.disabled=true;
    fetch('/login',{method:'POST',headers:{'X-Requested-With':'fetch'},body:new FormData(form)})
      .then(function(r){return r.json();})
      .then(function(j){
        if(j&&j.ok){
          status.textContent=(j.role==='viewer'?'只读登录成功，正在进入…':'登录成功，正在进入…');
          status.classList.remove('hint'); status.classList.add('ok');
          setTimeout(function(){location.replace(j.redirect||'/');},250);
        }else{
          status.textContent=(j&&j.error)||'登录失败';
          status.classList.remove('ok'); status.classList.remove('hint');
          submit.disabled=false;
          if(j&&j.code!=='1'){no.focus();}else{pw.focus();}
        }
      })
      .catch(function(){status.textContent='网络错误，请重试';status.classList.remove('ok');status.classList.remove('hint');submit.disabled=false;});
  });
  setTimeout(function(){try{no.focus({preventScroll:true});}catch(e){no.focus();}},0);
})();
</script></body></html>"""


@app.get("/login")
def login_page():
    if session.get("auth") and request.headers.get("CF-Connecting-IP"):
        return redirect("/")
    errs = {"1": "整体密钥不对", "2": "学号不在课表名单里", "3": "请填学号或整体密钥"}
    code = request.args.get("e") or ""
    err = '%s' % errs.get(code, "") if code else ""
    r = Response(LOGIN_HTML.replace("ERR", err), mimetype="text/html")
    r.headers["Cache-Control"] = "no-store"
    return r


@app.post("/login")
def login_post():
    ip = request.headers.get("CF-Connecting-IP") or request.remote_addr or "-"
    wants_json = request.headers.get("X-Requested-With") == "fetch"
    cnt, ts = _fails.get(ip, (0, 0))
    if cnt >= 6 and time.time() - ts < 600:
        if wants_json:
            return jsonify({"ok": False, "error": "连续失败已锁定，10 分钟后再试"}), 429
        return redirect("/login?e=1")
    no = (request.form.get("no") or "").strip()
    pw = (request.form.get("pw") or "").strip()
    role, name = "", ""
    code = ""
    if pw and not hmac.compare_digest(pw, get_password()):
        code = "1"
    elif no:
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        p = c.execute("SELECT name, student_no FROM persons WHERE student_no = ? ORDER BY id DESC LIMIT 1", (no,)).fetchone()
        c.close()
        if not p:
            code = "2"
        else:
            name, no = p["name"], p["student_no"]
            role = "admin" if pw else "viewer"
    elif pw:
        role, name = "admin", "负责人"
    else:
        code = "3"
    if role:
        _fails.pop(ip, None)
        session.permanent = True
        session["auth"] = True
        session["role"] = role
        session["name"] = name
        session["no"] = no
        if wants_json:
            return jsonify({"ok": True, "redirect": "/", "role": role, "name": name})
        return redirect("/")
    _fails[ip] = (cnt + 1 if time.time() - ts < 600 else 1, time.time())
    notes = {"1": "整体密钥不对", "2": "学号不在课表名单里", "3": "请填学号或整体密钥"}
    if wants_json:
        return jsonify({"ok": False, "error": notes.get(code, "登录失败"), "code": code})
    return redirect("/login?e=" + (code or "1"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.after_request
def gzip_small(resp):
    """公网走 Cloudflare 隧道时字节数直接决定打开速度，文本响应一律压一下。"""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    enc = (request.headers.get("Accept-Encoding") or "").lower()
    if "gzip" not in enc or resp.direct_passthrough or resp.status_code != 200:
        return resp
    if resp.headers.get("Content-Encoding"):
        return resp
    ctype = (resp.content_type or "")
    if not (ctype.startswith("application/json") or ctype.startswith("text/")
            or ctype.startswith("application/javascript")):
        return resp
    data = resp.get_data()
    if len(data) < 1024:
        return resp
    gz = gzip.compress(data, 6)
    if len(gz) >= len(data) - 200:
        return resp
    resp.set_data(gz)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(gz))
    resp.headers["Vary"] = "Accept-Encoding"
    return resp

SLOTS = [
    {"id": 0, "label": "第1-2节", "time": "10:00-11:40"},
    {"id": 1, "label": "第3-4节", "time": "12:05-13:45"},
    {"id": 2, "label": "第5-6节", "time": "15:30-17:10"},
    {"id": 3, "label": "第7-8节", "time": "17:35-19:15"},
    {"id": 4, "label": "第9-10节", "time": "19:35-21:15"},
]

def _small_to_slot(n):
    if n in (1, 2): return 0
    if n in (3, 4): return 1
    if n in (5, 6): return 2
    if n in (7, 8): return 3
    if n in (9, 10): return 4
    return None

DAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}

# ---------- 数据库 ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        student_no TEXT,
        source_file TEXT,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        day INTEGER NOT NULL,
        slot INTEGER NOT NULL,
        weeks TEXT NOT NULL,
        location TEXT
    );
    CREATE TABLE IF NOT EXISTS semesters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        weeks INTEGER NOT NULL DEFAULT 20,
        created_at TEXT NOT NULL
    );
    """)
    # 兼容旧库：补列
    for col, ddl in [("student_no", "TEXT"), ("source_file", "TEXT"), ("cls", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE persons ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    _migrate_semesters(conn)
    conn.commit()
    conn.close()


# 旧库升级：给 persons 加 semester_id，并把 name 的唯一约束改成 (name, semester_id)
# 这样一个名字可以同时存在于秋季和春季两个学期里
def _migrate_semesters(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(persons)").fetchall()]
    if "semester_id" in cols:
        return
    sid = _ensure_default_semester(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
    CREATE TABLE persons_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        student_no TEXT,
        source_file TEXT,
        created_at TEXT NOT NULL,
        semester_id INTEGER REFERENCES semesters(id) ON DELETE CASCADE,
        UNIQUE(name, semester_id)
    );
    """)
    conn.execute(
        "INSERT INTO persons_new(id, name, student_no, source_file, created_at, semester_id) "
        "SELECT id, name, student_no, source_file, created_at, ? FROM persons", (sid,))
    conn.executescript("""
    DROP TABLE persons;
    ALTER TABLE persons_new RENAME TO persons;
    """)
    conn.execute("PRAGMA foreign_keys = ON")


def _ensure_default_semester(conn):
    """库里没有学期时，造一个默认学期（当前这学期）"""
    row = conn.execute("SELECT id FROM semesters ORDER BY start_date DESC LIMIT 1").fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO semesters(name, start_date, weeks, created_at) VALUES(?,?,?,?)",
        ("2026 秋", "2026-09-14", 20, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    return cur.lastrowid


def _latest_semester_id(db):
    row = db.execute(
        "SELECT id FROM semesters ORDER BY start_date DESC, id DESC LIMIT 1").fetchone()
    if row:
        return row[0]
    return _ensure_default_semester(db)


def _resolve_semester(db, sid=None):
    """取学期记录：优先请求里指定的 id，取不到就回落到最新学期"""
    if sid:
        row = db.execute(
            "SELECT id, name, start_date, weeks FROM semesters WHERE id=?", (sid,)).fetchone()
        if row:
            return dict(row)
    row = db.execute(
        "SELECT id, name, start_date, weeks FROM semesters ORDER BY start_date DESC, id DESC LIMIT 1").fetchone()
    if row:
        return dict(row)
    _ensure_default_semester(db)
    row = db.execute(
        "SELECT id, name, start_date, weeks FROM semesters ORDER BY start_date DESC, id DESC LIMIT 1").fetchone()
    return dict(row)


# ---------- 课表解析 ----------
# 主表格时间段: 1-16周 二[3-4] JX1#310(144)
# 也有: 1-16周(双) 五[5-6] ...
# 也有: 1,3-7,9-16周 四[5-6] ...
TIME_RE = re.compile(
    r"(\d+(?:[-,]\d+)*周)\s*"
    r"(?:\((单|双)\))?\s*"
    r"([一二三四五六日])\[(\d+)-(\d+)\]\s*"
    r"([^；;]*)"
)

# 实验课表格时间: 四[3-4节](05周)
LAB_TIME_RE = re.compile(
    r"([一二三四五六日])\[(\d+)-(\d+)节\]\((\d+)周\)"
)

def parse_week_range(s):
    s = s.replace("周", "").strip()
    out = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out

def clean_course_name(raw):
    return re.sub(r"^\[[^\]]*\]", "", raw).strip()

def extract_meta(html_text):
    """从头部提取姓名和学号"""
    # 去掉标签和 &ensp;
    head = re.sub(r"<[^>]+>", " ", html_text[:3000])
    head = head.replace("&ensp;", " ").replace("&nbsp;", " ")
    name = re.search(r"姓\s*名[：:]\s*(\S+)", head)
    sno = re.search(r"学\s*号[：:]\s*(\S+)", head)
    return (
        name.group(1).strip() if name else None,
        sno.group(1).strip() if sno else None,
    )

def parse_schedule_html(html_text):
    """返回 [(course_name, day, slot, weeks:list, location)]"""
    results = []
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html_text, re.S)

    # ---- 主课程表（列数 >=11 的那个）----
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        for row in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            tds = [re.sub(r"<[^>]+>", "", x).replace("&ensp;", " ").strip() for x in tds]
            if len(tds) < 11:
                continue
            course_raw = tds[2]
            time_raw = tds[10]
            if not course_raw or not time_raw or "课程" in course_raw or "上课时间" in time_raw:
                continue
            course_name = clean_course_name(course_raw)
            for m in TIME_RE.finditer(time_raw):
                week_str, odd_even, day_cn, s1, s2, loc = m.groups()
                weeks = parse_week_range(week_str)
                if odd_even == "单":
                    weeks = {w for w in weeks if w % 2 == 1}
                elif odd_even == "双":
                    weeks = {w for w in weeks if w % 2 == 0}
                day = DAY_MAP.get(day_cn)
                if day is None:
                    continue
                a, b = int(s1), int(s2)
                slots = set()
                for n in range(a, b + 1):
                    sl = _small_to_slot(n)
                    if sl is not None:
                        slots.add(sl)
                loc = (loc or "").strip().rstrip("；;").strip()
                for sl in slots:
                    results.append((course_name, day, sl, sorted(weeks), loc))

    # ---- 实验课表（8 列，第6列时间）----
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        for row in rows:
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            tds = [re.sub(r"<[^>]+>", "", x).replace("&ensp;", " ").strip() for x in tds]
            if len(tds) < 8:
                continue
            course_raw = tds[0]
            time_raw = tds[6]
            loc_raw = tds[7] if len(tds) > 7 else ""
            if not course_raw or not time_raw or "课程" in course_raw or "节次" in tds[0]:
                continue
            course_name = clean_course_name(course_raw)
            m = LAB_TIME_RE.search(time_raw)
            if not m:
                continue
            day_cn, s1, s2, week = m.groups()
            day = DAY_MAP.get(day_cn)
            if day is None:
                continue
            a, b = int(s1), int(s2)
            slots = set()
            for n in range(a, b + 1):
                sl = _small_to_slot(n)
                if sl is not None:
                    slots.add(sl)
            for sl in slots:
                results.append((course_name, day, sl, [int(week)], loc_raw.strip()))

    return results

# ---------- API ----------
# ---------- 学期管理 ----------
@app.route("/api/semesters", methods=["GET"])
def list_semesters():
    db = get_db()
    _resolve_semester(db)  # 保证库里至少有一个学期
    rows = db.execute(
        "SELECT s.id, s.name, s.start_date, s.weeks, s.created_at, "
        "(SELECT COUNT(*) FROM persons p WHERE p.semester_id = s.id) AS person_count "
        "FROM semesters s ORDER BY s.start_date DESC, s.id DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/semesters", methods=["POST"])
def create_semester():
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    start = (data.get("start_date") or "").strip()
    try:
        weeks = int(data.get("weeks") or 20)
    except (TypeError, ValueError):
        weeks = 20
    if not name:
        return jsonify({"ok": False, "error": "学期名称不能为空"}), 400
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return jsonify({"ok": False, "error": "开学日期请用 YYYY-MM-DD"}), 400
    d = d - timedelta(days=d.weekday())  # 对齐到当周周一
    weeks = max(1, min(30, weeks))
    db = get_db()
    if db.execute("SELECT id FROM semesters WHERE name=?", (name,)).fetchone():
        return jsonify({"ok": False, "error": "已有同名学期"}), 400
    cur = db.execute(
        "INSERT INTO semesters(name, start_date, weeks, created_at) VALUES(?,?,?,?)",
        (name, d.isoformat(), weeks, datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.commit()
    return jsonify({"ok": True, "semester": {
        "id": cur.lastrowid, "name": name, "start_date": d.isoformat(), "weeks": weeks,
        "person_count": 0}})


@app.route("/api/semesters/<int:sid>", methods=["PATCH", "POST"])
def update_semester(sid):
    data = request.get_json(silent=True) or request.form
    db = get_db()
    row = db.execute("SELECT id, name, start_date, weeks FROM semesters WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "学期不存在"}), 404
    name = (data.get("name") or row["name"]).strip()
    start = (data.get("start_date") or row["start_date"]).strip()
    try:
        weeks = int(data.get("weeks") or row["weeks"])
    except (TypeError, ValueError):
        weeks = row["weeks"]
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return jsonify({"ok": False, "error": "开学日期请用 YYYY-MM-DD"}), 400
    d = d - timedelta(days=d.weekday())
    weeks = max(1, min(30, weeks))
    db.execute("UPDATE semesters SET name=?, start_date=?, weeks=? WHERE id=?",
               (name, d.isoformat(), weeks, sid))
    db.commit()
    return jsonify({"ok": True, "semester": {
        "id": sid, "name": name, "start_date": d.isoformat(), "weeks": weeks}})


@app.route("/api/semesters/<int:sid>", methods=["DELETE"])
def delete_semester(sid):
    db = get_db()
    count = db.execute("SELECT COUNT(*) AS c FROM persons WHERE semester_id=?", (sid,)).fetchone()["c"]
    if count:
        return jsonify({"ok": False,
                        "error": "该学期里还有 %d 人的课表，先删掉人再删学期" % count}), 400
    db.execute("DELETE FROM semesters WHERE id=?", (sid,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/import", methods=["POST"])
def import_schedule():
    f = request.files.get("file")
    if f is None:
        return jsonify({"ok": False, "error": "请选择课表文件"}), 400

    raw = f.read()
    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            html_text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return jsonify({"ok": False, "error": "文件编码无法识别"}), 400

    # 自动识别姓名学号
    auto_name, student_no = extract_meta(html_text)
    name = (request.form.get("name") or "").strip() or auto_name
    if not name:
        return jsonify({"ok": False, "error": "无法从文件识别姓名，请手动填写"}), 400

    courses = parse_schedule_html(html_text)
    if not courses:
        return jsonify({"ok": False, "error": "未解析到任何带时间地点的课程"}), 400

    # 保存源文件: <姓名>_<学号>.html
    os.makedirs(SOURCES_DIR, exist_ok=True)
    sno = student_no or "unknown"
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
    source_filename = f"{safe_name}_{sno}.html"
    source_path = os.path.join(SOURCES_DIR, source_filename)
    with open(source_path, "wb") as out:
        out.write(raw)

    db = get_db()
    raw_sid = request.form.get("semester")
    try:
        sid = int(raw_sid) if raw_sid else None
    except (TypeError, ValueError):
        sid = None
    sem = _resolve_semester(db, sid)
    db.execute("DELETE FROM courses WHERE person_id IN (SELECT id FROM persons WHERE name=? AND semester_id=?)",
               (name, sem["id"]))
    db.execute("DELETE FROM persons WHERE name=? AND semester_id=?", (name, sem["id"]))
    cur = db.execute(
        "INSERT INTO persons(name, student_no, source_file, created_at, semester_id) VALUES(?,?,?,?,?)",
        (name, student_no, source_filename, datetime.now().strftime("%Y-%m-%d %H:%M"), sem["id"]),
    )
    pid = cur.lastrowid
    for c in courses:
        db.execute(
            "INSERT INTO courses(person_id, name, day, slot, weeks, location) VALUES(?,?,?,?,?,?)",
            (pid, c[0], c[1], c[2], json.dumps(c[3]), c[4]),
        )
    db.commit()
    return jsonify({
        "ok": True,
        "person_id": pid,
        "course_count": len(courses),
        "name": name,
        "student_no": student_no,
        "source_file": source_filename,
    })

@app.route("/api/persons", methods=["GET"])
def list_persons():
    db = get_db()
    sem = _resolve_semester(db, request.args.get("semester", type=int))
    rows = db.execute(
        "SELECT id, name, COALESCE(student_no,'') AS student_no, COALESCE(cls,'') AS cls, "
        "source_file, created_at, semester_id FROM persons "
        "WHERE semester_id=? ORDER BY id", (sem["id"],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/persons/<int:pid>", methods=["DELETE"])
def delete_person(pid):
    db = get_db()
    # 同时删源文件
    row = db.execute("SELECT source_file FROM persons WHERE id=?", (pid,)).fetchone()
    if row and row["source_file"]:
        try:
            os.remove(os.path.join(SOURCES_DIR, row["source_file"]))
        except OSError:
            pass
    db.execute("DELETE FROM courses WHERE person_id=?", (pid,))
    db.execute("DELETE FROM persons WHERE id=?", (pid,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/source/<int:pid>")
def download_source(pid):
    db = get_db()
    row = db.execute("SELECT name, source_file FROM persons WHERE id=?", (pid,)).fetchone()
    if not row or not row["source_file"]:
        abort(404)
    return send_from_directory(SOURCES_DIR, row["source_file"], as_attachment=True)

@app.route("/api/schedule")
def get_schedule():
    week = request.args.get("week", type=int) or 1
    db = get_db()
    sem = _resolve_semester(db, request.args.get("semester", type=int))
    persons = db.execute(
        "SELECT id, name FROM persons WHERE semester_id=? ORDER BY id", (sem["id"],)).fetchall()
    # 一次查出全部课程再按人分组，避免每人一条查询（原来的 N+1）
    rows = db.execute(
        "SELECT c.person_id, c.name, c.day, c.slot, c.weeks, c.location FROM courses c "
        "JOIN persons p ON p.id = c.person_id WHERE p.semester_id=? "
        "ORDER BY c.person_id, c.day, c.slot", (sem["id"],)).fetchall()
    by_pid = {}
    for r in rows:
        if week in json.loads(r["weeks"]):
            by_pid.setdefault(r["person_id"], []).append({
                "name": r["name"],
                "day": r["day"],
                "slot": r["slot"],
                "location": r["location"],
            })
    out = [{"id": p["id"], "name": p["name"], "courses": by_pid.get(p["id"], [])} for p in persons]
    return jsonify({"week": week, "semester": sem, "slots": SLOTS,
                    "days": ["周一","周二","周三","周四","周五","周六","周日"], "persons": out})

# ---------- 导出（给 AI / 脚本读） ----------
DAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def _week_monday(week, sem=None):
    """第 1 周周一 = 学期的开学日；没有学期就回落到老规则 9 月 14 日"""
    if sem and sem.get("start_date"):
        y, m, d = [int(x) for x in sem["start_date"].split("-")]
        return date(y, m, d) + timedelta(days=(week - 1) * 7)
    today = date.today()
    year = today.year if today.month >= 9 else today.year - 1
    return date(year, 9, 14) + timedelta(days=(week - 1) * 7)

def _week_data(week, sem):
    db = get_db()
    persons = [dict(r) for r in db.execute(
        "SELECT id, name, student_no FROM persons WHERE semester_id=? ORDER BY id",
        (sem["id"],)).fetchall()]
    rows = db.execute(
        "SELECT c.person_id, c.name, c.day, c.slot, c.weeks, c.location FROM courses c "
        "JOIN persons p ON p.id=c.person_id WHERE p.semester_id=? "
        "ORDER BY c.person_id, c.day, c.slot", (sem["id"],)).fetchall()
    by_pid = {}
    for r in rows:
        if week not in json.loads(r["weeks"]):
            continue
        by_pid.setdefault(r["person_id"], []).append({
            "course": r["name"], "day": r["day"], "slot": r["slot"],
            "location": (r["location"] or "").strip(),
        })
    return persons, by_pid

def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ").strip()

def _md_export(week, sem):
    persons, by_pid = _week_data(week, sem)
    mon = _week_monday(week, sem)
    sun = mon + timedelta(days=6)
    has_class = [p for p in persons if by_pid.get(p["id"])]
    total = sum(len(v) for v in by_pid.values())
    L = []
    L.append("# 课表总览 · %s 第 %d 周（%d-%02d-%02d 至 %d-%02d-%02d）" % (
        sem["name"], week, mon.year, mon.month, mon.day, sun.year, sun.month, sun.day))
    L.append("")
    L.append("> 这份纯文本给 AI 或脚本直接读，不用打开网页。先看「一、怎么读」，"
             "再按需要看「三、按时段」「四、按人」「五、空闲速查」。")
    L.append("> 来源：局域网课表工具 http://localhost:17860/ ；"
             "导出时间 %s（UTC+6，中国新疆）；样本 %d 人，本周有课 %d 人，共 %d 个课次。" % (
        datetime.now().strftime("%Y-%m-%d %H:%M"), len(persons), len(has_class), total))
    L.append("")
    L.append("## 一、怎么读")
    L.append("- 本文件回答「谁在什么时间、哪间教室上课」。两小节合并成一个时段，全周 5 个时段，编号 S1~S5。")
    L.append("- 教室写法 `JX1#315(80)` = 教学 JX1 楼 315 室，括号内是容量；"
             "`实验-HGY#A220` 是实验楼；`博北区训练馆(1000)` 是场馆。")
    L.append("- 「空闲」指该时段没有课，可以直接约人。同一时段多人同课同教室是正常合班。")
    L.append("- 一个课次 = 一个人在一个时段的一门课；同一天同一人两门课会记两条。")
    L.append("")
    L.append("## 二、时段定义")
    L.append("")
    L.append("| 编号 | 节次 | 起止时间 |")
    L.append("|---|---|---|")
    for s in SLOTS:
        L.append("| S%d | %s | %s |" % (s["id"] + 1, s["label"], s["time"]))
    L.append("")
    L.append("## 三、按时段（本周全部课次）")
    L.append("")
    L.append("| 星期 | 日期 | 时段 | 时间 | 同学 | 课程 | 教室 |")
    L.append("|---|---|---|---|---|---|---|")
    order = []
    for d in range(7):
        for s in SLOTS:
            for p in persons:
                for c in by_pid.get(p["id"], []):
                    if c["day"] == d and c["slot"] == s["id"]:
                        order.append((d, s["id"], p, c))
    if not order:
        L.append("| - | - | - | - | - | 本周无任何课次 | - |")
    for d, sid, p, c in order:
        day_date = mon + timedelta(days=d)
        L.append("| %s | %d/%d | S%d | %s | %s | %s | %s |" % (
            DAY_CN[d], day_date.month, day_date.day, sid + 1,
            SLOTS[sid]["time"], _md_cell(p["name"]), _md_cell(c["course"]), _md_cell(c["location"])))
    L.append("")
    L.append("## 四、按人（整周安排）")
    L.append("")
    for p in persons:
        items = by_pid.get(p["id"], [])
        sno = (" · 学号 %s" % p["student_no"]) if p.get("student_no") else ""
        if not items:
            L.append("### %s%s · 本周无课" % (p["name"], sno))
            L.append("")
            continue
        L.append("### %s%s · %d 个课次" % (p["name"], sno, len(items)))
        for c in items:
            day_date = mon + timedelta(days=c["day"])
            L.append("- %s %d/%d · S%d %s · %s · %s" % (
                DAY_CN[c["day"]], day_date.month, day_date.day, c["slot"] + 1,
                SLOTS[c["slot"]]["time"], c["course"], c["location"] or "（未写教室）"))
        L.append("")
    L.append("## 五、空闲速查（按时段）")
    L.append("")
    for d in range(7):
        for s in SLOTS:
            busy_ids = {p["id"] for p in persons
                        if any(c["day"] == d and c["slot"] == s["id"] for c in by_pid.get(p["id"], []))}
            free = [p["name"] for p in persons if p["id"] not in busy_ids]
            day_date = mon + timedelta(days=d)
            if len(free) == len(persons) and persons:
                tail = "全员空闲"
            elif not free:
                tail = "全员有课"
            else:
                tail = "空闲 %d 人：%s" % (len(free), "、".join(free))
            L.append("- %s %d/%d · S%d %s · %s" % (
                DAY_CN[d], day_date.month, day_date.day, s["id"] + 1,
                SLOTS[s["id"]]["time"], tail))
    L.append("")
    L.append("## 六、结构化数据")
    L.append("")
    L.append("同一份数据还有 JSON 版：把本地址的 `format=md` 换成 `format=json` 即可，"
             "字段为 schema/week/date_range/timezone/generated_at/slots/days/persons/free。")
    L.append("")
    return "\n".join(L)

def _json_export(week, sem):
    persons, by_pid = _week_data(week, sem)
    mon = _week_monday(week, sem)
    sun = mon + timedelta(days=6)
    persons_out = []
    for p in persons:
        items = by_pid.get(p["id"], [])
        persons_out.append({
            "name": p["name"],
            "student_no": p.get("student_no"),
            "courses": [{
                "day": c["day"],
                "day_cn": DAY_CN[c["day"]],
                "date": (mon + timedelta(days=c["day"])).isoformat(),
                "slot": c["slot"] + 1,
                "slot_label": SLOTS[c["slot"]]["label"],
                "time": SLOTS[c["slot"]]["time"],
                "course": c["course"],
                "location": c["location"],
            } for c in items],
        })
    free = []
    for d in range(7):
        for s in SLOTS:
            busy_ids = {p["id"] for p in persons
                        if any(c["day"] == d and c["slot"] == s["id"] for c in by_pid.get(p["id"], []))}
            free.append({
                "day": d, "day_cn": DAY_CN[d],
                "date": (mon + timedelta(days=d)).isoformat(),
                "slot": s["id"] + 1, "slot_label": s["label"], "time": s["time"],
                "persons": [p["name"] for p in persons if p["id"] not in busy_ids],
            })
    return {
        "schema": "timetable/v1",
        "week": week,
        "semester": {"id": sem["id"], "name": sem["name"],
                     "start_date": sem["start_date"], "weeks": sem["weeks"]},
        "date_range": {"start": mon.isoformat(), "end": sun.isoformat()},
        "timezone": "Asia/Urumqi (UTC+6)",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+06:00"),
        "source": "http://localhost:17860/",
        "person_count": len(persons),
        "slots": [{"id": s["id"] + 1, "label": s["label"], "time": s["time"]} for s in SLOTS],
        "days": [{"day": i, "day_cn": DAY_CN[i],
                  "date": (mon + timedelta(days=i)).isoformat()} for i in range(7)],
        "persons": persons_out,
        "free": free,
    }

@app.route("/api/export")
def export_schedule():
    week = request.args.get("week", type=int) or 1
    fmt = (request.args.get("format") or "md").lower()
    db = get_db()
    sem = _resolve_semester(db, request.args.get("semester", type=int))
    if fmt == "json":
        body = json.dumps(_json_export(week, sem), ensure_ascii=False, indent=2)
        resp = Response(body, mimetype="application/json")
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        ext = "json"
    else:
        body = _md_export(week, sem)
        resp = Response(body)
        resp.headers["Content-Type"] = "text/markdown; charset=utf-8"
        ext = "md"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    if request.args.get("download") == "1":
        mon = _week_monday(week, sem)
        sun = mon + timedelta(days=6)
        fname = "timetable-week%d-%02d%02d-%02d%02d.%s" % (
            week, mon.month, mon.day, sun.month, sun.day, ext)
        resp.headers["Content-Disposition"] = 'attachment; filename="%s"' % fname
    return resp

@app.route("/")
def index():
    # 直接读盘返回（不用 send_from_directory，否则是 passthrough 响应没法 gzip）
    p = os.path.join(BASE_DIR, "index.html")
    with open(p, "rb") as f:
        body = f.read()
    u = current_user()
    attrs = (' data-role="%s" data-name="%s" data-no="%s"' % (
        html.escape(u["role"]), html.escape(u["name"]), html.escape(u["no"]))).encode("utf-8")
    body = body.replace(b"<body>", b"<body" + attrs + b">", 1)
    resp = Response(body, mimetype="text/html")
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return resp

# ---------- 日历订阅（ICS） ----------
BS = chr(92)

def _ics_escape(s):
    if s is None:
        return ""
    t = str(s)
    return (t.replace(BS, BS * 2).replace(";", BS + ";")
             .replace(",", BS + ",").replace("\n", BS + "n"))


@app.route("/calendar.ics")
def calendar_ics():
    db = get_db()
    sem = _resolve_semester(db, request.args.get("semester", type=int))
    qp = request.args.get("person")
    if qp:
        if qp.isdigit():
            prow = db.execute("SELECT id, name FROM persons WHERE semester_id=? AND id=?",
                              (sem["id"], int(qp))).fetchone()
        else:
            prow = db.execute("SELECT id, name FROM persons WHERE semester_id=? AND name=?",
                              (sem["id"], qp)).fetchone()
    else:
        prow = db.execute("SELECT id, name FROM persons WHERE semester_id=? ORDER BY id LIMIT 1",
                          (sem["id"],)).fetchone()
    if not prow:
        abort(404)

    rows = db.execute(
        "SELECT name, day, slot, weeks, location FROM courses WHERE person_id=? "
        "ORDER BY day, slot", (prow["id"],)).fetchall()

    flat = []
    for r in rows:
        try:
            wl = json.loads(r["weeks"] or "[]")
        except Exception:
            continue
        for w in wl:
            flat.append({"week": int(w), "day": r["day"], "slot": r["slot"],
                         "name": r["name"], "location": r["location"]})
    flat.sort(key=lambda x: (x["week"], x["day"], x["slot"], x["name"]))

    merged = []
    for it in flat:
        prev = merged[-1] if merged else None
        if (prev and prev["week"] == it["week"] and prev["day"] == it["day"]
                and prev["name"] == it["name"] and prev["location"] == it["location"]
                and prev["slot_end"] + 1 == it["slot"]):
            prev["slot_end"] = it["slot"]
        else:
            merged.append({"week": it["week"], "day": it["day"], "name": it["name"],
                           "location": it["location"],
                           "slot_start": it["slot"], "slot_end": it["slot"]})

    base = date(*[int(x) for x in sem["start_date"].split("-")])
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0",
         "PRODID:-//schedule-manager//CN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:" + _ics_escape("课表 " + prow["name"]),
         "X-WR-TIMEZONE:Asia/Urumqi",
         "BEGIN:VTIMEZONE", "TZID:Asia/Urumqi",
         "BEGIN:STANDARD", "DTSTART:19700101T000000",
         "TZOFFSETFROM:+0600", "TZOFFSETTO:+0600", "TZNAME:URUMQI",
         "END:STANDARD", "END:VTIMEZONE"]
    for m in merged:
        d = base + timedelta(days=(m["week"] - 1) * 7 + m["day"])
        t1 = SLOTS[m["slot_start"]]["time"].split("-")[0].replace(":", "")
        t2 = SLOTS[m["slot_end"]]["time"].split("-")[1].replace(":", "")
        L += ["BEGIN:VEVENT",
              "UID:p%d-w%d-d%d-s%d@schedule-manager" % (prow["id"], m["week"], m["day"], m["slot_start"]),
              "DTSTAMP:" + stamp,
              "DTSTART;TZID=Asia/Urumqi:%sT%s00" % (d.strftime("%Y%m%d"), t1),
              "DTEND;TZID=Asia/Urumqi:%sT%s00" % (d.strftime("%Y%m%d"), t2),
              "SUMMARY:" + _ics_escape(m["name"]),
              "LOCATION:" + _ics_escape(m["location"] or ""),
              "DESCRIPTION:" + _ics_escape("%s 第%d周 %s" % (DAY_CN[m["day"]], m["week"], SLOTS[m["slot_start"]]["label"])),
              "END:VEVENT"]
    L.append("END:VCALENDAR")
    body = "\r\n".join(L) + "\r\n"
    resp = Response(body, mimetype="text/calendar")
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/health")
def _health():
    return jsonify({"ok": True, "service": "schedule"})


@app.route("/api/me")
def api_me():
    if not session.get("auth"):
        return jsonify({"ok": False, "error": "未登录"}), 401
    u = current_user()
    return jsonify({"ok": True, "name": u["name"], "role": u["role"], "no": u["no"]})


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print(" 课表总览已启动")
    print(" 浏览器访问: http://127.0.0.1:17860")
    print("=" * 50)
    app.run(host="0.0.0.0", port=17860, debug=False)