# toxirov_bank_ultra.py — Toxirov Bank ULTRA: демо-банк с максимумом функций
# Запуск: pip install flask → python toxirov_bank_ultra.py
# Локально: http://127.0.0.1:5000 · С телефона (тот же Wi-Fi): http://<IP-ПК>:5000
# Вход: sarvar.com / sarvar26 · Быстрый вход: PIN 2606
# ⚠️ ДЕМО: реальных денег нет, всё симулируется локально.
import sqlite3, json, random, datetime, functools, io, os
from flask import (Flask, request, redirect, session,
                   render_template_string, Response)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "toxirov-bank-ultra-2026"
DB = "toxirov_ultra.db"

RATES = {"RUB": 1.0, "USD": 98.5, "UZS": 0.0078}
CUR_SYM = {"RUB": "₽", "USD": "$", "UZS": "so'm"}
SERVICES = ["Мобильная связь 📱", "Интернет 🌐", "ЖКХ 🏠", "Транспорт 🚇", "ТВ 📺"]
CASHBACK = 0.01   # 1%
DEPOSIT_RATE = 14 # % годовых

# ----------------------------- БАЗА ДАННЫХ -----------------------------

def init_db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password_hash TEXT, name TEXT,
        balance_rub REAL, balance_usd REAL, balance_uzs REAL,
        card_no TEXT, phone TEXT, avatar TEXT, pin_hash TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, type TEXT, currency TEXT, amount REAL,
        counterparty TEXT, comment TEXT, status TEXT, created_at TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS goals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, name TEXT, target REAL, saved REAL DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, text TEXT, icon TEXT, created_at TEXT, read INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS deposits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount REAL, rate REAL, created_at TEXT, last_accrual TEXT)""")
    if not con.execute("SELECT 1 FROM users WHERE username='sarvar.com'").fetchone():
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        con.execute("INSERT INTO users(username,password_hash,name,balance_rub,balance_usd,balance_uzs,card_no,phone,avatar,pin_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    ("sarvar.com", generate_password_hash("sarvar26"), "Sarvar Toxirov",
                     2500000.0, 5000.0, 120000000.0,
                     "9860 2606 7788 1234", "+998 90 260 06 26", "🦅",
                     generate_password_hash("2606")))
        for txt, ic in [("Добро пожаловать в Toxirov Bank ULTRA! ✨", "🎉"),
                        ("Ваш аккаунт переведён на тариф Premium ✦", "💎"),
                        ("Новое: вход по PIN-коду 📟", "🆕"),
                        ("Новое: вклады с 14% годовых 🏦", "🆕")]:
            con.execute("INSERT INTO notifications(user_id,text,icon,created_at) VALUES(?,?,?,?)", (1, txt, ic, now))
    con.commit(); con.close()

init_db()

# ----------------------------- УТИЛИТЫ -----------------------------

def now():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

def parse_dt(s):
    return datetime.datetime.strptime(s, "%d.%m.%Y %H:%M")

def notify(text, icon="🔔"):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO notifications(user_id,text,icon,created_at) VALUES(?,?,?,?)",
                (session["uid"], text, icon, now()))
    con.commit(); con.close()

def get_user():
    con = sqlite3.connect(DB)
    u = con.execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
    con.close()
    return u  # 0id 1user 2hash 3name 4rub 5usd 6uzs 7card 8phone 9avatar 10pin

def add_tx(kind, currency, amount, counterparty, comment, status="Выполнен (демо)"):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO transactions(user_id,type,currency,amount,counterparty,comment,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (session["uid"], kind, currency, amount, counterparty, comment, status, now()))
    con.commit(); con.close()

def unread_count():
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (session["uid"],)).fetchone()[0]
    con.close()
    return n

def fmt(x, dec=2):
    return f"{x:,.{dec}f}".replace(",", " ")

def accrue_deposits(uid):
    """Начисляет проценты по вкладам за прошедшие дни."""
    con = sqlite3.connect(DB)
    ds = con.execute("SELECT id,amount,rate,last_accrual FROM deposits WHERE user_id=?", (uid,)).fetchall()
    total_int = 0.0
    for d in ds:
        days = (datetime.datetime.now() - parse_dt(d[3])).days
        if days > 0:
            interest = d[1] * d[2] / 100 / 365 * days
            con.execute("UPDATE users SET balance_rub=balance_rub+? WHERE id=?", (interest, uid))
            con.execute("UPDATE deposits SET last_accrual=? WHERE id=?", (now(), d[0]))
            total_int += interest
    con.commit(); con.close()
    if total_int > 0:
        add_tx("in", "RUB", round(total_int, 2), "Проценты по вкладу", f"{DEPOSIT_RATE}% годовых × {days} дн.")
        notify(f"Начислены проценты по вкладу: +{fmt(total_int)} ₽ 📈", "🏦")

def spend(col, amount):
    con = sqlite3.connect(DB)
    con.execute(f"UPDATE users SET {col}={col}-? WHERE id=?", (amount, session["uid"]))
    con.commit(); con.close()

def earn(col, amount):
    con = sqlite3.connect(DB)
    con.execute(f"UPDATE users SET {col}={col}+? WHERE id=?", (amount, session["uid"]))
    con.commit(); con.close()

def balance_of(col):
    con = sqlite3.connect(DB)
    v = con.execute(f"SELECT {col} FROM users WHERE id=?", (session["uid"],)).fetchone()[0]
    con.close()
    return v

def login_required(f):
    @functools.wraps(f)
    def w(*args, **kwargs):
        if "uid" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return w

# ----------------------------- СТИЛИ -----------------------------

LOGO = """<svg width="42" height="42" viewBox="0 0 46 46" fill="none">
<rect x="2" y="2" width="42" height="42" rx="12" fill="url(#g1)" stroke="url(#g2)" stroke-width="2"/>
<path d="M14 16h18M23 16v15M17 24h12" stroke="#0b1020" stroke-width="3.4" stroke-linecap="round"/>
<defs><linearGradient id="g1" x1="0" y1="0" x2="46" y2="46">
<stop stop-color="#ffd76a"/><stop offset="1" stop-color="#c9962e"/></linearGradient>
<linearGradient id="g2" x1="0" y1="0" x2="46" y2="46">
<stop stop-color="#fff2c4"/><stop offset="1" stop-color="#8a6512"/></linearGradient></defs></svg>"""

CSS = """
*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
body{background:#0b1020;color:#e8ecf6;min-height:100vh;overflow-x:hidden;transition:background .5s,color .5s}
body.light{background:#eef1f8;color:#1c2340}
.bg-orbs{position:fixed;inset:0;z-index:-1;overflow:hidden}
.orb{position:absolute;border-radius:50%;filter:blur(90px);opacity:.32;animation:float 16s ease-in-out infinite}
.orb1{width:440px;height:440px;background:#2b5cff;top:-130px;left:-110px}
.orb2{width:380px;height:380px;background:#c9962e;bottom:-130px;right:-90px;animation-delay:-6s}
.orb3{width:260px;height:260px;background:#7b2bff;top:42%;left:56%;animation-delay:-3s}
body.light .orb{opacity:.18}
@keyframes float{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-42px) scale(1.07)}}
.page{animation:pageIn .5s cubic-bezier(.22,1,.36,1) both;max-width:1100px;margin:0 auto;padding:24px}
@keyframes pageIn{from{opacity:0;transform:translateY(22px) scale(.985)}to{opacity:1;transform:none}}
.topbar{display:flex;align-items:center;gap:14px;padding:12px 0 26px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px}
.brand b{font-size:20px;letter-spacing:.4px;background:linear-gradient(90deg,#ffd76a,#fff0c0,#ffd76a);
background-size:200%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:shine 4s linear infinite}
@keyframes shine{to{background-position:200%}}
.nav{margin-left:auto;display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.nav a{color:#aab4d4;text-decoration:none;padding:9px 13px;border-radius:10px;font-size:14px;transition:.25s}
.nav a:hover,.nav a.active{color:#ffd76a;background:rgba(255,215,106,.08)}
.bell{position:relative;font-size:18px;text-decoration:none;padding:9px 13px;border-radius:10px;transition:.25s}
.bell:hover{background:rgba(255,255,255,.08)}
.badge{position:absolute;top:4px;right:4px;background:#e94560;color:#fff;font-size:10px;font-weight:700;
min-width:17px;height:17px;border-radius:99px;display:flex;align-items:center;justify-content:center;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.18)}}
.card{background:linear-gradient(160deg,rgba(255,255,255,.06),rgba(255,255,255,.02));
border:1px solid rgba(255,255,255,.09);border-radius:22px;padding:26px;
backdrop-filter:blur(14px);box-shadow:0 22px 60px rgba(0,0,0,.45);
transition:transform .35s cubic-bezier(.22,1,.36,1),box-shadow .35s,background .5s}
.card:hover{transform:translateY(-3px);box-shadow:0 30px 70px rgba(0,0,0,.55)}
body.light .card{background:#fff;border-color:#e3e8f4;box-shadow:0 14px 40px rgba(30,50,120,.12)}
.grid{display:grid;gap:20px}
.grid-2{grid-template-columns:1.35fr 1fr}
.grid-3{grid-template-columns:repeat(3,1fr)}
@media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr}}
label{font-size:12px;color:#8b95b5;text-transform:uppercase;letter-spacing:1px}
input,select,textarea{width:100%;padding:13px 15px;margin:7px 0 15px;border-radius:12px;font-size:15px;
border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.05);color:#fff;outline:none;
transition:border .25s, box-shadow .25s;font-family:inherit}
input:focus,select:focus,textarea:focus{border-color:#ffd76a;box-shadow:0 0 0 3px rgba(255,215,106,.15)}
select option{color:#111}
body.light input,body.light select,body.light textarea{background:#f4f6fc;border-color:#dde3f0;color:#1c2340}
.btn{display:inline-block;width:100%;padding:14px;border:none;border-radius:13px;font-size:15px;
font-weight:600;cursor:pointer;color:#1a1300;text-decoration:none;text-align:center;
background:linear-gradient(135deg,#ffd76a,#e9b949);box-shadow:0 10px 26px rgba(233,185,73,.35);
transition:transform .22s, box-shadow .22s}
.btn:hover{transform:translateY(-2px) scale(1.01);box-shadow:0 16px 34px rgba(233,185,73,.5)}
.btn:active{transform:scale(.97)}
.btn-ghost{background:rgba(255,255,255,.07);color:#dfe5f5;box-shadow:none}
.btn-sm{width:auto;padding:8px 16px;margin:0 0 0 auto;font-size:13px}
.balance{font-size:42px;font-weight:700;letter-spacing:.5px;margin:4px 0;
background:linear-gradient(90deg,#fff,#ffd76a);-webkit-background-clip:text;background-clip:text;color:transparent}
body.light .balance{background:linear-gradient(90deg,#1c2340,#b8860b);-webkit-background-clip:text;background-clip:text}
.muted{color:#8b95b5;font-size:13px}
body.light .muted{color:#7a84a8}
.pill{font-size:11px;padding:4px 11px;border-radius:99px;background:rgba(74,222,128,.14);color:#4ade80;letter-spacing:.5px}
.bankcard{position:relative;height:200px;border-radius:20px;padding:24px;overflow:hidden;
background:linear-gradient(130deg,#1b2a5e,#0e1737 55%,#3a2c07);
border:1px solid rgba(255,215,106,.35);transition:transform .15s ease-out;transform-style:preserve-3d;will-change:transform}
.bankcard .chip{width:44px;height:32px;border-radius:7px;background:linear-gradient(135deg,#ffe9a3,#c9962e);margin-bottom:16px}
.bankcard .num{letter-spacing:3px;font-size:17px;margin-bottom:12px}
.bankcard .glow{position:absolute;width:200px;height:200px;border-radius:50%;background:radial-gradient(circle,rgba(255,215,106,.25),transparent 70%);
top:-70px;right:-50px;pointer-events:none}
.tx{display:flex;align-items:center;gap:14px;padding:13px 6px;border-bottom:1px solid rgba(255,255,255,.06);animation:pageIn .4s both}
.tx:last-child{border-bottom:none}
.tx .ic{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;
background:rgba(255,255,255,.07);flex-shrink:0}
body.light .tx .ic,body.light .notif .ic{background:#eef1fa}
.tx .amt{margin-left:auto;font-weight:600;white-space:nowrap}
.in{color:#4ade80}.out{color:#f87171}
.toast{position:fixed;top:24px;right:24px;padding:16px 22px;border-radius:14px;z-index:99;
background:linear-gradient(135deg,#123c26,#0d2a1c);border:1px solid rgba(74,222,128,.4);
color:#b9f6cf;box-shadow:0 18px 44px rgba(0,0,0,.5);animation:toastIn .45s cubic-bezier(.22,1,.36,1) both;max-width:340px}
.toast.err{background:linear-gradient(135deg,#4a1620,#2b0d13);border-color:rgba(248,113,113,.4);color:#fecaca}
@keyframes toastIn{from{opacity:0;transform:translateX(60px)}to{opacity:1;transform:none}}
.shine-line{height:3px;border-radius:99px;background:linear-gradient(90deg,transparent,#ffd76a,transparent);
margin:18px 0;animation:shine 3s linear infinite;background-size:200%}
.quick{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 8px;border-radius:16px;
background:rgba(255,255,255,.04);text-decoration:none;color:#dfe5f5;font-size:12.5px;transition:.28s;border:1px solid transparent}
.quick:hover{background:rgba(255,215,106,.1);border-color:rgba(255,215,106,.3);transform:translateY(-4px)}
.quick span{font-size:24px}
body.light .quick{background:#f4f6fc;color:#3a4470}
.progress{height:10px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden;margin-top:8px}
body.light .progress{background:#e5e9f4}
.progress i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#ffd76a,#4ade80);
transition:width 1s cubic-bezier(.22,1,.36,1)}
.avatar{width:74px;height:74px;border-radius:50%;background:linear-gradient(135deg,#2b5cff,#7b2bff);
display:flex;align-items:center;justify-content:center;font-size:36px;margin-bottom:12px}
.avatar.pick{cursor:pointer;width:52px;height:52px;font-size:24px;margin:0;transition:.25s;border:2px solid transparent}
.avatar.pick:hover,.avatar.pick.sel{border-color:#ffd76a;transform:scale(1.1)}
.faq-q{cursor:pointer;padding:15px 4px;font-weight:600;display:flex;justify-content:space-between;transition:color .25s;border-bottom:1px solid rgba(255,255,255,.07)}
.faq-q:hover{color:#ffd76a}
.faq-a{max-height:0;overflow:hidden;transition:max-height .4s ease;padding-left:4px;color:#aab4d4;font-size:14px}
.faq-a p{padding:10px 0}
.faq-item.open .faq-a{max-height:200px}
.faq-item.open .faq-q span{transform:rotate(45deg)}
.faq-q span{transition:transform .3s}
.center{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.login-box{width:100%;max-width:410px;text-align:center}
.login-box .brand{justify-content:center;margin-bottom:24px}
.hint{margin-top:16px;font-size:12px;color:#6b769a}
table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:10px 6px;border-bottom:1px solid rgba(255,255,255,.07)}
body.light td{border-color:#edf0f8}
tr{transition:background .25s}
tr:hover{background:rgba(255,255,255,.03)}
.switch{position:relative;width:48px;height:26px;background:rgba(255,255,255,.12);border-radius:99px;cursor:pointer;transition:.3s;display:inline-block;vertical-align:middle}
.switch:before{content:"";position:absolute;width:20px;height:20px;border-radius:50%;background:#fff;top:3px;left:3px;transition:.3s cubic-bezier(.22,1,.36,1)}
.switch.on{background:#4ade80}
.switch.on:before{left:25px}
.notif{display:flex;gap:14px;padding:15px 6px;border-bottom:1px solid rgba(255,255,255,.06);animation:pageIn .4s both}
.notif.unread{background:rgba(255,215,106,.05);border-radius:12px;padding:15px 12px}
body.light .notif,body.light .faq-q,body.light .tx{border-color:#edf0f8}
.chart{display:flex;align-items:flex-end;gap:10px;height:130px;padding-top:10px}
.bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:6px;height:100%;justify-content:flex-end}
.bar i{width:100%;max-width:38px;border-radius:8px 8px 3px 3px;background:linear-gradient(180deg,#ffd76a,#b8860b);
min-height:4px;transition:height 1s cubic-bezier(.22,1,.36,1);position:relative}
.bar i:hover{filter:brightness(1.2)}
.bar span{font-size:11px;color:#8b95b5}
.pinpad{display:grid;grid-template-columns:repeat(3,72px);gap:12px;justify-content:center;margin:18px 0}
.pinpad button{height:64px;border-radius:18px;font-size:22px;border:1px solid rgba(255,255,255,.1);
background:rgba(255,255,255,.05);color:#fff;cursor:pointer;transition:.2s}
.pinpad button:hover{background:rgba(255,215,106,.15);transform:scale(1.06)}
.pinpad button:active{transform:scale(.93)}
.pindots{display:flex;gap:14px;justify-content:center;margin:12px 0}
.pindots b{width:15px;height:15px;border-radius:50%;background:rgba(255,255,255,.15);transition:.2s}
.pindots b.f{background:#ffd76a;transform:scale(1.2)}
.stat{background:rgba(255,255,255,.05);border-radius:14px;padding:14px 16px;transition:background .3s}
.stat:hover{background:rgba(255,255,255,.09)}
body.light .stat{background:#f4f6fc}
.stat b{display:block;font-size:19px;margin-top:4px}
body.light .nav a{color:#5a6490}
body.light .nav a:hover,body.light .nav a.active{color:#b8860b}
"""

def page(title, body, active="", **kw):
    return render_template_string("""<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#0b1020">
<link rel="apple-touch-icon" href="/icon.png">
<link rel="manifest" href="/manifest.json">
<title>{{title}} — Toxirov Bank</title><style>""" + CSS + """</style></head>
<body class="{{'light' if t=='light'}}">
<div class="bg-orbs"><div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div></div>
<div class="page">
<div class="topbar"><div class="brand">""" + LOGO + """<b>TOXIROV BANK</b></div>
<nav class="nav">
<a href="/" class="{{'active' if a=='home'}}">Главная</a>
<a href="/transfer" class="{{'active' if a=='transfer'}}">Переводы</a>
<a href="/services" class="{{'active' if a=='services'}}">Услуги</a>
<a href="/exchange" class="{{'active' if a=='exchange'}}">Обмен</a>
<a href="/deposit" class="{{'active' if a=='deposit'}}">Вклад</a>
<a href="/loan" class="{{'active' if a=='loan'}}">Кредит</a>
<a href="/goals" class="{{'active' if a=='goals'}}">Цели</a>
<a href="/history" class="{{'active' if a=='history'}}">История</a>
<a href="/support" class="{{'active' if a=='support'}}">Поддержка</a>
<a href="/profile" class="{{'active' if a=='profile'}}">Профиль</a>
<a href="/notifications" class="bell">🔔{% if n %}<span class="badge">{{n}}</span>{% endif %}</a>
<a href="/logout" title="Выйти">➜</a></nav></div>
{{body|safe}}
</div>
<script>
document.querySelectorAll('.count').forEach(el=>{
 const target=parseFloat(el.dataset.v), dec=+(el.dataset.d||2), suf=el.dataset.s||'';
 const t0=performance.now(), dur=900;
 (function step(t){const p=Math.min((t-t0)/dur,1);
  el.textContent=target.toLocaleString('ru-RU',{minimumFractionDigits:dec,maximumFractionDigits:dec})+suf;
  if(p<1)requestAnimationFrame(step);})(t0);});
const bc=document.querySelector('.bankcard');
if(bc){bc.addEventListener('mousemove',e=>{const r=bc.getBoundingClientRect(),
 x=(e.clientX-r.left)/r.width-.5, y=(e.clientY-r.top)/r.height-.5;
 bc.style.transform=`rotateY(${x*14}deg) rotateX(${y*-10}deg) scale(1.03)`;});
 bc.addEventListener('mouseleave',()=>bc.style.transform='');}
document.querySelectorAll('.faq-q').forEach(q=>q.addEventListener('click',()=>{
 const it=q.parentElement, was=it.classList.contains('open');
 document.querySelectorAll('.faq-item').forEach(x=>x.classList.remove('open'));
 if(!was)it.classList.add('open');}));
setTimeout(()=>document.querySelectorAll('.toast').forEach(t=>{t.style.transition='opacity .5s';t.style.opacity=0;setTimeout(()=>t.remove(),500);}),4200);
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');
</script></body></html>""", title=title, body=body, a=active, n=unread_count() if "uid" in session else 0,
        t=session.get("theme", "dark"), **kw)

# ----------------------------- АВТОРИЗАЦИЯ -----------------------------

LOGIN_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Вход — Toxirov Bank</title><style>""" + CSS + """</style></head><body>
<div class="bg-orbs"><div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div></div>
<div class="center"><div class="page login-box">
<div class="brand">""" + LOGO + """<b>TOXIROV BANK</b></div>
<div class="card">
<h2 style="margin-bottom:6px">С возвращением 👋</h2>
<p class="muted" style="margin-bottom:22px">Войдите в свой аккаунт</p>
<form method="post">
<label>Логин</label><input name="username" placeholder="sarvar.com" required autofocus>
<label>Пароль</label><input name="password" type="password" placeholder="••••••••" required>
<button class="btn">Войти в банк 🔐</button>
</form>
{% if error %}<p style="color:#f87171;margin-top:14px;font-size:14px">{{error}}</p>{% endif %}
<p style="margin-top:16px;font-size:14px"><a href="/pin_login" style="color:#ffd76a;text-decoration:none">📟 Войти по PIN-коду</a></p>
</div>
<p class="hint">Демо-версия · sarvar.com / sarvar26 · PIN: 2606</p>
</div></div></body></html>"""

PIN_HTML = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PIN-вход — Toxirov Bank</title><style>""" + CSS + """</style></head><body>
<div class="bg-orbs"><div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div></div>
<div class="center"><div class="page login-box">
<div class="brand">""" + LOGO + """<b>TOXIROV BANK</b></div>
<div class="card">
<h2>📟 Быстрый вход</h2>
<p class="muted" style="margin:8px 0 4px">Введите 4-значный PIN-код</p>
<div class="pindots" id="dots"><b></b><b></b><b></b><b></b></div>
<form method="post" id="f"><input type="hidden" name="pin" id="pin"></form>
<div class="pinpad">
<button type="button">1</button><button type="button">2</button><button type="button">3</button>
<button type="button">4</button><button type="button">5</button><button type="button">6</button>
<button type="button">7</button><button type="button">8</button><button type="button">9</button>
<button type="button" data-k="c">C</button><button type="button">0</button><button type="button" data-k="b">⌫</button>
</div>
{% if error %}<p style="color:#f87171;font-size:14px">{{error}}</p>{% endif %}
<p style="margin-top:14px;font-size:14px"><a href="/login" style="color:#aab4d4;text-decoration:none">← Войти по паролю</a></p>
</div></div></div>
<script>
let v='';
const dots=document.querySelectorAll('#dots b'), inp=document.getElementById('pin');
document.querySelectorAll('.pinpad button').forEach(b=>b.addEventListener('click',()=>{
 const k=b.dataset.k;
 if(k==='c'){v='';}
 else if(k==='b'){v=v.slice(0,-1);}
 else if(v.length<4){v+=b.textContent;}
 dots.forEach((d,i)=>d.classList.toggle('f',i<v.length));
 inp.value=v;
 if(v.length===4)setTimeout(()=>document.getElementById('f').submit(),180);
}));</script></body></html>"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if "uid" in session:
        return redirect("/")
    error = None
    if request.method == "POST":
        con = sqlite3.connect(DB)
        u = con.execute("SELECT * FROM users WHERE username=?", (request.form["username"].strip(),)).fetchone()
        con.close()
        if u and check_password_hash(u[2], request.form["password"]):
            session["uid"] = u[0]
            session["hide_balance"] = False
            accrue_deposits(u[0])
            notify("Вы вошли в аккаунт. Приятного пользования! 👋", "🔐")
            return redirect("/")
        error = "Неверный логин или пароль 😕"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/pin_login", methods=["GET", "POST"])
def pin_login():
    if "uid" in session:
        return redirect("/")
    error = None
    if request.method == "POST":
        con = sqlite3.connect(DB)
        users = con.execute("SELECT * FROM users WHERE pin_hash IS NOT NULL").fetchall()
        con.close()
        for u in users:
            if check_password_hash(u[10], request.form["pin"]):
                session["uid"] = u[0]
                session["hide_balance"] = False
                accrue_deposits(u[0])
                notify("Быстрый вход по PIN 📟", "🔐")
                return redirect("/")
        error = "Неверный PIN-код 😕"
    return render_template_string(PIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/toggle_theme")
@login_required
def toggle_theme():
    session["theme"] = "light" if session.get("theme", "dark") == "dark" else "dark"
    return redirect(request.args.get("back", "/"))

# ----------------------------- ГЛАВНАЯ -----------------------------

@app.route("/")
@login_required
def home():
    u = get_user()
    accrue_deposits(u[0])
    u = get_user()
    con = sqlite3.connect(DB)
    txs = con.execute("SELECT type,currency,amount,counterparty,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 6", (u[0],)).fetchall()
    goals = con.execute("SELECT name,target,saved FROM goals WHERE user_id=?", (u[0],)).fetchall()
    deps = con.execute("SELECT amount,rate FROM deposits WHERE user_id=?", (u[0],)).fetchall()
    # график: расходы за 7 дней (RUB)
    alltx = con.execute("SELECT amount,created_at FROM transactions WHERE user_id=? AND type='out' AND currency='RUB'", (u[0],)).fetchall()
    con.close()
    days = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%d.%m") for i in range(6, -1, -1)]
    sums = {d: 0.0 for d in days}
    for t in alltx:
        d = t[1][:5]
        if d in sums:
            sums[d] += t[0]
    mx = max(sums.values()) or 1
    bars = "".join(f'<div class="bar"><i style="height:{max(4, sums[d]/mx*100):.0f}%"></i><span>{d}</span></div>' for d in days)
    hide = session.get("hide_balance", False)
    bal_html = "••••••" if hide else f'<span class="balance"><span class="count" data-v="{u[4]}">{fmt(u[4])}</span> ₽</span>'
    def mini(cur, val, dec, suf):
        v = "••••" if hide else fmt(val, dec)
        return f'<div class="stat"><span class="muted">{cur}</span><b>{v} {suf}</b></div>'
    tx_html = "".join(
        f"""<div class="tx"><div class="ic">{'💸' if t[0]=='out' else '💰'}</div>
        <div><div>{t[3]}</div><div class="muted">{t[4]} · {t[1]}</div></div>
        <div class="amt {'out' if t[0]=='out' else 'in'}">{('-' if t[0]=='out' else '+')}{fmt(t[2])} {CUR_SYM[t[1]]}</div></div>"""
        for t in txs) or '<p class="muted" style="padding:14px 0">Операций пока нет ✨</p>'
    goals_html = "".join(
        f"""<div style="margin-bottom:16px"><div style="display:flex;justify-content:space-between">
        <b>🎯 {g[0]}</b><span class="muted">{fmt(min(g[2],g[1]))} / {fmt(g[1])} ₽</span></div>
        <div class="progress"><i style="width:{min(100,g[2]/g[1]*100):.0f}%"></i></div></div>"""
        for g in goals[:3]) or '<p class="muted">Целей нет — создай на странице «Цели» 🎯</p>'
    dep_html = "".join(
        f"""<div class="tx"><div class="ic">🏦</div><div>Вклад<div class="muted">{d[1]}% годовых</div></div>
        <div class="amt in">{fmt(d[0])} ₽</div></div>""" for d in deps) or '<p class="muted">Вкладов нет — открой на 14% годовых 📈</p>'
    body = f"""
<div class="grid grid-2">
<div class="card">
<div style="display:flex;justify-content:space-between;align-items:center">
<span class="pill">ULTRA · PREMIUM ✦</span>
<a href="/toggle_balance?back=/" style="text-decoration:none;font-size:18px" title="Показать/скрыть баланс">{'🙈' if not hide else '👁'}</a></div>
<p class="muted" style="margin-top:14px">Общий баланс счёта</p>
{bal_html}
<p class="muted">{u[3]} · UZ-2606-MAIN</p>
<div class="shine-line"></div>
<div class="stats">{mini('RUB',u[4],2,'₽')}{mini('USD',u[5],2,'$')}{mini('UZS',u[6],0,"so'm")}</div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px">
<a class="quick" href="/transfer"><span>💸</span>Перевод</a>
<a class="quick" href="/topup"><span>➕</span>Пополнить</a>
<a class="quick" href="/services"><span>🛍</span>Услуги</a>
<a class="quick" href="/exchange"><span>🔄</span>Обмен</a>
</div></div>
<div class="bankcard"><div class="glow"></div>
<div style="display:flex;justify-content:space-between;align-items:flex-start">
<span style="color:#ffd76a;font-weight:700;letter-spacing:2px;font-size:13px">TOXIROV BANK</span><span style="font-size:22px">💳</span></div>
<div class="chip"></div>
<div class="num">{u[7] if not hide else '•••• •••• •••• ••••'}</div>
<div style="display:flex;justify-content:space-between">
<span class="muted" style="color:#c9b377">{u[3].upper()}</span><span class="muted" style="color:#c9b377">12/29</span></div>
</div></div>
<div class="grid grid-2" style="margin-top:20px">
<div class="card"><h3 style="margin-bottom:8px">Расходы за 7 дней 📊</h3><div class="chart">{bars}</div></div>
<div class="card"><h3 style="margin-bottom:10px">Вклады 🏦</h3>{dep_html}
<div class="shine-line"></div><h3 style="margin-bottom:10px">Мои цели 🎯</h3>{goals_html}</div>
</div>
<div class="card" style="margin-top:20px"><h3 style="margin-bottom:8px">Последние операции</h3>{tx_html}
<a href="/history" style="color:#ffd76a;font-size:13px;text-decoration:none">Вся история →</a></div>"""
    return page("Главная", body, "home")

@app.route("/toggle_balance")
@login_required
def toggle_balance():
    session["hide_balance"] = not session.get("hide_balance", False)
    return redirect(request.args.get("back", "/"))

# ----------------------------- ПЕРЕВОДЫ -----------------------------

@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    toast = ""
    if request.method == "POST":
        amount = float(request.form["amount"])
        to = request.form["to"].strip()
        currency = request.form.get("currency", "RUB")
        comment = request.form.get("comment", "").strip() or "Перевод"
        col = {"RUB": "balance_rub", "USD": "balance_usd", "UZS": "balance_uzs"}[currency]
        if amount <= 0 or amount > balance_of(col):
            toast = """<div class="toast err">Недостаточно средств или неверная сумма ❌</div>"""
        else:
            spend(col, amount)
            add_tx("out", currency, amount, to, comment)
            notify(f"Перевод {fmt(amount)} {CUR_SYM[currency]} для «{to}» выполнен ✅", "💸")
            toast = f"""<div class="toast">✅ Перевод {fmt(amount)} {CUR_SYM[currency]} для «{to}» выполнен!</div>"""
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card">
<h2 style="margin-bottom:18px">Перевод средств 💸</h2>
<form method="post">
<label>Кому (имя, карта или телефон)</label>
<input name="to" placeholder="Aziz Karimov / 9860 ... / +998 ..." required>
<label>Валюта</label>
<select name="currency"><option value="RUB">RUB ₽</option><option value="USD">USD $</option><option value="UZS">UZS so'm</option></select>
<label>Сумма</label>
<input name="amount" type="number" step="0.01" min="1" placeholder="10 000" required>
<label>Комментарий</label>
<input name="comment" placeholder="За обед 🍕">
<button class="btn">Отправить перевод ➤</button>
</form></div>
<div class="card">
<h3 style="margin-bottom:10px">⚡ Быстрые шаблоны</h3>
<div class="tx"><div class="ic">👤</div><div>Aziz Karimov<div class="muted">Карта ···· 7788</div></div>
<button class="btn btn-sm" onclick="quick('Aziz Karimov',15000)">15 000 ₽</button></div>
<div class="tx"><div class="ic">👤</div><div>Malika Yusupova<div class="muted">Телефон +998···</div></div>
<button class="btn btn-sm" onclick="quick('Malika Yusupova',25000)">25 000 ₽</button></div>
<div class="tx"><div class="ic">🏠</div><div>Маме на карту<div class="muted">Карта ···· 1234</div></div>
<button class="btn btn-sm" onclick="quick('Маме на карту',50000)">50 000 ₽</button></div>
<div class="tx"><div class="ic">⚡</div><div>Оплата ЖКХ<div class="muted">Ежемесячно</div></div>
<button class="btn btn-sm" onclick="quick('Оплата ЖКХ',3500)">3 500 ₽</button></div>
<p class="muted" style="margin-top:14px">💡 Шаблоны подставляют получателя и сумму автоматически.</p>
</div></div>
<script>
function quick(name,sum){{document.querySelector('[name=to]').value=name;
document.querySelector('[name=amount]').value=sum;
document.querySelector('form button').scrollIntoView({{behavior:'smooth',block:'center'}});}}
</script>"""
    return page("Переводы", body, "transfer")

# ----------------------------- ПОПОЛНЕНИЕ -----------------------------

@app.route("/topup", methods=["GET", "POST"])
@login_required
def topup():
    toast = ""
    if request.method == "POST":
        amount = float(request.form["amount"])
        source = request.form.get("source", "Другая карта")
        currency = request.form.get("currency", "RUB")
        if amount <= 0:
            toast = """<div class="toast err">Введите корректную сумму ❌</div>"""
        else:
            col = {"RUB": "balance_rub", "USD": "balance_usd", "UZS": "balance_uzs"}[currency]
            earn(col, amount)
            add_tx("in", currency, amount, f"Пополнение · {source}", "Зачисление")
            notify(f"Счёт пополнен на {fmt(amount)} {CUR_SYM[currency]} ➕", "💰")
            toast = f"""<div class="toast">✅ Счёт пополнен на {fmt(amount)} {CUR_SYM[currency]}!</div>"""
    body = f"""
{toast}
<div class="card" style="max-width:560px;margin:0 auto">
<h2 style="margin-bottom:18px">Пополнение счёта ➕</h2>
<form method="post">
<label>Способ пополнения</label>
<select name="source"><option>Другая карта</option><option>Наличные в банкомате</option><option>Со счёта телефона</option><option>Из другого банка</option></select>
<label>Валюта зачисления</label>
<select name="currency"><option value="RUB">RUB ₽</option><option value="USD">USD $</option><option value="UZS">UZS so'm</option></select>
<label>Сумма</label>
<input name="amount" type="number" step="0.01" min="1" placeholder="50 000" required>
<button class="btn">Пополнить счёт 💰</button>
</form>
<p class="muted" style="margin-top:14px">💡 Зачисление мгновенное (в демо-режиме).</p>
</div>"""
    return page("Пополнение", body, "home")

# ----------------------------- УСЛУГИ (с кэшбэком) -----------------------------

@app.route("/services", methods=["GET", "POST"])
@login_required
def services():
    toast = ""
    if request.method == "POST":
        amount = float(request.form["amount"])
        service = request.form["service"]
        currency = request.form.get("currency", "RUB")
        col = {"RUB": "balance_rub", "USD": "balance_usd", "UZS": "balance_uzs"}[currency]
        if amount <= 0 or amount > balance_of(col):
            toast = """<div class="toast err">Недостаточно средств или неверная сумма ❌</div>"""
        else:
            spend(col, amount)
            cash = round(amount * CASHBACK, 2)
            earn(col, cash)
            add_tx("out", currency, amount, f"Услуги · {service}", "Оплата")
            add_tx("in", currency, cash, f"Кэшбэк 1% · {service}", "Возврат")
            notify(f"Оплачено: {service} — {fmt(amount)} {CUR_SYM[currency]} · кэшбэк +{fmt(cash)} ₽ 🛍", "✅")
            toast = f"""<div class="toast">✅ {service} оплачено! Кэшбэк +{fmt(cash)} {CUR_SYM[currency]} 💜</div>"""
    svc_btns = "".join(f'<button type="button" class="btn btn-ghost" style="margin:0 0 10px" onclick="pick(\'{s}\')">{s}</button>' for s in SERVICES)
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card">
<h2 style="margin-bottom:18px">Оплата услуг 🛍</h2>
<form method="post">
<label>Услуга</label><input name="service" id="svc" placeholder="Выберите слева или введите..." required>
<label>Валюта</label>
<select name="currency"><option value="RUB">RUB ₽</option><option value="USD">USD $</option><option value="UZS">UZS so'm</option></select>
<label>Сумма</label><input name="amount" type="number" step="0.01" min="1" placeholder="1 000" required>
<button class="btn">Оплатить · кэшбэк 1% ✨</button>
</form></div>
<div class="card"><h3 style="margin-bottom:14px">Категории</h3>{svc_btns}
<div class="shine-line"></div>
<p class="muted">💜 С каждой оплаты возвращаем <b style="color:#ffd76a">1%</b> на баланс мгновенно.</p></div></div>
<script>function pick(s){{document.getElementById('svc').value=s;}}</script>"""
    return page("Услуги", body, "services")

# ----------------------------- ОБМЕН ВАЛЮТ -----------------------------

@app.route("/exchange", methods=["GET", "POST"])
@login_required
def exchange():
    toast = ""
    u = get_user()
    if request.method == "POST":
        frm, to_ = request.form["frm"], request.form["to"]
        amount = float(request.form["amount"])
        col = {"RUB": "balance_rub", "USD": "balance_usd", "UZS": "balance_uzs"}
        if frm == to_:
            toast = """<div class="toast err">Выберите разные валюты ❌</div>"""
        elif amount <= 0 or amount > balance_of(col[frm]):
            toast = """<div class="toast err">Недостаточно средств или неверная сумма ❌</div>"""
        else:
            got = amount * RATES[frm] / RATES[to_]
            spend(col[frm], amount)
            earn(col[to_], got)
            add_tx("out", frm, amount, f"Обмен → {to_}", f"Получено {fmt(got)} {CUR_SYM[to_]}")
            notify(f"Обменяно {fmt(amount)} {CUR_SYM[frm]} → {fmt(got)} {CUR_SYM[to_]} 🔄", "🔄")
            toast = f"""<div class="toast">✅ Обмен: {fmt(amount)} {CUR_SYM[frm]} → {fmt(got)} {CUR_SYM[to_]}!</div>"""
    rates_rows = "".join(f"<tr><td>{c}</td><td>{fmt(1/RATES[c],2)} {CUR_SYM[c]}</td><td>{fmt(RATES[c],4)} ₽</td></tr>" for c in ["USD","UZS"])
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card">
<h2 style="margin-bottom:18px">Обмен валют 🔄</h2>
<form method="post">
<label>Отдаю</label>
<select name="frm"><option value="RUB">RUB ₽ · {fmt(u[4])}</option><option value="USD">USD $ · {fmt(u[5])}</option><option value="UZS">UZS so'm · {fmt(u[6],0)}</option></select>
<label>Сумма</label>
<input name="amount" type="number" step="0.01" min="1" placeholder="1 000" required>
<label>Получаю</label>
<select name="to"><option value="USD">USD $</option><option value="UZS">UZS so'm</option><option value="RUB">RUB ₽</option></select>
<button class="btn">Обменять ✦</button>
</form></div>
<div class="card">
<h3 style="margin-bottom:12px">Курсы сегодня 📈</h3>
<table><tr><td style="color:#8b95b5">Валюта</td><td style="color:#8b95b5">1 ₽ =</td><td style="color:#8b95b5">1 ед. =</td></tr>{rates_rows}</table>
<p class="muted" style="margin-top:14px">💱 Демо-курсы фиксированы. Без комиссии.</p>
</div></div>"""
    return page("Обмен", body, "exchange")

# ----------------------------- ВКЛАДЫ -----------------------------

@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    toast = ""
    if request.method == "POST":
        amount = float(request.form["amount"])
        if amount <= 0 or amount > balance_of("balance_rub"):
            toast = """<div class="toast err">Недостаточно средств на RUB-счёте ❌</div>"""
        else:
            spend("balance_rub", amount)
            con = sqlite3.connect(DB)
            con.execute("INSERT INTO deposits(user_id,amount,rate,created_at,last_accrual) VALUES(?,?,?,?,?)",
                        (session["uid"], amount, DEPOSIT_RATE, now(), now()))
            con.commit(); con.close()
            add_tx("out", "RUB", amount, "Открытие вклада", f"{DEPOSIT_RATE}% годовых")
            notify(f"Открыт вклад на {fmt(amount)} ₽ под {DEPOSIT_RATE}% годовых 🏦", "📈")
            toast = f"""<div class="toast">🏦 Вклад открыт! Проценты начисляются ежедневно 📈</div>"""
    con = sqlite3.connect(DB)
    ds = con.execute("SELECT id,amount,rate,created_at FROM deposits WHERE user_id=?", (session["uid"],)).fetchall()
    con.close()
    rows = "".join(
        f"""<div class="tx"><div class="ic">🏦</div><div>Вклад от {d[3][:10]}<div class="muted">{d[2]}% годовых · ежедневное начисление</div></div>
        <div class="amt in">{fmt(d[1])} ₽</div></div>""" for d in ds) or '<p class="muted">Вкладов пока нет — открой первый и зарабатывай 📈</p>'
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card">
<span class="pill">+{DEPOSIT_RATE}% ГОДОВЫХ</span>
<h2 style="margin:14px 0 18px">Накопительный вклад 📈</h2>
<form method="post">
<label>Сумма вклада, ₽</label>
<input name="amount" type="number" step="1" min="100" placeholder="100 000" required>
<button class="btn">Открыть вклад 🔒</button>
</form>
<p class="muted" style="margin-top:14px">💡 Проценты начисляются автоматически каждый день при входе в банк. Досрочное закрытие — в любой момент без потери уже начисленного.</p>
</div>
<div class="card"><h3 style="margin-bottom:10px">Мои вклады 🏦</h3>{rows}</div></div>"""
    return page("Вклад", body, "deposit")

# ----------------------------- КРЕДИТНЫЙ КАЛЬКУЛЯТОР -----------------------------

@app.route("/loan")
@login_required
def loan():
    body = """
<div class="card" style="max-width:620px;margin:0 auto">
<span class="pill">СТАВКА ОТ 12% ГОДОВЫХ</span>
<h2 style="margin:14px 0 18px">Кредитный калькулятор 🧮</h2>
<label>Сумма кредита, ₽</label>
<input id="la" type="number" value="500000" min="1000" oninput="calc()">
<label>Срок, месяцев</label>
<input id="lm" type="number" value="12" min="1" max="60" oninput="calc()">
<label>Ставка, % годовых</label>
<input id="lr" type="number" value="12" min="1" max="100" step="0.1" oninput="calc()">
<div class="shine-line"></div>
<table>
<tr><td class="muted">Ежемесячный платёж</td><td style="text-align:right"><b id="mp" style="color:#ffd76a;font-size:20px">—</b></td></tr>
<tr><td class="muted">Переплата всего</td><td style="text-align:right"><b id="ov" style="color:#f87171">—</b></td></tr>
<tr><td class="muted">Общая выплата</td><td style="text-align:right"><b id="tt">—</b></td></tr>
</table>
<p class="muted" style="margin-top:16px">💡 Калькулятор справочный. Оформление кредита появится в следующих версиях.</p>
</div>
<script>
function calc(){
 const A=+document.getElementById('la').value||0, n=+document.getElementById('lm').value||1, r=(+document.getElementById('lr').value||0)/1200;
 if(A>0&&r>0){
  const mp=A*r/(1-Math.pow(1+r,-n));
  document.getElementById('mp').textContent=mp.toLocaleString('ru-RU',{maximumFractionDigits:0})+' ₽';
  document.getElementById('ov').textContent=((mp*n-A).toLocaleString('ru-RU',{maximumFractionDigits:0}))+' ₽';
  document.getElementById('tt').textContent=(mp*n).toLocaleString('ru-RU',{maximumFractionDigits:0})+' ₽';
 }else{
  document.getElementById('mp').textContent='—';
  document.getElementById('ov').textContent='—';
  document.getElementById('tt').textContent='—';}}
calc();
</script>"""
    return page("Кредит", body, "loan")

# ----------------------------- ЦЕЛИ -----------------------------

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    toast = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            name = request.form["name"].strip()
            target = float(request.form["target"])
            if name and target > 0:
                con = sqlite3.connect(DB)
                con.execute("INSERT INTO goals(user_id,name,target,saved) VALUES(?,?,?,0)", (session["uid"], name, target))
                con.commit(); con.close()
                notify(f"Создана новая цель «{name}» 🎯", "🎯")
                toast = f"""<div class="toast">✅ Цель «{name}» создана!</div>"""
        elif action == "add":
            gid = request.form["gid"]
            amount = float(request.form["amount"])
            con = sqlite3.connect(DB)
            g = con.execute("SELECT target,saved FROM goals WHERE id=? AND user_id=?", (gid, session["uid"])).fetchone()
            if g and 0 < amount <= balance_of("balance_rub"):
                saved = min(g[1] + amount, g[0])
                con.execute("UPDATE goals SET saved=? WHERE id=?", (saved, gid))
                con.commit(); con.close()
                spend("balance_rub", amount)
                add_tx("out", "RUB", amount, "Пополнение цели", f"Цель #{gid}")
                if saved >= g[0]:
                    notify(f"🎉 Цель достигнута! Собрано {fmt(g[0])} ₽", "🏆")
                    toast = """<div class="toast">🏆 Поздравляем! Цель достигнута!</div>"""
                else:
                    toast = f"""<div class="toast">✅ Внесено {fmt(amount)} ₽ на цель!</div>"""
            else:
                con.close()
                toast = """<div class="toast err">Недостаточно средств ❌</div>"""
    con = sqlite3.connect(DB)
    gs = con.execute("SELECT id,name,target,saved FROM goals WHERE user_id=?", (session["uid"],)).fetchall()
    con.close()
    cards = "".join(
        f"""<div class="card" style="animation:pageIn .5s both">
        <div style="display:flex;justify-content:space-between;align-items:center">
        <b>🎯 {g[1]}</b>{'<span class="pill">ДОСТИГНУТО 🏆</span>' if g[3]>=g[2] else ''}</div>
        <div style="display:flex;justify-content:space-between;margin-top:10px">
        <span class="muted">Накоплено</span><b>{fmt(g[3])} / {fmt(g[2])} ₽</b></div>
        <div class="progress"><i style="width:{min(100,g[3]/g[2]*100):.0f}%"></i></div>
        <form method="post" style="display:flex;gap:10px;margin-top:16px;align-items:center">
        <input type="hidden" name="action" value="add"><input type="hidden" name="gid" value="{g[0]}">
        <input name="amount" type="number" step="0.01" min="1" placeholder="Сумма ₽" style="margin:0;flex:1">
        <button class="btn btn-sm" style="margin:0">Внести</button></form></div>"""
        for g in gs) or '<div class="card"><p class="muted">Целей пока нет — создайте первую ниже 👇</p></div>'
    body = f"""
{toast}
<div class="grid grid-2">
<div class="grid">{cards}</div>
<div class="card" style="align-self:start">
<h3 style="margin-bottom:16px">Новая цель ✨</h3>
<form method="post">
<input type="hidden" name="action" value="create">
<label>Название цели</label>
<input name="name" placeholder="Например: MacBook Pro 💻" required>
<label>Сумма, ₽</label>
<input name="target" type="number" step="1" min="100" placeholder="300 000" required>
<button class="btn">Создать цель 🎯</button>
</form></div></div>"""
    return page("Цели", body, "goals")

# ----------------------------- ИСТОРИЯ + ПОИСК + ЭКСПОРТ -----------------------------

@app.route("/history")
@login_required
def history():
    f = request.args.get("f", "all")
    q = request.args.get("q", "").strip()
    con = sqlite3.connect(DB)
    base = "SELECT type,currency,amount,counterparty,comment,status,created_at FROM transactions WHERE user_id=?"
    params = [session["uid"]]
    if f in ("in", "out"):
        base += " AND type=?"; params.append(f)
    if q:
        base += " AND (counterparty LIKE ? OR comment LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    txs = con.execute(base + " ORDER BY id DESC LIMIT 200", params).fetchall()
    con.close()
    def tab(name, val):
        return f'<a href="/history?f={val}&q={q}" class="btn btn-sm" style="{"background:linear-gradient(135deg,#ffd76a,#e9b949);color:#1a1300" if f==val else ""}">{name}</a>'
    rows = "".join(
        f"""<div class="tx"><div class="ic">{'💸' if t[0]=='out' else '💰'}</div>
        <div><div>{t[3]} <span class="muted">· {t[4]}</span></div>
        <div class="muted">{t[6]} · {t[1]} · <span style="color:#4ade80">{t[5]}</span></div></div>
        <div class="amt {'out' if t[0]=='out' else 'in'}">{('-' if t[0]=='out' else '+')}{fmt(t[2])} {CUR_SYM[t[1]]}</div></div>"""
        for t in txs) or '<p class="muted" style="padding:16px 0">Ничего не найдено.</p>'
    body = f"""<div class="card">
<div style="display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
<h2 style="margin-right:auto">История операций 📜</h2>
{tab('Все','all')}{tab('Поступления','in')}{tab('Списания','out')}</div>
<form method="get" style="display:flex;gap:10px;margin-bottom:14px">
<input type="hidden" name="f" value="{f}">
<input name="q" value="{q}" placeholder="🔍 Поиск по названию или комментарию..." style="margin:0;flex:1">
<button class="btn btn-sm" style="margin:0">Найти</button>
<a href="/history/export" class="btn btn-sm" style="margin:0;background:rgba(255,255,255,.07);color:#dfe5f5;box-shadow:none">📥 CSV</a>
</form>{rows}</div>"""
    return page("История", body, "history")

@app.route("/history/export")
@login_required
def history_export():
    con = sqlite3.connect(DB)
    txs = con.execute("SELECT type,currency,amount,counterparty,comment,status,created_at FROM transactions WHERE user_id=? ORDER BY id DESC", (session["uid"],)).fetchall()
    con.close()
    out = io.StringIO()
    out.write("Тип;Валюта;Сумма;Контрагент;Комментарий;Статус;Дата\n")
    for t in txs:
        out.write(f"{'Списание' if t[0]=='out' else 'Поступление'};{t[1]};{t[2]};{t[3]};{t[4]};{t[5]};{t[6]}\n")
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=toxirov_history.csv"})

# ----------------------------- УВЕДОМЛЕНИЯ -----------------------------

@app.route("/notifications")
@login_required
def notifications():
    con = sqlite3.connect(DB)
    ns = con.execute("SELECT id,icon,text,created_at,read FROM notifications WHERE user_id=? ORDER BY id DESC", (session["uid"],)).fetchall()
    con.execute("UPDATE notifications SET read=1 WHERE user_id=?", (session["uid"],))
    con.commit(); con.close()
    rows = "".join(
        f"""<div class="notif {{'unread' if not n[4] else ''}}"><div class="ic" style="width:40px;height:40px;border-radius:12px;
        display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.07);font-size:18px;flex-shrink:0">{n[1]}</div>
        <div><div>{n[2]}</div><div class="muted">{n[3]}</div></div></div>"""
        for n in ns) or '<p class="muted">Уведомлений нет 🎉</p>'
    return page("Уведомления", f'<div class="card"><h2 style="margin-bottom:12px">🔔 Уведомления</h2>{rows}</div>', "")

# ----------------------------- ПРОФИЛЬ -----------------------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    u = get_user()
    toast = ""
    if request.method == "POST":
        action = request.form.get("action")
        con = sqlite3.connect(DB)
        if action == "profile":
            con.execute("UPDATE users SET name=?, avatar=? WHERE id=?",
                        (request.form["name"].strip(), request.form.get("avatar", u[9]), u[0]))
            con.commit(); con.close()
            toast = """<div class="toast">✅ Профиль обновлён!</div>"""
        elif action == "password":
            if check_password_hash(u[2], request.form["old"]) and len(request.form["new"]) >= 4:
                con.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(request.form["new"]), u[0]))
                con.commit(); con.close()
                notify("Пароль был изменён 🔑", "🔑")
                toast = """<div class="toast">✅ Пароль изменён!</div>"""
            else:
                con.close()
                toast = """<div class="toast err">Неверный старый пароль (или новый короче 4 символов) ❌</div>"""
        elif action == "pin":
            pin = request.form["pin"].strip()
            if pin.isdigit() and len(pin) == 4:
                con.execute("UPDATE users SET pin_hash=? WHERE id=?", (generate_password_hash(pin), u[0]))
                con.commit(); con.close()
                notify("PIN-код обновлён 📟", "📟")
                toast = """<div class="toast">✅ PIN-код обновлён!</div>"""
            else:
                con.close()
                toast = """<div class="toast err">PIN должен состоять из 4 цифр ❌</div>"""
    u = get_user()
    emojis = ["🦅","😎","🦁","🐯","🚀","💎","🤴","⚡"]
    picks = "".join(f"""<label class="avatar pick {'sel' if e==u[9] else ''}">
    <input type="radio" name="avatar" value="{e}" {'checked' if e==u[9] else ''} style="display:none">{e}</label>""" for e in emojis)
    theme_on = session.get("theme", "dark") == "light"
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card" style="text-align:center">
<div class="avatar" style="margin:0 auto">{u[9]}</div>
<h2 style="margin:10px 0 2px">{u[3]}</h2>
<p class="muted">{u[1]} · {u[8]}</p>
<span class="pill" style="margin-top:8px;display:inline-block">ULTRA PREMIUM ✦</span>
<div class="shine-line"></div>
<form method="post" style="text-align:left">
<input type="hidden" name="action" value="profile">
<label>Имя</label><input name="name" value="{u[3]}" required>
<label>Аватар</label>
<div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0 16px">{picks}</div>
<button class="btn">Сохранить изменения 💾</button>
</form></div>
<div class="grid" style="align-content:start">
<div class="card">
<h3 style="margin-bottom:14px">⚙️ Настройки</h3>
<table>
<tr><td>Светлая тема 🌗</td><td style="text-align:right"><a class="switch {{'on' if t}}" href="/toggle_theme?back=/profile"></a></td></tr>
<tr><td>Скрывать баланс 🙈</td><td style="text-align:right"><a class="switch {{'on' if h}}" href="/toggle_balance?back=/profile"></a></td></tr>
<tr><td>Push-уведомления</td><td style="text-align:right"><span class="switch on" onclick="this.classList.toggle('on')"></span></td></tr>
<tr><td>Спецпредложения</td><td style="text-align:right"><span class="switch on" onclick="this.classList.toggle('on')"></span></td></tr>
</table></div>
<div class="card">
<h3 style="margin-bottom:14px">📟 PIN-код быстрого входа</h3>
<form method="post">
<input type="hidden" name="action" value="pin">
<label>Новый PIN (4 цифры)</label>
<input name="pin" type="password" inputmode="numeric" maxlength="4" pattern="\\d{4}" placeholder="••••" required>
<button class="btn">Сохранить PIN 📟</button>
</form></div>
<div class="card">
<h3 style="margin-bottom:14px">🔐 Смена пароля</h3>
<form method="post">
<input type="hidden" name="action" value="password">
<label>Старый пароль</label><input name="old" type="password" required>
<label>Новый пароль</label><input name="new" type="password" required>
<button class="btn">Изменить пароль 🔑</button>
</form></div>
<div class="card">
<h3 style="margin-bottom:10px">💳 Мои карты</h3>
<div class="tx"><div class="ic">💳</div><div>Debit Gold<div class="muted">{u[7]}</div></div>
<span class="pill" style="margin-left:auto">АКТИВНА</span></div>
<div class="tx"><div class="ic">🌍</div><div>Virtual USD<div class="muted">4035 ···· ···· 9001</div></div>
<span class="pill" style="margin-left:auto">АКТИВНА</span></div>
</div></div></div>"""
    return page("Профиль", body, "profile", h=session.get("hide_balance", False), t=theme_on)

# ----------------------------- ПОДДЕРЖКА -----------------------------

@app.route("/support", methods=["GET", "POST"])
@login_required
def support():
    toast = ""
    if request.method == "POST":
        if request.form["msg"].strip():
            notify("Обращение в поддержку принято. Ответим в течение часа 📨", "🎧")
            toast = """<div class="toast">✅ Обращение отправлено! Ответим в течение часа.</div>"""
    faqs = [
        ("Как перевести деньги?", "Перейдите в «Переводы», укажите получателя и сумму. В демо-режиме переводы мгновенные."),
        ("Как работает вклад?", f"Откройте вклад в разделе «Вклад» — проценты {DEPOSIT_RATE}% годовых начисляются автоматически каждый день при входе."),
        ("Что такое кэшбэк?", f"С каждой оплаты услуг возвращаем {int(CASHBACK*100)}% на баланс мгновенно."),
        ("Как войти по PIN?", "На странице входа нажмите «Войти по PIN-коду» и введите 4 цифры. PIN можно сменить в профиле."),
        ("Это настоящий банк?", "Нет, это учебное демо-приложение. Реальных денег здесь нет 💜"),
    ]
    faq_html = "".join(f"""<div class="faq-item"><div class="faq-q">{q}<span>＋</span></div>
    <div class="faq-a"><p>{a}</p></div></div>""" for q, a in faqs)
    body = f"""
{toast}
<div class="grid grid-2">
<div class="card"><h2 style="margin-bottom:14px">🎧 Написать в поддержку</h2>
<form method="post">
<label>Ваше сообщение</label>
<textarea name="msg" rows="4" placeholder="Опишите вопрос..." required></textarea>
<button class="btn">Отправить 📨</button></form></div>
<div class="card"><h2 style="margin-bottom:8px">❓ Частые вопросы</h2>{faq_html}</div></div>"""
    return page("Поддержка", body, "support")

MANIFEST = {
    "name": "Toxirov Bank",
    "short_name": "Toxirov",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0b1020",
    "theme_color": "#0b1020",
    "icons": [
        {"src": "/icon.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon.png", "sizes": "512x512", "type": "image/png"}
    ]
}

SW = """const C='toxirov-v1';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/','/manifest.json','/icon.png'])));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(clients.claim());});
self.addEventListener('fetch',e=>{
 if(e.request.method!=='GET')return;
 e.respondWith(fetch(e.request).then(r=>{const cl=r.clone();caches.open(C).then(c=>c.put(e.request,cl));return r;})
 .catch(()=>caches.match(e.request).then(r=>r||caches.match('/'))));
});"""

@app.route("/manifest.json")
def manifest():
    return Response(json.dumps(MANIFEST), mimetype="application/manifest+json")

@app.route("/sw.js")
def sw():
    return Response(SW, mimetype="application/javascript",
                    headers={"Cache-Control": "no-cache"})

@app.route("/icon.png")
def icon():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png"), "rb") as f:
            return Response(f.read(), mimetype="image/png")
    except FileNotFoundError:
        return Response(status=404)

@app.errorhandler(404)
def not_found(e):
    if "uid" not in session:
        return redirect("/login")
    return page("404", """<div class="card" style="text-align:center;padding:60px">
<div style="font-size:64px">🛰️</div><h2>404 — Страница не найдена</h2>
<p class="muted" style="margin:10px 0 20px">Кажется, вы свернули не туда...</p>
<a href="/" class="btn" style="width:auto;padding:12px 30px">На главную 🏠</a></div>""")

if __name__ == "__main__":
    # host="0.0.0.0" — видно извне; PORT берём из окружения (Render задаёт свой)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
