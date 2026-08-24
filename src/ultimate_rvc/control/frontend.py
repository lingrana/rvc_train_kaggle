"""Self-contained control console served without a frontend build step."""

HTML = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RVC Training Console</title><link rel="icon" type="image/png" href="data:image/png;base64,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">
<style>
:root{--bg:#fafbfc;--card:#fff;--card-hover:#f8f9fa;--border:#e8ecef;--border-light:#f0f2f5;--text:#1a1a2e;--text-dim:#5a6072;--text-muted:#9ca3b0;--accent:#0066ff;--accent2:#6366f1;--accent3:#0ea5e9;--green:#10b981;--green-dim:rgba(16,185,129,.08);--red:#ef4444;--red-dim:rgba(239,68,68,.08);--orange:#f59e0b;--purple:#8b5cf6;--hover:#f0f2f5}
body.dark{--bg:#0a0a0f;--card:#12121a;--card-hover:#1a1a25;--border:#1e1e2a;--border-light:#2a2a3a;--text:#e8e8ed;--text-dim:#9ca3b0;--text-muted:#6b7280;--accent:#4d8eff;--accent2:#818cf8;--accent3:#38bdf8;--green:#34d399;--green-dim:rgba(52,211,153,.1);--red:#f87171;--red-dim:rgba(248,113,113,.1);--orange:#fbbf24;--purple:#a78bfa;--hover:#1a1a25}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Noto Sans SC',Roboto,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;-webkit-font-smoothing:antialiased}
button,input,select{font:inherit;letter-spacing:0}
.nav{position:sticky;top:0;z-index:100;background:rgba(250,251,252,.88);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-bottom:1px solid var(--border);padding:0 32px;height:52px;display:flex;align-items:center;justify-content:space-between}
body.dark .nav{background:rgba(10,10,15,.88)}
.nav-left{display:flex;align-items:center;gap:10px}
.nav-logo{font-size:18px;font-weight:700;letter-spacing:-.3px;color:var(--text)}
.nav-badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:16px;background:var(--green-dim);color:var(--green);font-size:11px;font-weight:600}
.nav-dot{width:5px;height:5px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.nav-right{display:flex;gap:8px;align-items:center}
.nav-btn{padding:6px 12px;border-radius:6px;border:1px solid var(--border);background:transparent;color:var(--text-dim);font-size:12px;font-weight:500;cursor:pointer;transition:all .2s}
.nav-btn:hover{background:var(--card);color:var(--text)}
.theme-btn,.sidebar-toggle{width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--text-dim);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s}
.theme-btn:hover,.sidebar-toggle:hover{background:var(--card);color:var(--text)}
.layout{display:grid;grid-template-columns:1fr 280px;gap:20px;max-width:1100px;margin:0 auto;padding:24px 32px 60px;transition:all .3s}
body.sidebar-hidden .layout{grid-template-columns:minmax(0,736px);justify-content:center}
.main{min-width:0}
.hero{margin-bottom:24px}
.hero h1{font-size:28px;font-weight:700;letter-spacing:-.5px;line-height:1.2;margin-bottom:6px}
.hero p{font-size:14px;color:var(--text-dim);max-width:480px}
.tabs{display:flex;gap:0;margin-bottom:24px;border-bottom:1px solid var(--border)}
.tab{position:relative;padding:10px 18px;font-size:14px;font-weight:500;color:var(--text-muted);cursor:pointer;transition:color .2s;user-select:none}
.tab:hover{color:var(--text-dim)}
.tab.active{color:var(--text);font-weight:600}
.tab.active::after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:var(--text);border-radius:1px}
.tab .tab-num{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:5px;background:var(--border-light);color:var(--text-muted);font-size:10px;font-weight:700;margin-right:6px;transition:all .2s}
.tab.active .tab-num{background:var(--text);color:#fff}
.tab.done .tab-num{background:var(--green-dim);color:var(--green)}
.tab.done .tab-num::after{content:'\2713'}
.tab[data-step="1"] .tab-num::before{content:'1'}.tab[data-step="2"] .tab-num::before{content:'2'}.tab[data-step="3"] .tab-num::before{content:'3'}.tab[data-step="4"] .tab-num::before{content:'4'}
.tab.done .tab-num::before{content:none !important}
.panel{display:none}
.panel.active{display:block}
.section{margin-bottom:24px}
.section-header{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.section-num{font-size:12px;font-weight:700;color:var(--accent);letter-spacing:1px}
.section-title{font-size:12px;font-weight:600;color:var(--text-muted);letter-spacing:.5px;text-transform:uppercase}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:12px;transition:all .2s}
.card:hover{border-color:var(--text-muted)}
.card-grid{display:grid;gap:12px}
.card-grid.c2{grid-template-columns:1fr 1fr}
.card-grid.c3{grid-template-columns:1fr 1fr 1fr}
.row-inline{display:flex;gap:12px;flex-wrap:nowrap;align-items:flex-end}
.row-inline>.field{flex:1;min-width:0}
.field{display:flex;flex-direction:column;gap:4px}
.field-label{font-size:11px;font-weight:600;color:var(--text-muted);letter-spacing:.3px}
.field-input{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 12px;color:var(--text);font-size:13px;outline:none;width:100%;transition:border-color .2s}
.field-input:focus{border-color:var(--accent)}
.field-input:disabled{opacity:.5;cursor:not-allowed}
.sel{position:relative;width:100%}
.sel-btn{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 28px 8px 10px;color:var(--text);font-size:13px;width:100%;cursor:pointer;display:flex;align-items:center;gap:8px;transition:border-color .2s;text-align:left}
.sel-btn:hover{border-color:var(--text-muted)}
.sel-btn .si{font-size:13px;opacity:.6}
.sel-btn .st{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sel-btn .sa{position:absolute;right:10px;top:50%;transform:translateY(-50%);width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;border-top:4px solid var(--text-muted);transition:transform .2s}
.sel-btn.open .sa{transform:translateY(-50%) rotate(180deg)}
.sel-dd{position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:999;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:4px;box-shadow:0 8px 32px rgba(0,0,0,.1);display:none;max-height:200px;overflow-y:auto}
body.dark .sel-dd{box-shadow:0 8px 32px rgba(0,0,0,.4)}
.sel-dd.open{display:block}
.sel-opt{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:6px;font-size:13px;color:var(--text-dim);cursor:pointer;transition:all .12s}
.sel-opt:hover{background:var(--bg);color:var(--text)}
.sel-opt.selected{color:var(--accent);font-weight:600}
.sel-opt .oi{font-size:13px;width:18px;text-align:center;flex-shrink:0}
.sel-opt .ol{flex:1}
.sel-opt .ob{font-size:10px;padding:2px 6px;border-radius:4px;background:var(--bg);color:var(--text-muted)}
.sel-opt .oc{color:var(--accent);font-size:13px;opacity:0}
.sel-opt.selected .oc{opacity:1}
.sel-search{width:100%;padding:8px 10px;border:none;background:var(--bg);color:var(--text);font-size:12px;border-radius:6px;margin-bottom:2px;outline:none}
.sel-search::placeholder{color:var(--text-muted)}
.sel-sep{height:1px;background:var(--border);margin:2px 6px}
.multi .sel-opt{position:relative;padding-left:32px}
.multi .sel-opt::before{content:'';position:absolute;left:10px;top:50%;transform:translateY(-50%);width:16px;height:16px;border-radius:4px;border:1.5px solid var(--border);background:var(--bg);transition:all .12s}
.multi .sel-opt.selected::before{background:var(--accent);border-color:var(--accent)}
.multi .sel-opt.selected::after{content:'\2713';position:absolute;left:13px;top:50%;transform:translateY(-50%);color:#fff;font-size:10px;font-weight:700}
.multi .sel-opt .oi{display:none}
.multi .sel-opt .oc{display:none}
.toggle-row{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px}
.toggle-label{font-size:13px;color:var(--text)}
.toggle{width:36px;height:20px;border-radius:10px;background:var(--border);position:relative;cursor:pointer;transition:background .2s;flex-shrink:0}
.toggle.on{background:var(--accent)}
.toggle::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;transition:transform .2s}
.toggle.on::after{transform:translateX(16px)}
.upload{border:2px dashed var(--border);border-radius:12px;padding:32px 24px;text-align:center;cursor:pointer;transition:all .25s;background:var(--card);margin-bottom:12px}
.upload:hover{border-color:var(--accent);background:var(--card-hover)}
.upload.dragover{border-color:var(--accent3);box-shadow:0 0 24px rgba(14,165,233,.06)}
.upload-icon{width:44px;height:44px;margin:0 auto 10px;border-radius:10px;background:var(--bg);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:20px}
.upload-title{font-size:14px;font-weight:600;margin-bottom:4px}
.upload-hint{font-size:12px;color:var(--text-muted)}
.upload-tags{display:flex;gap:5px;justify-content:center;margin-top:8px;flex-wrap:wrap}
.upload-tag{padding:3px 10px;border-radius:5px;font-size:11px;font-weight:500;background:var(--bg);color:var(--text-muted);border:1px solid var(--border)}
.upload-row{display:flex;align-items:center;gap:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;margin-bottom:6px}
.upload-row strong{flex:1;font-size:13px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar{flex:0 0 120px;height:5px;border-radius:3px;background:var(--border);overflow:hidden;position:relative}
.bar i{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .3s;width:0}
.progress{margin-bottom:12px}
.progress-head{display:flex;justify-content:space-between;margin-bottom:4px}
.progress-model{font-size:13px;font-weight:600}
.progress-pct{font-size:12px;font-weight:600;color:var(--accent)}
.progress-bar{height:5px;border-radius:3px;background:var(--border);overflow:hidden}
.progress-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .5s}
.progress-stats{display:flex;gap:16px;margin-top:6px;font-size:12px;color:var(--text-muted)}
.progress-stats b{color:var(--text);font-weight:600}
@keyframes fadeIn{from{opacity:0;transform:translateY(-2px)}to{opacity:1;transform:none}}
.file-row.playing{background:var(--green-dim)}
.wplayer{display:flex;align-items:center;gap:10px;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:8px;margin:4px 0;width:100%;flex-basis:100%}
.wplay{width:30px;height:30px;border:none;border-radius:50%;background:var(--accent);color:#fff;font-size:12px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;flex-shrink:0}
.wplay:hover{transform:scale(1.08);opacity:.9}
.wwave{position:relative;flex:1;height:32px;cursor:pointer;overflow:hidden}
.wwave-bars{position:absolute;inset:0;display:flex;align-items:center;gap:2px;padding:0 2px}
.wwave-bars i{width:3px;border-radius:2px;background:var(--border-light);flex:none}
.wwave-fill{position:absolute;left:0;top:0;bottom:0;width:0;overflow:hidden;transition:width .2s linear}
.wwave-fill .wwave-bars i{background:linear-gradient(180deg,var(--accent),var(--accent2))}
.wtime{font-size:11px;color:var(--text-muted);font-variant-numeric:tabular-nums;white-space:nowrap;flex-shrink:0}
.wplaying{animation:wavePulse 1s ease-in-out infinite alternate}
@keyframes wavePulse{from{box-shadow:0 0 0 0 rgba(0,102,255,.35)}to{box-shadow:0 0 0 6px rgba(0,102,255,0)}}
.log{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-family:'SF Mono','JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);line-height:1.6;max-height:80px;overflow-y:auto;margin-top:8px}
.btns{display:flex;gap:8px;margin-top:16px}
.btn{padding:8px 0;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;text-align:center}
.btn-ghost{flex:1;background:var(--bg);color:var(--text-dim);border:1px solid var(--border)}
.btn-ghost:hover{background:var(--border);color:var(--text)}
.btn-primary{flex:1.5;background:var(--text);color:#fff}
body.dark .btn-primary{background:#fff;color:#000}
.btn-primary:hover{opacity:.9;transform:translateY(-1px)}
.btn-danger{flex:1.5;background:var(--red);color:#fff}
.btn-danger:hover{opacity:.9}
.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}
.output{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--text-muted);min-height:36px;display:flex;align-items:center;flex:2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.output.ok{color:var(--green);border-color:var(--green)}
.output.err{color:var(--red);border-color:var(--red)}
.sidebar{position:sticky;top:68px;align-self:start;transition:all .3s;overflow:hidden}
.sidebar.hidden{display:none}
.side-card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:12px}
.side-title{font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:12px}
.side-info{display:flex;flex-direction:column;gap:8px}
.side-row{display:flex;justify-content:space-between;font-size:12px}
.side-row span:first-child{color:var(--text-muted)}
.side-row span:last-child{font-weight:600;color:var(--text)}
.dl-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.dl-card{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:14px 10px;text-align:center;transition:all .2s}
.dl-card:hover{border-color:var(--accent);transform:translateY(-1px)}
.dl-icon{width:40px;height:40px;border-radius:10px;margin:0 auto 8px;display:flex;align-items:center;justify-content:center;font-size:20px;background:var(--card);border:1px solid var(--border)}
.dl-name{font-size:12px;font-weight:700;margin-bottom:2px}
.dl-meta{font-size:10px;color:var(--text-muted);margin-bottom:8px}
.dl-btn{display:inline-block;padding:6px 14px;border-radius:6px;border:none;font-size:11px;font-weight:600;cursor:pointer;transition:all .2s;background:var(--text);color:#fff;text-decoration:none}
body.dark .dl-btn{background:#fff;color:#000}
.dl-btn:hover{opacity:.9}
.dl-all{margin-top:10px;text-align:center}
.dl-all-btn{width:100%;padding:8px;border-radius:8px;border:none;font-size:12px;font-weight:600;cursor:pointer;background:var(--text);color:#fff;transition:all .2s;text-decoration:none;display:inline-block}
body.dark .dl-all-btn{background:#fff;color:#000}
.dl-all-btn:hover{opacity:.9}
.collapse{border:1px solid var(--border);border-radius:10px;margin-bottom:12px;overflow:visible}
.collapse-head{padding:10px 14px;background:var(--card);display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none;font-size:13px;font-weight:600;color:var(--text-dim)}
.collapse-head .arrow{transition:transform .2s;font-size:10px;color:var(--text-muted)}
.collapse-head.open .arrow{transform:rotate(90deg)}
.collapse-body{padding:14px;display:none}
.collapse-body.open{display:block}
.history{background:var(--bg);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-top:10px}
.history-row{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px}
.history-row:last-child{border-bottom:none}
.history-icon{font-size:14px}
.history-name{flex:1;font-weight:500}
.history-phase{color:var(--text-muted);font-size:11px}
.history-dl{color:var(--accent);font-size:11px;font-weight:600;cursor:pointer;text-decoration:none}
.history-dl:hover{text-decoration:underline}
.notice{padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;display:none;background:var(--red-dim);border:1px solid rgba(239,68,68,.12);color:var(--red)}
.notice.show{display:block}
.empty{padding:20px;text-align:center;color:var(--text-muted);font-size:13px}
.login{position:fixed;inset:0;z-index:200;background:var(--bg);display:flex;align-items:center;justify-content:center}
.login.hidden{display:none}
.kaggle-setup{position:fixed;inset:0;z-index:190;background:rgba(10,10,15,.72);display:flex;align-items:center;justify-content:center;padding:20px}
.kaggle-setup.hidden{display:none}
.resume-picker{position:fixed;inset:0;z-index:195;background:rgba(10,10,15,.72);display:flex;align-items:center;justify-content:center;padding:20px}
.resume-picker.hidden{display:none}
.resume-picker-box{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:24px;width:min(560px,100%);max-height:min(680px,90vh);display:flex;flex-direction:column}
.resume-picker-box h2{font-size:20px;margin-bottom:6px}.resume-picker-copy{font-size:13px;color:var(--text-dim);margin-bottom:14px}.resume-list{overflow:auto;display:flex;flex-direction:column;gap:8px;min-height:80px}.resume-item{border:1px solid var(--border);border-radius:10px;background:var(--bg);padding:12px;text-align:left;cursor:pointer;color:var(--text);transition:border-color .2s,background .2s}.resume-item:hover{border-color:var(--accent);background:var(--card-hover)}.resume-item.selected{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent);background:var(--card-hover)}.resume-item strong{display:block;font-size:13px}.resume-item small{display:block;color:var(--text-muted);font-size:11px;margin-top:3px}.resume-empty{padding:24px;text-align:center;color:var(--text-muted);font-size:13px}#resume-error{color:var(--red);font-size:12px;min-height:18px;margin-top:8px}
.login-box{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:40px;width:360px;text-align:center}
.login-box h1{font-size:22px;font-weight:700;margin-bottom:24px;color:var(--text)}
.login-box h2{font-size:20px;font-weight:700;margin-bottom:8px;color:var(--text)}
.login-box .setup-copy{font-size:13px;color:var(--text-dim);text-align:left;margin-bottom:16px}
.login-box .setup-warning{font-size:12px;color:var(--orange);text-align:left;margin:0 0 16px}
.login-box input{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:8px;background:var(--bg);color:var(--text);font-size:14px;outline:none;margin-bottom:12px;transition:border-color .2s}
.login-box input:focus{border-color:var(--accent)}
.login-box .btn-primary{width:100%;padding:12px;margin-top:4px}
#login-error{color:var(--red);font-size:13px;margin-top:12px;min-height:20px}
footer{max-width:1100px;margin:0 auto;padding:0 32px 48px;text-align:center}
footer a{font-size:12px;color:var(--text-muted);text-decoration:none;transition:color .2s}
footer a:hover{color:var(--accent)}
@media(max-width:768px){.layout{grid-template-columns:1fr;padding:16px}.sidebar{display:none}.card-grid.c3{grid-template-columns:1fr}.nav{padding:0 16px}.tabs{overflow-x:auto}}
</style></head><body>

<div class="login" id="login"><form class="login-box" id="login-form"><h1>RVC Training Console</h1><input id="user" value="rvc" autocomplete="username" placeholder="用户名"><input id="password" type="password" autocomplete="current-password" placeholder="密码"><button class="btn btn-primary" type="submit">登录</button><p id="login-error"></p></form></div>

<div class="kaggle-setup hidden" id="kaggle-setup"><form class="login-box" id="kaggle-form"><h2 id="kaggle-title">Kaggle Access Token</h2><p class="setup-copy" id="kaggle-copy">输入新版 Kaggle API Token，用于私有模型持久化和跨 Session 续训。Token 仅保留在当前服务进程中。</p><input id="kaggle-token" type="password" autocomplete="off" placeholder="可留空"><p class="setup-warning" id="kaggle-warning">不输入仍可训练和浏览器下载，但不能上传私有模型、保存跨 Session checkpoint 或恢复私有 Dataset。</p><div class="btns"><button class="btn btn-ghost" id="skip-kaggle" type="button">暂不配置</button><button class="btn btn-primary" id="kaggle-submit" type="submit">验证并启用</button></div><p id="kaggle-error"></p></form></div>
<div class="resume-picker hidden" id="resume-picker"><div class="resume-picker-box"><h2>选择恢复模型</h2><p class="resume-picker-copy">选择一个恢复 Dataset，然后点击确认恢复。</p><div class="resume-list" id="resume-list"><div class="resume-empty">正在读取 Dataset...</div></div><div class="btns"><button class="btn btn-ghost" id="resume-cancel" type="button">取消</button><button class="btn btn-primary" id="resume-confirm" type="button" disabled>确认恢复</button></div><p id="resume-error"></p></div></div>

<nav class="nav">
  <div class="nav-left">
    <span class="nav-logo">RVC Training</span>
    <span class="nav-badge"><span class="nav-dot"></span><span id="gpu-info">加载中...</span></span>
  </div>
  <div class="nav-right">
    <button class="nav-btn" id="kaggle-settings">Kaggle</button><span id="kaggle-owner" style="font-size:11px;color:var(--text-muted);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
    <button class="nav-btn" id="resume-history" disabled>恢复历史</button>
    <button class="theme-btn" onclick="toggleTheme()" title="切换主题" id="theme-btn">☀️</button>
    <button class="sidebar-toggle" onclick="toggleSidebar()" title="切换侧栏">📊</button>
    <button class="nav-btn" id="logout">退出</button>
  </div>
</nav>

<div class="layout">
<div class="main">
  <div class="hero" style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap">
    <div><h1>RVC 语音模型训练</h1><p>独立任务进程 · 断线自动恢复 · RVC v2 48k</p></div>
    <div class="field" style="width:240px">
      <div class="field-label">当前模型</div>
      <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🧩</span><span class="st">选择模型...</span><span class="sa"></span></div>
        <div class="sel-dd" id="model-options"></div></div>
    </div>
  </div>
  <div id="notice" class="notice"></div>

  <div class="tabs">
    <div class="tab active" data-step="1" onclick="switchTab(1)"><span class="tab-num"></span>数据上传</div>
    <div class="tab" data-step="2" onclick="switchTab(2)"><span class="tab-num"></span>数据预处理</div>
    <div class="tab" data-step="3" onclick="switchTab(3)"><span class="tab-num"></span>特征提取</div>
    <div class="tab" data-step="4" onclick="switchTab(4)"><span class="tab-num"></span>模型训练</div>
  </div>

  <!-- ═══════ 步骤 1 ═══════ -->
  <div class="panel active" data-step="1">
    <div class="section">
      <div class="section-header"><span class="section-num">01</span><span class="section-title">数据集配置</span></div>
      <div class="card">
        <div class="row-inline">
          <div class="field"><div class="field-label">数据集类型</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">📂</span><span class="st">新建数据集</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'dataset-type')" data-value="new"><span class="oi">🆕</span><span class="ol">新建数据集</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'dataset-type')" data-value="existing"><span class="oi">📂</span><span class="ol">现有数据集</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field" id="dataset-new-wrap"><div class="field-label">数据集名称</div><input class="field-input" id="dataset" value="MyDataset"></div>
          <div class="field" id="dataset-existing-wrap" style="display:none"><div class="field-label">选择数据集</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🎵</span><span class="st">暂无数据集</span><span class="sa"></span></div>
              <div class="sel-dd" id="dataset-options"></div></div>
          </div>
          <button class="btn btn-primary" id="dataset-confirm" style="flex:none;padding:8px 24px" onclick="confirmDataset()">确定</button>
        </div>
      </div>
    </div>

    <div class="section" id="upload-section">
      <div class="section-header"><span class="section-num">02</span><span class="section-title">上传音频</span></div>
      <div class="upload" id="upload-zone" onclick="pickFiles()">
        <div class="upload-icon">🎙️</div>
        <div class="upload-title">拖拽音频文件到此处，或点击选择</div>
        <div class="upload-hint">支持批量上传 · 单文件最大 2 GB</div>
        <div class="upload-tags"><span class="upload-tag">.wav</span><span class="upload-tag">.mp3</span><span class="upload-tag">.flac</span><span class="upload-tag">.ogg</span><span class="upload-tag">.m4a</span><span class="upload-tag">.aac</span></div>
      </div>
      <input type="file" id="file-input" multiple accept="audio/*" style="display:none">
      <div id="uploads"></div>
      <div id="upload-tip" class="tip" style="display:none"></div>
    </div>

    <div class="section">
      <div class="section-header"><span class="section-num">03</span><span class="section-title">数据集文件</span></div>
      <div class="card" style="margin-bottom:0">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span style="font-size:12px;font-weight:600;color:var(--text-muted)">点击文件播放预览</span>
          <span id="file-count" style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg);color:var(--text-muted)">0 个音频</span>
        </div>
        <div id="file-list" style="max-height:240px;overflow-y:auto"><div style="padding:12px;color:var(--text-muted);font-size:12px">选择数据集后显示文件列表</div></div>
      </div>
    </div>
  </div>

  <!-- ═══════ 步骤 2 ═══════ -->
  <div class="panel" data-step="2">
    <div class="section">
      <div class="section-header"><span class="section-num">01</span><span class="section-title">预处理选项</span></div>
      <div class="card">
        <div class="card-grid c3">
          <div class="field"><div class="field-label">采样率</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">📊</span><span class="st">48000 Hz</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'sample-rate')" data-value="48000"><span class="oi">📊</span><span class="ol">48000 Hz</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'sample-rate')" data-value="40000"><span class="oi">📊</span><span class="ol">40000 Hz</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'sample-rate')" data-value="32000"><span class="oi">📊</span><span class="ol">32000 Hz</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">归一化模式</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">⚖️</span><span class="st">Post</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'normalization')" data-value="post"><span class="oi">⬇️</span><span class="ol">Post</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'normalization')" data-value="pre"><span class="oi">⬆️</span><span class="ol">Pre</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'normalization')" data-value="none"><span class="oi">🚫</span><span class="ol">None</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">音频分割</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">✂️</span><span class="st">自动</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'split')" data-value="Automatic"><span class="oi">🤖</span><span class="ol">自动</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'split')" data-value="Simple"><span class="oi">✂️</span><span class="ol">简单</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'split')" data-value="Skip"><span class="oi">⏭️</span><span class="ol">跳过</span><span class="oc">✓</span></div></div></div>
          </div>
        </div>
        <div class="card-grid c3" style="margin-top:12px">
          <div class="field"><div class="field-label">分段长度（秒）</div><input class="field-input" id="chunk" type="number" value="3" step="0.1"></div>
          <div class="field"><div class="field-label">重叠长度（秒）</div><input class="field-input" id="overlap" type="number" value="0.3" step="0.1"></div>
          <div class="field"><div class="field-label">CPU 核心数</div><input class="field-input" id="preprocess-cores" type="number" value="4"></div>
        </div>
        <div class="card-grid c2" style="margin-top:12px">
          <div class="toggle-row"><span class="toggle-label">高通滤波</span><div class="toggle on" data-field="filter-audio" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">音频降噪</span><div class="toggle" data-field="clean-audio" onclick="toggleSwitch(this)"></div></div>
        </div>
        <div class="field" style="margin-top:12px"><div class="field-label">降噪强度</div><input class="field-input" id="clean-strength" type="number" value="0.7" step="0.1" min="0" max="1"></div>
      </div>
    </div>

    <div class="btns">
      <button class="btn btn-ghost" onclick="resetStep1()">重置</button>
      <button class="btn btn-primary" id="preprocess-btn" onclick="submitJob('preprocess')">预处理数据集</button>
      <div class="output" id="preprocess-msg"></div>
    </div>
  </div>

  <!-- ═══════ 步骤 3 ═══════ -->
  <div class="panel" data-step="3">
    <div class="section">
      <div class="section-header"><span class="section-num">01</span><span class="section-title">提取配置</span></div>
      <div class="card-grid c3">
          <div class="field"><div class="field-label">F0 提取方法</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🔬</span><span class="st">RMVPE</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'f0-method')" data-value="rmvpe"><span class="oi">🔬</span><span class="ol">RMVPE</span><span class="ob">推荐</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'f0-method')" data-value="pm"><span class="oi">📡</span><span class="ol">PM</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">嵌入模型</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🧠</span><span class="st">HuBERT Base</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'embedder')" data-value="local-hubert-base"><span class="oi">🧠</span><span class="ol">HuBERT Base（最新）</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'embedder')" data-value="contentvec"><span class="oi">🧠</span><span class="ol">ContentVec</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'embedder')" data-value="custom"><span class="oi">🔧</span><span class="ol">自定义</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field" id="custom-embedder-wrap" style="display:none"><div class="field-label">自定义嵌入模型</div><input class="field-input" id="custom-embedder"></div>
          <div class="field"><div class="field-label">包含静音数</div><input class="field-input" id="mutes" type="number" value="2" min="0" max="10"></div>
        </div>
      </div>

    <div class="btns">
      <button class="btn btn-ghost" onclick="resetStep2()">重置</button>
      <button class="btn btn-primary" id="extract-btn" onclick="submitJob('extract')">提取特征</button>
      <div class="output" id="extract-msg"></div>
    </div>
  </div>

  <!-- ═══════ 步骤 4 ═══════ -->
  <div class="panel" data-step="4">
    <div class="section">
      <div class="section-header"><span class="section-num">01</span><span class="section-title">基础配置</span></div>
      <div class="card">
        <div class="card-grid c3">
          <div class="field"><div class="field-label">模型版本</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🏷️</span><span class="st">RVC v2</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'version')" data-value="v2"><span class="oi">🏷️</span><span class="ol">RVC v2</span><span class="ob">推荐</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">训练轮数</div><input class="field-input" id="epochs" type="number" value="300" min="1" max="1000"></div>
          <div class="field"><div class="field-label">每张 GPU 批次</div><input class="field-input" id="batch" type="number" value="8" min="1" max="64"></div>
        </div>
        <div class="card-grid c2" style="margin-top:12px">
          <div class="toggle-row"><span class="toggle-label">F0 音高引导</span><div class="toggle on" data-field="f0-guidance" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">过拟合检测</span><div class="toggle on" data-field="detect-overtrain" onclick="toggleSwitch(this)"></div></div>
        </div>
        <div class="card-grid c2" style="margin-top:12px">
          <div class="field"><div class="field-label">保存间隔</div><input class="field-input" id="save" type="number" value="25" min="1" max="100"></div>
          <div class="field"><div class="field-label">过拟合阈值</div><input class="field-input" id="overtrain-threshold" type="number" value="50"></div>
        </div>
      </div>
    </div>

    <div class="collapse">
      <div class="collapse-head" onclick="accToggle(this)"><span>⚙️ 算法与底模</span><span class="arrow">▶</span></div>
      <div class="collapse-body">
        <div class="card-grid c3">
          <div class="field"><div class="field-label">声码器</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🎵</span><span class="st">HiFi-GAN</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'vocoder')" data-value="HiFi-GAN"><span class="oi">🎵</span><span class="ol">HiFi-GAN</span><span class="ob">默认</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">索引算法</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🔍</span><span class="st">Faiss</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'index')" data-value="Faiss"><span class="oi">🔍</span><span class="ol">Faiss</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'index')" data-value="Auto"><span class="oi">🤖</span><span class="ol">Auto</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'index')" data-value="KMeans"><span class="oi">📐</span><span class="ol">KMeans</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">预训练模型</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">📦</span><span class="st">Default</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'pretrained')" data-value="Default"><span class="oi">📦</span><span class="ol">Default</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'pretrained')" data-value="Custom"><span class="oi">🔧</span><span class="ol">Custom</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'pretrained')" data-value="None"><span class="oi">🚫</span><span class="ol">None</span><span class="oc">✓</span></div></div></div>
          </div>
        </div>
        <div class="field" id="custom-pretrained-wrap" style="display:none;margin-top:12px"><div class="field-label">自定义预训练模型</div><input class="field-input" id="custom-pretrained"></div>
      </div>
    </div>

    <div class="collapse">
      <div class="collapse-head" onclick="accToggle(this)"><span>⚙️ 保存与上传</span><span class="arrow">▶</span></div>
      <div class="collapse-body">
        <div class="card-grid c2">
          <div class="field" id="upload-name-wrap" style="display:none"><div class="field-label">上传模型名称</div><input class="field-input" id="upload-name"></div>
        </div>
        <div class="card-grid c2" style="margin-top:12px">
          <div class="toggle-row"><span class="toggle-label">保存全部检查点</span><div class="toggle" data-field="save-checkpoints" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">保存全部权重</span><div class="toggle" data-field="save-weights" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">清除已保存数据</span><div class="toggle" data-field="clear-data" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">上传语音模型</span><div class="toggle" data-field="upload-model" onclick="toggleSwitch(this)"></div></div>
        </div>
      </div>
    </div>

    <div class="collapse">
      <div class="collapse-head" onclick="accToggle(this)"><span>⚙️ 设备与精度</span><span class="arrow">▶</span></div>
      <div class="collapse-body">
        <div class="card-grid c3">
          <div class="field"><div class="field-label">硬件加速</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">⚡</span><span class="st">GPU</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'training-device')" data-value="GPU"><span class="oi">⚡</span><span class="ol">GPU</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'training-device')" data-value="Automatic"><span class="oi">🤖</span><span class="ol">自动</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'training-device')" data-value="CPU"><span class="oi">💻</span><span class="ol">CPU</span><span class="oc">✓</span></div></div></div>
          </div>
          <div class="field"><div class="field-label">GPU 选择</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">⚡</span><span class="st">选择 GPU...</span><span class="sa"></span></div>
              <div class="sel-dd" id="training-gpu-options"></div></div>
            <input type="hidden" id="training-gpus" value="0"></div>
          <div class="field"><div class="field-label">训练精度</div>
            <div class="sel"><div class="sel-btn" onclick="selToggle(this)"><span class="si">🔢</span><span class="st">fp32</span><span class="sa"></span></div>
              <div class="sel-dd"><div class="sel-opt selected" onclick="selPick(this,'precision')" data-value="fp32"><span class="oi">🔢</span><span class="ol">fp32</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'precision')" data-value="fp16"><span class="oi">⚡</span><span class="ol">fp16</span><span class="oc">✓</span></div><div class="sel-sep"></div><div class="sel-opt" onclick="selPick(this,'precision')" data-value="bf16"><span class="oi">🔬</span><span class="ol">bf16</span><span class="oc">✓</span></div></div></div>
          </div>
        </div>
        <div class="card-grid c2" style="margin-top:12px">
          <div class="toggle-row"><span class="toggle-label">预加载数据集</span><div class="toggle" data-field="preload" onclick="toggleSwitch(this)"></div></div>
          <div class="toggle-row"><span class="toggle-label">减少显存使用</span><div class="toggle" data-field="reduce-memory" onclick="toggleSwitch(this)"></div></div>
        </div>
      </div>
    </div>

    <div class="btns">
      <button class="btn btn-ghost" onclick="resetStep3()">重置</button>
      <button class="btn btn-primary" id="train-btn" onclick="submitJob('train')">训练模型</button>
      <button class="btn btn-danger" id="stop-btn" style="display:none" onclick="stopJob()">停止训练</button>
      <div class="output" id="train-msg"></div>
    </div>
  </div>

</div>

<!-- ═══════ 右侧栏 ═══════ -->
<div class="sidebar" id="sidebar">
  <div class="side-card">
    <div class="side-title">当前阶段</div>
    <div class="side-info" id="side-model-info"><div style="font-size:12px;color:var(--text-muted)">等待训练任务...</div></div>
  </div>
  <div class="side-card">
    <div class="side-title">训练进度</div>
    <div id="side-stage-card"><div style="font-size:12px;color:var(--text-muted)">尚未选择模型</div></div>
  </div>
  <div class="side-card">
    <div class="side-title">下载文件</div>
    <div id="side-downloads"><div style="font-size:12px;color:var(--text-muted)">暂无可下载文件</div></div>
  </div>
  <div class="side-card">
    <div class="side-title">历史任务</div>
    <div id="side-history"><div style="font-size:12px;color:var(--text-muted)">暂无历史记录</div></div>
  </div>
</div>

</div>

<footer><a href="https://github.com/lingrana/rvc_train_kaggle" target="_blank">© 2026 lingran · 用心打造每一个项目</a></footer>

<script>
const state={etag:'',timer:null,failures:0,connLost:false,lastJobs:[],uploading:false,datasetConfirmed:false,selectedValues:{},gpus:[],registry:{},progressSnap:{},paths:{},kaggleOwner:'',uploadPct:0,uploadActive:false,uploadDone:false,uploadDataset:''};
const $=s=>document.querySelector(s);
const text=(el,v)=>{if(el)el.textContent=v};
function notice(msg){const el=$('#notice');text(el,msg);el.classList.toggle('show',!!msg)}

async function api(url,options={}){const r=await fetch(url,{cache:'no-store',...options});if(r.status===401){$('#login').classList.remove('hidden');throw new Error('请重新登录')}if(!r.ok){let d={};try{d=await r.json()}catch{}throw new Error(typeof d.detail==='string'?d.detail:'请求失败 '+r.status)}return r}

function toggleTheme(){document.body.classList.toggle('dark');$('#theme-btn').textContent=document.body.classList.contains('dark')?'🌙':'☀️'}
function toggleSidebar(){document.body.classList.toggle('sidebar-hidden');$('#sidebar').classList.toggle('hidden')}
function switchTab(n){document.querySelectorAll('.tab').forEach(el=>{el.classList.remove('active');if(parseInt(el.dataset.step)===n)el.classList.add('active')});document.querySelectorAll('.panel').forEach(el=>{el.classList.remove('active');if(parseInt(el.dataset.step)===n)el.classList.add('active')})}
function accToggle(el){el.classList.toggle('open');el.nextElementSibling.classList.toggle('open')}
function toggleSwitch(el){el.classList.toggle('on');const on=el.classList.contains('on');if(el.dataset.field==='detect-overtrain'){const t=$('#overtrain-threshold');if(t)t.disabled=!on}if(el.dataset.field==='f0-guidance'&&!on&&(state.selectedValues['pretrained']||'Default')==='Default'){setSel('pretrained','None')}if(el.dataset.field)onFieldChange(el.dataset.field,on?'on':'off')}
function setSel(fieldId,value){const opt=document.querySelector('.sel-opt[data-value="'+value+'"]');if(opt)selPick(opt,fieldId)}
function setToggle(fieldId,on){const el=$('[data-field="'+fieldId+'"]');if(el){el.classList.toggle('on',on);if(fieldId==='detect-overtrain'){const t=$('#overtrain-threshold');if(t)t.disabled=!on}}}
function resetStep1(){setSel('sample-rate','48000');setSel('normalization','post');setSel('split','Automatic');$('#chunk').value=3;$('#overlap').value=.3;$('#preprocess-cores').value=4;setToggle('filter-audio',true);setToggle('clean-audio',false);$('#clean-strength').value=.7}
function resetStep2(){setSel('f0-method','rmvpe');setSel('embedder','local-hubert-base');$('#custom-embedder').value='';$('#mutes').value=2}
function resetStep3(){setSel('version','v2');$('#epochs').value=300;$('#batch').value=8;setToggle('f0-guidance',true);setToggle('detect-overtrain',true);$('#overtrain-threshold').value=50;$('#save').value=25;setSel('vocoder','HiFi-GAN');setSel('index','Faiss');setSel('pretrained','Default');$('#custom-pretrained').value='';setToggle('save-checkpoints',false);setToggle('save-weights',false);setToggle('clear-data',false);setToggle('upload-model',false);$('#upload-name').value='';$('#upload-name-wrap').style.display='none';setSel('training-device','GPU');setSel('precision','fp32');setToggle('preload',false);setToggle('reduce-memory',false)}

function selToggle(el){const dd=el.nextElementSibling;document.querySelectorAll('.sel-dd.open').forEach(d=>{if(d!==dd)d.classList.remove('open')});document.querySelectorAll('.sel-btn.open').forEach(c=>{if(c!==el)c.classList.remove('open')});el.classList.toggle('open');dd.classList.toggle('open')}
function selPick(opt,fieldId){const wrap=opt.closest('.sel'),btn=wrap.querySelector('.sel-btn');btn.querySelector('.st').textContent=opt.querySelector('.ol').textContent;btn.querySelector('.si').textContent=opt.querySelector('.oi').textContent;wrap.querySelectorAll('.sel-opt').forEach(o=>o.classList.remove('selected'));opt.classList.add('selected');btn.classList.remove('open');wrap.querySelector('.sel-dd').classList.remove('open');if(fieldId)state.selectedValues[fieldId]=opt.dataset.value;onFieldChange(fieldId,opt.dataset.value)}
function selFilter(input){const q=input.value.toLowerCase();input.nextElementSibling.querySelectorAll('.sel-opt').forEach(o=>{o.style.display=o.querySelector('.ol').textContent.toLowerCase().includes(q)?'':'none'})}
function selMulti(opt){opt.classList.toggle('selected');const wrap=opt.closest('.sel');const selected=[...wrap.querySelectorAll('.sel-opt.selected')].map(o=>o.dataset.value);const count=selected.length;wrap.querySelector('.sel-btn').querySelector('.st').textContent=count?selected.map(id=>{const g=state.gpus.find(x=>String(x.id)===id);return g?'GPU '+id+' ('+g.name+')':'GPU '+id}).join(', '):'选择 GPU...';const hidden=wrap.parentElement.querySelector('input[type=hidden]');if(hidden)hidden.value=selected.join(',')}

document.addEventListener('click',e=>{if(!e.target.closest('.sel')){document.querySelectorAll('.sel-dd.open').forEach(d=>d.classList.remove('open'));document.querySelectorAll('.sel-btn.open').forEach(c=>c.classList.remove('open'))}});

function onFieldChange(fieldId,value){
  if(fieldId==='dataset-type'){const isNew=value==='new';$('#dataset-new-wrap').style.display=isNew?'':'none';$('#dataset-existing-wrap').style.display=isNew?'none':'';$('#file-input').disabled=!isNew;if(!isNew){const ds=state.selectedValues['existing-dataset']||'';if(ds)loadFiles(ds)}else{loadFiles($('#dataset').value.trim())}}
  if(fieldId==='existing-dataset'){loadFiles(value)}
  if(fieldId==='embedder'){$('#custom-embedder-wrap').style.display=value==='custom'?'':'none'}
  if(fieldId==='pretrained'){$('#custom-pretrained-wrap').style.display=value==='Custom'?'':'none'}
  if(fieldId==='upload-model'){$('#upload-name-wrap').style.display=value==='on'?'':'none'}
}

async function loadFiles(dataset){
  const el=$('#file-list');
  if(!dataset){el.innerHTML='<div style="padding:12px;color:var(--text-muted);font-size:12px">选择数据集后显示文件列表</div>';return}
  try{
    const d=await(await api('/api/v1/datasets/'+encodeURIComponent(dataset)+'/files')).json();
    const files=d.files||[];
    if(!files.length){el.innerHTML='<div style="padding:12px;color:var(--text-muted);font-size:12px">数据集为空</div>';return}
    const icons={'.wav':'🎵','.flac':'🎶','.mp3':'🔊','.ogg':'🔉','.m4a':'🎧'};
    el.innerHTML=files.map(f=>{
      const size=f.size>1048576?(f.size/1048576).toFixed(1)+' MB':(f.size/1024).toFixed(0)+' KB';
      return'<div class="file-row" onclick="previewAudio(this,\''+d.dataset+'/'+f.name+'\')" style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;cursor:pointer;transition:background .2s" onmouseover="this.style.background=\'var(--hover)\'" onmouseout="this.style.background=\'\'"><span style="font-size:14px">'+(icons[f.ext]||'📄')+'</span><span style="flex:1;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+f.name+'</span><span class="fz-size" style="font-size:11px;color:var(--text-muted)">'+size+'</span></div>'
    }).join('');
    $('#file-count').textContent=files.length+' 个音频';
  }catch(err){el.innerHTML='<div style="padding:12px;color:var(--red);font-size:12px">'+err.message+'</div>'}
}

function previewAudio(row,path){
  if(row.querySelector('.wplayer')){
    const wp=row.querySelector('.wplayer');
    if(wp._audio)wp._audio.pause();
    wp.remove();row.classList.remove('playing');
    return
  }
  document.querySelectorAll('.file-row.playing').forEach(r=>r.classList.remove('playing'));
  document.querySelectorAll('#file-list .wplayer').forEach(w=>w.remove());
  row.classList.add('playing');
  const wrap=document.createElement('div');wrap.className='wplayer';wrap.addEventListener('click',e=>e.stopPropagation());
  wrap.innerHTML='<button class="wplay">▶</button><div class="wwave"><div class="wwave-bars"></div><div class="wwave-fill"><div class="wwave-bars"></div></div></div><span class="wtime">0:00 / --:--</span>';
  const play=wrap.querySelector('.wplay'),wave=wrap.querySelector('.wwave'),time=wrap.querySelector('.wtime');
  const HEIGHTS=[6,12,20,28,16,8,22,30,14,24,10,18,26,12,6,20,30,16,24,8,14,28,10,22,18,6,26,12,20,30,8,16,24,10,28,14,6,18,26,22];
  [wave.firstElementChild,wave.children[1].firstElementChild].forEach(bars=>{bars.innerHTML=HEIGHTS.map(h=>'<i style="height:'+h+'px"></i>').join('')});
  const fill=wave.querySelector('.wwave-fill');
  const audio=new Audio('/api/v1/audio/'+encodeURIComponent(path));
  wrap._audio=audio;
  audio.preload='metadata';
  const fmt=s=>{if(!isFinite(s))return'--:--';s=Math.max(0,Math.floor(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
  audio.addEventListener('loadedmetadata',()=>{time.textContent='0:00 / '+fmt(audio.duration)});
  audio.addEventListener('timeupdate',()=>{if(audio.duration){fill.style.width=(audio.currentTime/audio.duration*100)+'%';time.textContent=fmt(audio.currentTime)+' / '+fmt(audio.duration)}});
  audio.addEventListener('ended',()=>{play.textContent='▶';play.classList.remove('wplaying');fill.style.width='0%'});
  const toggle=()=>{if(audio.paused){audio.play().then(()=>{play.textContent='⏸';play.classList.add('wplaying')}).catch(()=>{play.textContent='▶'})}else{audio.pause();play.textContent='▶';play.classList.remove('wplaying')}};
  play.onclick=toggle;
  wave.onclick=e=>{if(!audio.duration)return;const r=wave.getBoundingClientRect();audio.currentTime=(e.clientX-r.left)/r.width*audio.duration;toggle()};
  row.append(wrap);
}

function selectedDataset(){return state.selectedValues['dataset-type']==='existing'?(state.selectedValues['existing-dataset']||''):($('#dataset').value.trim()||'')}
function confirmDataset(){
  const ds=selectedDataset();
  if(!ds){notice('请先填写数据集名称或选择现有数据集');return}
  const dd=$('#model-options');
  if(dd&&![...dd.querySelectorAll('.sel-opt')].some(o=>o.dataset.value===ds)){
    const opt=document.createElement('div');opt.className='sel-opt';opt.dataset.value=ds;
    opt.onclick=function(){selPick(this,'model')};
    opt.innerHTML='<span class="oi">🧩</span><span class="ol">'+ds+'</span><span class="oc">✓</span>';
    dd.append(opt);
  }
  selectModel('model',ds);
  state.registry[ds]=state.registry[ds]||{stages:{upload:{done:false},preprocess:{done:false},extract:{done:false},train:{done:false}},last_phase:''};
  renderStageCard();
  state.datasetConfirmed=true;
  notice('数据集已确定：'+ds+'，可以上传音频了');
  api('/api/v1/datasets/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:ds})}).then(()=>loadOptions()).catch(()=>{});
}
function checked(fieldId){return $('[data-field="'+fieldId+'"]').classList.contains('on')}
function gpuIds(id){const raw=$(id)?$(id).value:'';return raw.split(',').map(x=>x.trim()).filter(Boolean).map(Number).filter(Number.isInteger)}

function params(kind){const modelName=selectedDataset();if(!modelName)throw new Error('请先确认数据集');return{model_name:modelName,dataset_name:modelName,sample_rate:Number(state.selectedValues['sample-rate']||'48000'),normalization_mode:state.selectedValues['normalization']||'post',filter_audio:checked('filter-audio'),clean_audio:checked('clean-audio'),clean_strength:Number($('#clean-strength').value),split_method:state.selectedValues['split']||'Automatic',chunk_len:Number($('#chunk').value),overlap_len:Number($('#overlap').value),preprocess_cores:Number($('#preprocess-cores').value),f0_method:state.selectedValues['f0-method']||'rmvpe',embedder_model:state.selectedValues['embedder']||'local-hubert-base',custom_embedder_model:$('#custom-embedder')?$('#custom-embedder').value.trim():null,include_mutes:Number($('#mutes').value),extraction_cores:4,extraction_device:'CPU',version:state.selectedValues['version']||'v2',f0_guidance:checked('f0-guidance'),epochs:Number($('#epochs').value),batch_size:Number($('#batch').value),detect_overtraining:checked('detect-overtrain'),overtraining_threshold:Number($('#overtrain-threshold').value),vocoder:state.selectedValues['vocoder']||'HiFi-GAN',index_algorithm:state.selectedValues['index']||'Faiss',pretrained_type:state.selectedValues['pretrained']||'Default',custom_pretrained_model:$('#custom-pretrained')?$('#custom-pretrained').value.trim():null,save_interval:Number($('#save').value),save_all_checkpoints:checked('save-checkpoints'),save_all_weights:checked('save-weights'),clear_saved_data:checked('clear-data'),upload_model:checked('upload-model'),upload_name:$('#upload-name')?$('#upload-name').value.trim():null,training_device:state.selectedValues['training-device']||'GPU',training_gpu_ids:gpuIds('#training-gpus'),precision:state.selectedValues['precision']||'fp32',preload_dataset:checked('preload'),reduce_memory_usage:checked('reduce-memory')}}

async function submitJob(kind){notice('');try{const key=crypto.randomUUID(),jobParams=params(kind);const r=await api('/api/v1/jobs/'+kind,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(jobParams)});const job=await r.json();if(kind==='preprocess'){selectModel('model',job.params.model_name)}if(r.status===409){notice('已有任务正在运行');renderJobs([job,...state.lastJobs.filter(x=>x.id!==job.id)])}else{renderJobs([job,...state.lastJobs.filter(x=>x.id!==job.id)])}}catch(err){notice(err.message)}}

async function stopJob(){const active=state.lastJobs.find(j=>['queued','running','stopping'].includes(j.phase));if(!active)return;try{await api('/api/v1/jobs/'+active.id+'/stop',{method:'POST'})}catch(err){notice(err.message)}}

async function digest(blob){const value=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());return[...new Uint8Array(value)].map(x=>x.toString(16).padStart(2,'0')).join('')}
async function uploadFile(file,dataset,row){const started=await(await api('/api/v1/uploads/direct',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset,filename:file.name,size:file.size})})).json(),xhr=new XMLHttpRequest(),lastReported={v:0};return new Promise((resolve,reject)=>{state.uploadDataset=dataset;state.uploadActive=true;state.uploadDone=false;state.uploadPct=0;renderStageCard();xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.min(100,Math.round(e.loaded/e.total*100)),mb=(e.loaded/1048576).toFixed(1),totalMb=(e.total/1048576).toFixed(1);row.querySelector('i').style.width=pct+'%';text(row.querySelector('.upload-status'),pct>=100?'完成 ✓':pct+'% ('+mb+' MB / '+totalMb+' MB)');row.querySelector('.upload-status').style.color=pct>=100?'var(--green)':'var(--text-muted)';if(pct>state.uploadPct){state.uploadPct=pct;renderStageCard()}if(e.loaded-lastReported.v>262144){lastReported.v=e.loaded;fetch('/api/v1/uploads/direct/'+encodeURIComponent(started.id)+'/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({received:Math.round(e.loaded)})}).catch(()=>{})}}};xhr.onload=()=>{fetch('/api/v1/uploads/direct/'+encodeURIComponent(started.id)+'/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({received:file.size})}).catch(()=>{});if(xhr.status>=200&&xhr.status<300){text(row.querySelector('.upload-status'),'完成 ✓');row.querySelector('.upload-status').style.color='var(--green)';state.uploadPct=100;state.uploadActive=false;state.uploadDone=true;renderStageCard();resolve()}else{state.uploadActive=false;renderStageCard();try{const d=JSON.parse(xhr.responseText);reject(new Error(d.detail||d.message||'上传失败'))}catch{reject(new Error('上传失败'))}}};xhr.onerror=()=>{state.uploadActive=false;renderStageCard();reject(new Error('网络错误'))};xhr.open('PUT','/api/v1/uploads/direct/'+encodeURIComponent(started.id));xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.send(file)})}

$('#upload-zone').addEventListener('dragover',e=>{e.preventDefault();$('#upload-zone').classList.add('dragover')});
$('#upload-zone').addEventListener('dragleave',()=>$('#upload-zone').classList.remove('dragover'));
$('#upload-zone').addEventListener('drop',e=>{e.preventDefault();$('#upload-zone').classList.remove('dragover');handleFiles(e.dataTransfer.files)});
$('#file-input').addEventListener('change',e=>handleFiles(e.target.files));

function pickFiles(){if(!state.datasetConfirmed){notice('请先在上方点击「确定」按钮确认数据集名称');return}const dataset=selectedDataset()||$('#dataset').value.trim();if(!dataset){notice('请先确认数据集名称');return}$('#file-input').click()}
async function handleFiles(files){if(!state.datasetConfirmed){notice('请先在上方点击「确定」按钮确认数据集名称');return}const filesList=[...files],dataset=selectedDataset()||$('#dataset').value.trim();if(!filesList.length)return;if(!dataset){notice('请先确认数据集名称');return}state.uploading=true;notice('');let allOk=true;for(const file of filesList){const row=document.createElement('div');row.className='upload-row';const name=document.createElement('strong');name.textContent=file.name;const bar=document.createElement('div');bar.className='bar';bar.innerHTML='<i></i>';const status=document.createElement('span');status.className='upload-status';status.textContent='上传中';status.style.cssText='font-size:11px;color:var(--text-muted);white-space:nowrap';row.append(name,bar,status);$('#uploads').append(row);try{await uploadFile(file,dataset,row)}catch(err){status.textContent=err.message;status.style.color='var(--red)';allOk=false}}state.uploading=false;if(allOk){const tip=$('#upload-tip');tip.textContent='✅ 已上传 '+filesList.length+' 个文件';tip.style.display='';setTimeout(()=>tip.style.display='none',5000);if(dataset)loadFiles(dataset)}}

const fmt=s=>{s=Math.max(0,Math.round(Number(s)||0));return[Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(x=>String(x).padStart(2,'0')).join(':')};

function renderJobs(jobs){state.lastJobs=jobs;const active=jobs.find(j=>['queued','running','stopping'].includes(j.phase));const completed=jobs.filter(j=>j.phase==='completed');
renderSideModel(active);renderSideDownloads(completed);renderSideHistory(completed);renderStageCard();
['preprocess-btn','extract-btn','train-btn'].forEach(id=>{$('#'+id).disabled=!!active});$('#stop-btn').style.display=active?'':'none'}

function fmtClock(seconds){try{seconds=Math.max(0,Math.round(Number(seconds)))||0}catch{return '--:--'}if(seconds<1)return '不到1秒';const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return h?h+'小时'+m+'分':(m?m+'分'+s+'秒':s+'秒')}
function liveElapsed(live,fallback){const st=Number(live&&live.stage_started_at);if(st>0&&Number.isFinite(st))return Math.max(0,Date.now()/1000-st);const elapsed=Number(live&&live.stage_elapsed_seconds);if(Number.isFinite(elapsed)&&elapsed>=0)return elapsed;return Math.max(0,Number(fallback)||0)}
const PIPELINE_STEPS=[
  {key:'upload',number:1,label:'数据上传'},
  {key:'preprocess',number:2,label:'数据处理'},
  {key:'extract',number:3,label:'特征提取'},
  {key:'train',number:4,label:'模型训练'}
];
const PHASE_VIEW={
  uploading_file:{step:'upload',label:'步骤1 · 上传音频'},
  upload_validating:{step:'upload',label:'步骤1 · 校验文件'},
  upload_completed:{step:'upload',label:'步骤1 · 上传完成'},
  preparing:{step:'preprocess',label:'步骤2 · 准备环境'},
  preprocessing:{step:'preprocess',label:'步骤2 · 数据处理'},
  preprocess_completed:{step:'preprocess',label:'步骤2 · 处理完成'},
  extract_starting:{step:'extract',label:'步骤3 · 准备环境'},
  extracting:{step:'extract',label:'步骤3 · 基频提取'},
  extracting_pitch:{step:'extract',label:'步骤3 · 基频提取'},
  extracting_embed:{step:'extract',label:'步骤3 · 特征提取'},
  extracting_verify:{step:'extract',label:'步骤3 · 特征校验'},
  extract_completed:{step:'extract',label:'步骤3 · 提取完成'},
  starting:{step:'train',label:'步骤4 · 准备环境'},
  training:{step:'train',label:'步骤4 · 模型训练'},
  indexing:{step:'train',label:'步骤4 · 生成索引'},
  validating:{step:'train',label:'步骤4 · 验证模型'},
  uploading:{step:'train',label:'步骤4 · 上传模型'},
  completed:{step:'train',label:'步骤4 · 训练完成'},
  queued:{step:'',label:'等待任务开始'},
  stopping:{step:'',label:'正在停止任务'},
  stopped:{step:'',label:'任务已停止'},
  failed:{step:'',label:'任务执行失败'}
};
const JOB_STEP={preprocess:'preprocess',extract:'extract',train:'train',pipeline:'preprocess'};
const JOB_STAGE_STEP={preprocessing:'preprocess',extracting:'extract',training:'train',uploading:'train'};
const JOB_START_PHASE={preprocess:'preparing',extract:'extract_starting',train:'starting',pipeline:'preparing'};
const JOB_STAGE_PHASE={preprocessing:'preparing',extracting:'extract_starting',training:'starting',uploading:'uploading'};

function emptyStages(){return Object.fromEntries(PIPELINE_STEPS.map(step=>[step.key,{done:false,finished_at:null,elapsed_seconds:null}]))}
function mergeDefined(...sources){const result={};sources.forEach(source=>Object.entries(source||{}).forEach(([key,value])=>{if(value!==undefined&&value!==null)result[key]=value}));return result}
function clampPercent(value){const number=Number(value);return Number.isFinite(number)?Math.max(0,Math.min(100,number)):0}
function modelJob(name){return state.lastJobs.find(job=>job.params&&job.params.model_name===name)||null}
function jobStep(job){return JOB_STAGE_STEP[String((job||{}).stage||'')]||JOB_STEP[String((job||{}).type||'')]||''}
function completedPhase(stages){for(const step of [...PIPELINE_STEPS].reverse()){if(stages[step.key]&&stages[step.key].done)return step.key==='train'?'completed':step.key+'_completed'}return ''}
function currentPhaseLabel(progress,phase){const backend=String(progress.phase_label||'').trim();if(backend&&!['queued','stopping','stopped','failed'].includes(phase))return backend;return (PHASE_VIEW[phase]||{}).label||phase||'等待任务开始'}

function buildStageView(name,preferredJob=null){
  const registry=state.registry[name]||{};
  const job=preferredJob||modelJob(name);
  const saved=state.progressSnap[name]||{};
  const live=(job&&job.progress)||{};
  const jobPhase=String((job&&job.phase)||'');
  const liveUpdated=Number(live.updated_at||0);
  const jobCreated=Number((job&&job.created_at)||0);
  const liveIsCurrent=!job||!jobCreated||liveUpdated>=jobCreated;
  const jobIsActive=['queued','running','stopping'].includes(jobPhase);
  const progress=jobIsActive&&!liveIsCurrent?{}:mergeDefined(saved,liveIsCurrent?live:{});
  const stages={...emptyStages(),...(registry.stages||{}),...((job&&job.stages)||{})};
  let phase=String(progress.phase||'');
  if(jobPhase==='queued')phase='queued';
  else if(jobPhase==='stopping')phase='stopping';
  else if(jobPhase==='stopped'||jobPhase==='failed')phase=jobPhase;
  else if(jobPhase==='running'&&!liveIsCurrent)phase=JOB_STAGE_PHASE[String(job.stage||'')]||JOB_START_PHASE[String(job.type||'')]||'preparing';
  if(!phase)phase=completedPhase(stages);
  let step=(PHASE_VIEW[phase]||{}).step||jobStep(job);
  if(phase==='preparing'&&jobStep(job))step=jobStep(job);
  const error=String(progress.error||(job&&job.error)||'');
  return {name,job,stages,progress,phase,step,label:currentPhaseLabel(progress,phase),percent:phase==='completed'?100:clampPercent(progress.percent),error};
}

function stageFailureStep(view){
  if(!['failed','stopped'].includes(view.phase))return '';
  return view.step||jobStep(view.job)||((PIPELINE_STEPS.find(step=>!(view.stages[step.key]||{}).done)||{}).key||'');
}
function stageRow(step,view){
  const stored=view.stages[step.key]||{};
  const selectedUpload=step.key==='upload'&&state.uploadDataset===view.name;
  if(selectedUpload&&state.uploadActive)return {icon:'⏳',text:'上传音频 · '+Math.round(state.uploadPct)+'%'};
  if(selectedUpload&&state.uploadDone)return {icon:'✅',text:'已上传 '+Math.round(state.uploadPct)+'%'};
  if(stored.done){const clock=stored.finished_at?new Date(stored.finished_at*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'';const text=stored.elapsed_seconds!=null?'已用 '+fmtClock(stored.elapsed_seconds):'完成';return {icon:'✅',text:text+(clock?' · '+clock:'')}}
  const failureStep=stageFailureStep(view);
  if(failureStep===step.key)return {icon:'❌',text:'未完成 · '+(view.phase==='failed'?'已失败':'已停止')};
  if(view.step===step.key&&!['failed','stopped'].includes(view.phase)){
    const fallback=view.job?Date.now()/1000-(Number(view.job.created_at)||Date.now()/1000):0;
    const elapsed=liveElapsed(view.progress,fallback);
    const shortLabel=view.label.replace(/^步骤\d\s*·\s*/,'');
    let text=shortLabel+(view.percent>0?' · '+Math.round(view.percent)+'%':'')+(elapsed>0?' · 已用 '+fmtClock(elapsed):'');
    if(view.progress.stage_detail)text+=' · '+view.progress.stage_detail;
    return {icon:'⏳',text};
  }
  return {icon:'▫️',text:['failed','stopped'].includes(view.phase)?'未开始':'等待开始'};
}

function renderStageCard(){
  const el=$('#side-stage-card');if(!el)return;
  const name=state.selectedValues['model']||'';
  if(!name){el.innerHTML='<div style="font-size:12px;color:var(--text-muted)">尚未选择模型</div>';return}
  const view=buildStageView(name);
  const rows=PIPELINE_STEPS.map(step=>{
    const row=stageRow(step,view);
    return '<div class="side-row"><span>步骤'+step.number+' '+step.label+'</span><span style="color:var(--text-muted);font-weight:400;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+escapeAttr(row.text)+'">'+row.icon+' '+escapeHtml(row.text)+'</span></div>'
  }).join('');
  let extra='';
  if(view.phase==='completed')extra=view.progress.upload_failed?'<div class="side-row"><span>状态</span><span style="color:var(--orange)">⚠️ 训练完成但上传失败</span></div>':'<div class="side-row"><span>状态</span><span style="color:var(--green)">✅ 训练完成</span></div>';
  else if(view.phase==='failed'||view.phase==='stopped'){const errorShown=view.error.slice(0,400);extra='<div class="side-row"><span>状态</span><span style="color:var(--red)">❌ '+(view.phase==='failed'?'任务失败':'已停止')+'</span></div>'+(errorShown?'<div style="font-size:11px;color:var(--red);margin-top:6px;word-break:break-all">'+escapeHtml(errorShown)+'</div>':'')}
  el.innerHTML='<div class="side-info">'+rows+extra+'</div>'
}
function renderSideModel(active){
  const el=$('#side-model-info');
  const name=String((active&&active.params&&active.params.model_name)||state.selectedValues['model']||'');
  if(!name){el.innerHTML='<div style="font-size:12px;color:var(--text-muted)">等待训练任务...</div>';return}
  const view=buildStageView(name,active||null),p=view.progress;
  const fallback=view.job?Date.now()/1000-(Number(view.job.created_at)||Date.now()/1000):0;
  const rows=[['当前阶段',view.label],['当前进度',view.percent.toFixed(1)+'%'],['已用时间',fmt(liveElapsed(p,fallback))]];
  if(p.stage_detail)rows.push(['阶段详情',String(p.stage_detail)]);
  const eta=Number(p.eta_seconds||0);
  if(eta>0)rows.push(['剩余时间',fmt(eta)]);
  if(view.step==='train'&&(Number(p.total_epochs)>0||Number(p.epoch)>0)){
    rows.push(['训练轮次',(p.epoch||0)+' / '+(p.total_epochs||0)]);
    if(p.best_epoch!=null)rows.push(['最佳轮次',p.best_epoch]);
    if(p.best_loss!=null)rows.push(['最佳损失',Number(p.best_loss).toFixed(4)]);
    rows.push(['生成器损失','G '+Number(p.loss_g||0).toFixed(4)]);
    rows.push(['判别器损失','D '+Number(p.loss_d||0).toFixed(4)])
  }
  if(view.error&&view.phase==='failed')rows.push(['错误',view.error.slice(0,400)]);
  el.innerHTML='<div class="side-row" style="margin-bottom:8px"><span>模型名称</span><span style="max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+escapeAttr(name)+'">'+escapeHtml(name)+'</span></div><div class="progress-bar" style="margin:6px 0 10px"><div class="progress-fill" style="width:'+view.percent+'%"></div></div>'+rows.map(([label,value])=>'<div class="side-row"><span>'+escapeHtml(label)+'</span><span>'+escapeHtml(value)+'</span></div>').join('')
}

function displayPath(root,name){const base=String(root||'').replace(/[\\/]+$/,'');return base+'/'+String(name||'').replace(/^[/\\]+|[/\\]+$/g,'')+'/'}
function escapeAttr(value){return String(value).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function escapeHtml(value){return escapeAttr(value)}
function renderSideDownloads(completed){const el=$('#side-downloads');const ready=completed.filter(j=>j.phase==='completed');if(!ready.length){el.innerHTML='<div style="font-size:12px;color:var(--text-muted)">暂无可下载文件</div>';return}const model=ready[0],p=model.params||{},name=p.model_name||'';const files=model.files||{};if(!files.pth||!files.index||!files.log){el.innerHTML='<div style="font-size:12px;color:var(--text-muted)">交付文件生成中…</div>';return}const dataset=p.dataset_name||name,uploadPath=displayPath(state.paths.upload_root,dataset),modelPath=displayPath(state.paths.training_root,name),kaggleUrl=model.kaggle_url||(model.result&&model.result.upload&&model.result.upload.kaggle)||'';const link=kaggleUrl?'<a class="dl-all-btn" href="'+escapeAttr(kaggleUrl)+'" target="_blank" rel="noopener noreferrer">🔗 打开 Kaggle Dataset</a>':'<a class="dl-all-btn" href="/api/v1/models/'+encodeURIComponent(name)+'/zip" download>⬇ 下载模型压缩包</a>'+(model.progress&&model.progress.upload_failed?'<div style="font-size:12px;color:var(--orange);margin-top:6px">Kaggle 上传失败，已切换为浏览器下载</div>':'');el.innerHTML='<div style="font-size:11px;color:var(--text-muted);line-height:1.7;margin-bottom:10px"><div><b style="color:var(--text)">上传路径</b><br><span style="word-break:break-all">'+uploadPath+'</span></div><div style="margin-top:6px"><b style="color:var(--text)">生成路径</b><br><span style="word-break:break-all">'+modelPath+'</span></div><div style="margin-top:6px"><b style="color:var(--text)">模型存放路径</b><br><span style="word-break:break-all">'+modelPath+'</span></div></div>'+link}

function renderSideHistory(completed){const el=$('#side-history');if(!completed.length){el.innerHTML='<div style="font-size:12px;color:var(--text-muted)">暂无历史记录</div>';return}el.innerHTML='<div class="history">'+completed.slice(0,10).map(j=>{const name=j.params?.model_name||'';const icon=j.phase==='completed'?'✅':'❌';return'<div class="history-row"><span class="history-icon">'+icon+'</span><span class="history-name">'+name+'.'+j.type+'</span><span class="history-phase">'+j.phase+'</span></div>'}).join('')+'</div>'}

async function poll(){clearTimeout(state.timer);try{const headers={};if(state.etag)headers['If-None-Match']=state.etag;const r=await fetch('/api/v1/jobs',{cache:'no-store',headers});if(r.status===401){$('#login').classList.remove('hidden');notice('登录已过期，请重新登录');return}if(r.status!==304){if(!r.ok)throw new Error();state.etag=r.headers.get('ETag')||'';const d=await r.json();renderJobs(d.jobs||[])}state.failures=0;if(state.connLost){state.connLost=false;notice('')}}catch{state.failures++;if(state.failures>=3){state.connLost=true;notice('控制服务连接中断，正在自动重试')}}state.timer=setTimeout(poll,document.hidden?10000:2500)}

async function loadOptions(){try{const d=await(await api('/api/v1/options')).json();state.paths=d.paths||{};const dd=$('#dataset-options');dd.innerHTML='';if(d.datasets&&d.datasets.length){d.datasets.forEach(name=>{const opt=document.createElement('div');opt.className='sel-opt';opt.dataset.value=name;opt.onclick=function(){selPick(this,'existing-dataset')};opt.innerHTML='<span class="oi">🎵</span><span class="ol">'+name+'</span><span class="oc">✓</span>';dd.append(opt)});const sep=document.createElement('div');sep.className='sel-sep';dd.append(sep)}else{const opt=document.createElement('div');opt.className='sel-opt';opt.innerHTML='<span class="ol" style="color:var(--text-muted)">暂无数据集</span>';dd.append(opt)}const placeholder=document.createElement('div');placeholder.className='sel-opt';placeholder.innerHTML='<span class="ol" style="color:var(--text-muted)">选择现有数据集...</span>';dd.append(placeholder);state.registry={};(d.models||[]).forEach(m=>{state.registry[m.name]=m});state.progressSnap=d.progress||{};loadModels(d.models||[]);loadGpus(d.gpus||[]);renderStageCard()}catch(err){text($('#gpu-info'),'GPU 状态不可用');notice(err.message)}}

function loadModels(models){const dd=$('#model-options');if(!dd)return;const selected=state.selectedValues['model'],names=models.map(m=>typeof m==='string'?m:m.name),choices=[...new Set([...names,selected].filter(Boolean))];dd.innerHTML='';if(!choices.length){dd.innerHTML='<div class="sel-opt"><span class="ol" style="color:var(--text-muted)">暂无可用模型，请先确定数据集</span></div>';return}choices.forEach(name=>{const opt=document.createElement('div');opt.className='sel-opt'+(name===selected?' selected':'');opt.dataset.value=name;opt.onclick=function(){selPick(this,'model')};opt.innerHTML='<span class="oi">🧩</span><span class="ol">'+name+'</span><span class="oc">✓</span>';dd.append(opt)});if(selected)selectModel('model',selected);else{const auto=(Object.values(state.registry).sort((a,b)=>(b.created_at||0)-(a.created_at||0))[0]||{}).name||names[0];if(auto)selectModel('model',auto)}renderStageCard()}
function selectModel(fieldId,name){state.selectedValues[fieldId]=name;const dd=$('#'+fieldId+'-options');if(!dd){renderStageCard();return}const opt=[...dd.querySelectorAll('.sel-opt')].find(item=>item.dataset.value===name);if(opt)selPick(opt,fieldId);renderStageCard()}

function loadGpus(gpus){state.gpus=gpus;const badge=$('#gpu-info');text(badge,gpus.length?gpus.map(g=>'GPU '+g.id+': '+g.name).join(' · '):'未检测到 GPU');if(gpus.length)badge.title=gpus.map(g=>'GPU '+g.id+': '+g.name+' ('+Math.round(g.memory_mb)+' MB)').join('\n');['training-gpu-options'].forEach(id=>{const dd=$('#'+id);if(!dd)return;dd.innerHTML='';dd.closest('.sel').classList.add('multi');if(!gpus.length){dd.innerHTML='<div class="sel-opt"><span class="ol" style="color:var(--text-muted)">未检测到 GPU</span></div>';return}gpus.forEach(g=>{const opt=document.createElement('div');opt.className='sel-opt selected';opt.dataset.value=String(g.id);opt.onclick=function(){selMulti(this)};opt.innerHTML='<span class="oi">⚡</span><span class="ol">GPU '+g.id+' — '+g.name+'</span><span class="oc" style="font-size:10px;color:var(--text-muted)">'+Math.round(g.memory_mb)+' MB</span>';dd.append(opt)});const btn=dd.closest('.sel').querySelector('.sel-btn');btn.querySelector('.st').textContent=gpus.map(g=>'GPU '+g.id).join(', ');const hidden=dd.closest('.field').querySelector('input[type=hidden]');if(hidden)hidden.value=gpus.map(g=>String(g.id)).join(',')})}

function setResumeControl(d){state.resumeDataset=d.resume_dataset||null;const btn=$('#resume-history');btn.disabled=!d.configured;btn.title=btn.disabled?'请先验证 Kaggle Token':'选择可恢复的 Dataset'}
function setKaggleOwner(owner){state.kaggleOwner=String(owner||'');text($('#kaggle-owner'),state.kaggleOwner?'owner: '+state.kaggleOwner:'')}
async function openKaggleSettings(){const d=await(await api('/api/v1/kaggle-auth')).json();state.kaggleConfigured=!!d.configured;setKaggleOwner(d.owner);setResumeControl(d);$('#kaggle-token').value='';text($('#kaggle-error'),'');if(d.configured){text($('#kaggle-title'),'Kaggle Access Token 已配置');text($('#kaggle-copy'),'当前 owner：'+(d.owner||'已验证')+'。输入新 Token 可重新验证，留空则保持当前 Token。');$('#kaggle-token').placeholder='留空则保持当前 Token';text($('#kaggle-warning'),'训练历史请通过顶部“恢复历史”按钮选择。');text($('#skip-kaggle'),'取消');text($('#kaggle-submit'),'保存设置')}else{text($('#kaggle-title'),'Kaggle Access Token');text($('#kaggle-copy'),'输入新版 Kaggle API Token，用于私有模型持久化和跨 Session 续训。Token 仅保留在当前服务进程中。');$('#kaggle-token').placeholder='可留空';text($('#kaggle-warning'),'不输入仍可训练和浏览器下载，但不能上传私有模型、保存跨 Session checkpoint 或恢复私有 Dataset。');text($('#skip-kaggle'),'暂不配置');text($('#kaggle-submit'),'验证并启用')}$('#kaggle-setup').classList.remove('hidden')}
async function startConsole(){const d=await(await api('/api/v1/kaggle-auth')).json();state.kaggleConfigured=!!d.configured;setKaggleOwner(d.owner);setResumeControl(d);if(d.setup_required){await openKaggleSettings()}else if(d.configured){notice('Kaggle Token 已验证，Dataset owner: '+d.owner)}else if(d.warning||d.setup_required===false){setKaggleOwner('');notice('未配置 Kaggle Token：不能上传私有模型或恢复跨 Session 训练')}poll();loadOptions()}
async function submitKaggleToken(token){const d=await(await api('/api/v1/kaggle-auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})})).json();$('#kaggle-token').value='';$('#kaggle-setup').classList.add('hidden');text($('#kaggle-error'),'');state.kaggleConfigured=!!d.configured;setKaggleOwner(d.owner);setResumeControl(d);if(d.warning)notice(d.warning);else if(d.configured)notice('Kaggle Token 已启用，Dataset owner: '+d.owner)}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('#user').value,password:$('#password').value})});$('#login').classList.add('hidden');text($('#login-error'),'');await startConsole()}catch(err){text($('#login-error'),err.message)}});
$('#kaggle-form').addEventListener('submit',async e=>{e.preventDefault();try{await submitKaggleToken($('#kaggle-token').value)}catch(err){text($('#kaggle-error'),err.message)}});
$('#skip-kaggle').onclick=async()=>{if(state.kaggleConfigured){$('#kaggle-setup').classList.add('hidden');return}try{await submitKaggleToken('')}catch(err){text($('#kaggle-error'),err.message)}};
$('#kaggle-settings').onclick=()=>openKaggleSettings().catch(err=>notice(err.message));
async function restoreSelectedDataset(handle){const confirm=$('#resume-confirm');text($('#resume-error'),'');confirm.disabled=true;text(confirm,'正在恢复...');try{const setting=await(await api('/api/v1/kaggle-auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:'',resume_dataset:handle})})).json();setResumeControl(setting);const d=await(await api('/api/v1/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:handle})})).json();$('#resume-picker').classList.add('hidden');await loadOptions();const restoredModels=Array.isArray(d.models)?d.models.filter(Boolean):[];if(restoredModels.length)selectModel('model',restoredModels[0]);notice(restoredModels.length?'训练历史已准备，当前模型：'+restoredModels[0]:'训练历史已准备：'+d.dataset)}catch(err){text($('#resume-error'),err.message)}finally{text(confirm,'确认恢复');confirm.disabled=!state.resumeSelection}}
async function openResumePicker(){if(!state.kaggleConfigured){await openKaggleSettings();text($('#kaggle-error'),'请先验证 Kaggle Token');return}state.resumeSelection='';$('#resume-picker').classList.remove('hidden');const list=$('#resume-list'),confirm=$('#resume-confirm');confirm.disabled=true;text(confirm,'确认恢复');list.innerHTML='<div class="resume-empty">正在读取 Dataset...</div>';text($('#resume-error'),'');try{const d=await(await api('/api/v1/resume/datasets')).json();if(!d.datasets||!d.datasets.length){list.innerHTML='<div class="resume-empty">没有找到以 -resume 结尾的恢复 Dataset</div>';return}list.innerHTML=d.datasets.map(item=>'<button class="resume-item" type="button" data-handle="'+escapeAttr(item.handle)+'"><strong>'+escapeHtml(item.title||item.handle)+'</strong><small>'+escapeHtml(item.handle)+(item.updated?' · 更新于 '+escapeHtml(item.updated):'')+'</small></button>').join('');list.querySelectorAll('.resume-item').forEach(item=>item.onclick=()=>{list.querySelectorAll('.resume-item').forEach(other=>other.classList.remove('selected'));item.classList.add('selected');state.resumeSelection=item.dataset.handle;confirm.disabled=false})}catch(err){list.innerHTML='<div class="resume-empty">读取失败</div>';text($('#resume-error'),err.message)}}
$('#resume-history').onclick=()=>openResumePicker().catch(err=>notice(err.message));
$('#resume-confirm').onclick=()=>{if(state.resumeSelection)restoreSelectedDataset(state.resumeSelection)};
$('#resume-cancel').onclick=()=>{state.resumeSelection='';$('#resume-picker').classList.add('hidden')};
$('#logout').onclick=async()=>{await fetch('/api/v1/auth/logout',{method:'POST'});$('#login').classList.remove('hidden')};
document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll()});
fetch('/api/v1/session').then(async r=>{if(!r.ok)return;const d=await r.json();if(d.authenticated){$('#login').classList.add('hidden');startConsole()}});
</script></body></html>'''
