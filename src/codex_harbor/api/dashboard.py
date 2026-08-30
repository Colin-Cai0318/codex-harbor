# A raw string is intentional: JavaScript uses escaped newlines in split/join.
# Keeping those escapes intact prevents the browser syntax failure that occurred
# when this page was embedded in a regular Python triple-quoted string.
DASHBOARD = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>Codex Harbor</title>
  <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22><text y=%2252%22 x=%2250%22 text-anchor=%22middle%22 dominant-baseline=%22middle%22 font-size=%2250%22>⚓</text></svg>">
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f5;
      --surface: #ffffff;
      --surface-raised: #ffffff;
      --surface-soft: #f0f0ed;
      --text: #20201e;
      --muted: #72726d;
      --faint: #9b9b95;
      --border: #e2e2de;
      --border-strong: #cecec8;
      --accent: #d97757;
      --accent-hover: #c76748;
      --accent-soft: #f7e8e1;
      --success: #2e7d5b;
      --success-soft: #e4f2eb;
      --warning: #a96614;
      --warning-soft: #f7edda;
      --danger: #b74848;
      --danger-soft: #f7e4e4;
      --info: #3e6d92;
      --info-soft: #e5eef5;
      --shadow: 0 12px 32px rgba(35, 35, 30, .08);
    }

    :root[data-theme="dark"] {
      color-scheme: dark;
      --bg: #171716;
      --surface: #20201e;
      --surface-raised: #272725;
      --surface-soft: #2c2c29;
      --text: #f3f3ef;
      --muted: #aaa9a2;
      --faint: #7e7d77;
      --border: #353532;
      --border-strong: #494944;
      --accent: #e18a6b;
      --accent-hover: #ec9a7c;
      --accent-soft: #3b2b25;
      --success: #75c49e;
      --success-soft: #20372c;
      --warning: #e0ad61;
      --warning-soft: #3d3220;
      --danger: #e38484;
      --danger-soft: #402626;
      --info: #89b6d6;
      --info-soft: #243541;
      --shadow: 0 16px 40px rgba(0, 0, 0, .24);
    }

    * { box-sizing: border-box; }
    html { min-width: 320px; background: var(--bg); }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
      transition: background .18s ease, color .18s ease;
    }
    button, input, textarea, select { font: inherit; }
    button { color: inherit; }
    .shell { min-height: 100vh; }
    .appbar {
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 24px;
      position: sticky;
      top: 0;
      z-index: 20;
      background: color-mix(in srgb, var(--bg) 88%, transparent);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(16px);
    }
    .brand { display: flex; align-items: center; gap: 11px; font-weight: 650; letter-spacing: -.01em; }
    .brandmark {
      width: 30px;
      height: 30px;
      display: grid;
      place-items: center;
      color: white;
      background: var(--text);
      border-radius: 9px;
      font-size: 15px;
    }
    [data-theme="dark"] .brandmark { color: #171716; background: #f3f3ef; }
    .app-actions { display: flex; align-items: center; gap: 8px; }
    .page { max-width: 1680px; margin: 0 auto; padding: 28px 24px 48px; }
    .hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin-bottom: 22px; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 6px; font-size: clamp(24px, 3vw, 34px); letter-spacing: -.035em; font-weight: 650; }
    .hero p { color: var(--muted); margin-bottom: 0; max-width: 720px; }
    .pool-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      padding: 7px 11px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--surface);
      font-size: 12px;
      font-weight: 650;
    }
    .pool-pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--success); box-shadow: 0 0 0 3px var(--success-soft); }
    .pool-pill[data-state="PAUSED"]::before, .pool-pill[data-state="DRAINING"]::before { background: var(--warning); box-shadow: 0 0 0 3px var(--warning-soft); }
    .pool-pill[data-state="FROZEN"]::before { background: var(--info); box-shadow: 0 0 0 3px var(--info-soft); }
    .metrics { display: grid; grid-template-columns: 1fr 1.35fr 1.35fr; gap: 12px; margin-bottom: 18px; }
    .metric-card {
      min-width: 0;
      padding: 17px 18px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      box-shadow: 0 1px 0 rgba(0, 0, 0, .02);
    }
    .metric-head { display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 12px; }
    .metric-value { margin-top: 7px; font-size: 24px; line-height: 1.1; font-weight: 620; letter-spacing: -.03em; }
    .metric-sub { margin-top: 7px; color: var(--faint); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .progress { height: 5px; margin-top: 13px; overflow: hidden; border-radius: 999px; background: var(--surface-soft); }
    .progress > i { display: block; width: 0; height: 100%; border-radius: inherit; background: var(--accent); transition: width .25s ease; }
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px;
      margin-bottom: 16px;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
    }
    .toolbar-left, .toolbar-right, .button-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .search { position: relative; min-width: min(340px, 52vw); }
    .search span { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); color: var(--faint); pointer-events: none; }
    .search input { width: 100%; padding-left: 34px; }
    input, textarea, select {
      width: 100%;
      color: var(--text);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 9px 10px;
      outline: none;
    }
    input:focus, textarea:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    textarea { min-height: 88px; resize: vertical; }
    .btn, .icon-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 7px;
      min-height: 36px;
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 9px;
      background: var(--surface-raised);
      cursor: pointer;
      font-weight: 560;
      transition: border-color .15s ease, background .15s ease, transform .15s ease;
    }
    .btn:hover, .icon-btn:hover { border-color: var(--border-strong); background: var(--surface-soft); }
    .btn:active, .icon-btn:active { transform: translateY(1px); }
    .btn.primary { color: white; background: var(--accent); border-color: var(--accent); }
    .btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
    .btn.danger { color: var(--danger); }
    .icon-btn { width: 36px; padding: 0; font-size: 16px; }
    .switch-label { display: inline-flex; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; cursor: pointer; }
    .switch-label input { width: 34px; height: 19px; appearance: none; padding: 0; border: 0; border-radius: 99px; background: var(--border-strong); position: relative; cursor: pointer; }
    .switch-label input::after { content: ""; position: absolute; width: 15px; height: 15px; top: 2px; left: 2px; border-radius: 50%; background: white; transition: transform .18s ease; box-shadow: 0 1px 3px #0004; }
    .switch-label input:checked { background: var(--accent); }
    .switch-label input:checked::after { transform: translateX(15px); }
    .notice { display: none; margin-bottom: 16px; padding: 12px 14px; border: 1px solid var(--warning); border-radius: 11px; color: var(--warning); background: var(--warning-soft); }
    .notice.show { display: block; }
    .board { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(238px, 1fr); gap: 12px; overflow-x: auto; padding: 1px 1px 14px; scroll-snap-type: x proximity; }
    .lane { min-height: 410px; padding: 10px; border: 1px solid var(--border); border-radius: 14px; background: color-mix(in srgb, var(--surface-soft) 65%, transparent); scroll-snap-align: start; }
    .lane-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 3px 3px 11px; }
    .lane-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 650; }
    .lane-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); }
    .lane[data-lane="active"] .lane-dot { background: var(--accent); }
    .lane[data-lane="waiting"] .lane-dot { background: var(--warning); }
    .lane[data-lane="attention"] .lane-dot { background: var(--danger); }
    .lane[data-lane="completed"] .lane-dot { background: var(--success); }
    .count { min-width: 23px; padding: 2px 7px; text-align: center; color: var(--muted); background: var(--surface); border: 1px solid var(--border); border-radius: 999px; font-size: 11px; }
    .card-list { display: grid; gap: 9px; align-content: start; }
    .task-card {
      position: relative;
      width: 100%;
      padding: 13px;
      text-align: left;
      color: inherit;
      border: 1px solid var(--border);
      border-radius: 11px;
      background: var(--surface-raised);
      box-shadow: 0 1px 1px rgba(0, 0, 0, .025);
      cursor: pointer;
      transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
    }
    .task-card:hover { transform: translateY(-1px); border-color: var(--border-strong); box-shadow: var(--shadow); }
    .card-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .task-id { color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
    .status-chip { padding: 3px 7px; border-radius: 999px; font-size: 10px; font-weight: 680; color: var(--info); background: var(--info-soft); }
    .status-chip[data-status="RUNNING"], .status-chip[data-status="CLAIMED"] { color: var(--accent); background: var(--accent-soft); }
    .status-chip[data-status="WAIT_QUOTA"], .status-chip[data-status="WAIT_DEP"], .status-chip[data-status="RETRY_WAIT"] { color: var(--warning); background: var(--warning-soft); }
    .status-chip[data-status="BLOCKED"], .status-chip[data-status="FAILED"] { color: var(--danger); background: var(--danger-soft); }
    .status-chip[data-status="SUCCEEDED"] { color: var(--success); background: var(--success-soft); }
    .task-title { margin: 12px 0 11px; font-size: 14px; font-weight: 620; line-height: 1.35; overflow-wrap: anywhere; }
    .card-meta { display: flex; flex-wrap: wrap; gap: 5px; color: var(--muted); font-size: 11px; }
    .meta-tag { max-width: 100%; padding: 3px 6px; overflow: hidden; border-radius: 5px; background: var(--surface-soft); text-overflow: ellipsis; white-space: nowrap; }
    .empty-lane { padding: 26px 8px; text-align: center; color: var(--faint); font-size: 12px; }
    dialog { color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 16px; box-shadow: var(--shadow); }
    dialog::backdrop { background: rgba(10, 10, 10, .48); backdrop-filter: blur(3px); }
    .modal { width: min(760px, calc(100vw - 28px)); max-height: calc(100vh - 40px); padding: 0; overflow: auto; }
    .modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; position: sticky; top: 0; z-index: 2; padding: 19px 21px 15px; background: var(--surface); border-bottom: 1px solid var(--border); }
    .modal-head h2 { margin: 0; font-size: 18px; letter-spacing: -.02em; }
    .modal-body { padding: 20px 21px 22px; }
    .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .field { display: flex; flex-direction: column; gap: 6px; color: var(--muted); font-size: 12px; }
    .field.wide { grid-column: 1 / -1; }
    .form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 9px; margin-top: 18px; }
    .form-message { margin-right: auto; color: var(--muted); font-size: 12px; }
    .drawer { width: min(620px, calc(100vw - 16px)); max-width: none; height: 100vh; max-height: 100vh; margin: 0 0 0 auto; border-radius: 16px 0 0 16px; }
    .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
    .detail-item { min-width: 0; padding: 11px; border-radius: 9px; background: var(--surface-soft); }
    .detail-item .label { display: block; margin-bottom: 4px; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
    .detail-item .value { overflow-wrap: anywhere; }
    .detail-section { margin-top: 22px; }
    .detail-section h3 { margin-bottom: 9px; font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
    pre { max-height: 230px; padding: 12px; overflow: auto; border-radius: 9px; color: var(--muted); background: var(--surface-soft); font: 11px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
    .skeleton { min-height: 108px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface-soft) 50%, var(--surface) 75%); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
    @keyframes shimmer { to { background-position: -200% 0; } }
    .updated { color: var(--faint); font-size: 11px; }
    .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
    @media (max-width: 820px) {
      .metrics { grid-template-columns: 1fr; }
      .toolbar { align-items: stretch; flex-direction: column; }
      .toolbar-left, .toolbar-right { justify-content: space-between; }
      .search { min-width: 0; flex: 1; }
      .board { grid-auto-columns: minmax(250px, 84vw); }
    }
    @media (max-width: 560px) {
      .appbar { padding: 0 14px; }
      .page { padding: 21px 14px 36px; }
      .hero { flex-direction: column; gap: 12px; }
      .form-grid, .detail-grid { grid-template-columns: 1fr; }
      .field.wide { grid-column: auto; }
      .toolbar-right .switch-label span { display: none; }
    }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; } }
  </style>
</head>
<body>
  <div class="shell">
    <header class="appbar">
      <div class="brand"><span class="brandmark">⌁</span><span>Codex Harbor</span></div>
      <div class="app-actions">
        <span id="lastUpdated" class="updated">Connecting…</span>
        <button id="themeToggle" class="icon-btn" type="button" aria-label="Switch theme" title="Switch theme">◐</button>
      </div>
    </header>

    <main class="page">
      <section class="hero">
        <div><h1>Task board</h1><p>Persistent Codex work, organized by lifecycle and kept safe across processes.</p></div>
        <span id="poolPill" class="pool-pill" data-state="LOADING">LOADING</span>
      </section>

      <div id="errorNotice" class="notice" role="alert"></div>
      <div id="poolNotice" class="notice" role="status"></div>

      <section class="metrics" aria-label="Runtime overview">
        <article class="metric-card">
          <div class="metric-head"><span>Workers</span><span id="workerState">Idle</span></div>
          <div id="workers" class="metric-value">—</div>
          <div class="metric-sub">Active scheduler capacity</div>
        </article>
        <article class="metric-card">
          <div class="metric-head"><span>5-hour usage</span><span id="fiveAvailability">Checking</span></div>
          <div id="five" class="metric-value">—</div>
          <div class="progress"><i id="fivebar"></i></div>
          <div id="fiveReset" class="metric-sub">Reset time unavailable</div>
        </article>
        <article class="metric-card">
          <div class="metric-head"><span>Weekly usage</span><span id="weekAvailability">Checking</span></div>
          <div id="weekly" class="metric-value">—</div>
          <div class="progress"><i id="weekbar"></i></div>
          <div id="weekReset" class="metric-sub">Reset time unavailable</div>
        </article>
      </section>

      <section class="toolbar" aria-label="Board controls">
        <div class="toolbar-left">
          <label class="search"><span>⌕</span><span class="sr-only">Search tasks</span><input id="searchInput" type="search" placeholder="Search tasks"></label>
          <button id="newTaskButton" class="btn primary" type="button">＋ New task</button>
        </div>
        <div class="toolbar-right">
          <label class="switch-label"><input id="weeklyFreeze" type="checkbox"><span>Freeze on weekly reset</span></label>
          <button class="btn pool-action" data-action="pause" type="button">Pause</button>
          <button class="btn pool-action" data-action="freeze" type="button">Freeze</button>
          <button class="btn pool-action" data-action="resume" type="button">Resume</button>
        </div>
      </section>

      <section id="board" class="board" aria-label="Task status board">
        <div class="lane skeleton"></div><div class="lane skeleton"></div><div class="lane skeleton"></div>
      </section>
    </main>
  </div>

  <dialog id="createDialog" class="modal">
    <div class="modal-head"><div><h2>Create Harbor task</h2><span class="updated">The repository must already be registered.</span></div><button class="icon-btn dialog-close" type="button" aria-label="Close">×</button></div>
    <form id="createForm" class="modal-body">
      <div class="form-grid">
        <label class="field wide">Title<input name="title" required placeholder="A concrete task title"></label>
        <label class="field">Repository<select id="repositorySelect" name="repository" required></select></label>
        <label class="field">Execution backend<select name="execution_backend"><option value="local">Local</option><option value="linux">Linux</option><option value="wsl">WSL2</option><option value="windows">Windows</option></select></label>
        <label class="field">Priority<input name="priority" type="number" value="100"></label>
        <label class="field">Maximum attempts<input name="max_attempts" type="number" value="5" min="1"></label>
        <label class="field">Model<select id="modelSelect" name="model"><option value="">Inherit default</option></select></label>
        <label class="field">Reasoning<select name="reasoning_effort"><option value="">Inherit default</option><option>minimal</option><option>low</option><option>medium</option><option>high</option><option>xhigh</option></select></label>
        <label class="field">Profile<select id="profileSelect" name="profile"><option value="">None</option></select></label>
        <label class="field">Exclusive group<input name="exclusive_group" placeholder="Optional"></label>
        <label class="field wide">Dependencies<input name="depends_on" placeholder="T001, T002"></label>
        <label class="field wide">Description<textarea name="description" placeholder="Useful context for operators"></textarea></label>
        <label class="field wide">Prompt<textarea name="prompt" required placeholder="Objective, constraints, and expected outcome"></textarea></label>
        <label class="field wide">Acceptance commands<textarea name="acceptance_commands" placeholder="One command per line"></textarea></label>
      </div>
      <div class="form-actions"><span id="createStatus" class="form-message"></span><button class="btn dialog-close" type="button">Cancel</button><button class="btn primary" type="submit">Create task</button></div>
    </form>
  </dialog>

  <dialog id="detailDialog" class="modal drawer">
    <div class="modal-head"><div><h2 id="detailTitle">Task</h2><span id="detailSubtitle" class="updated"></span></div><button class="icon-btn dialog-close" type="button" aria-label="Close">×</button></div>
    <div class="modal-body">
      <div id="detailBody" class="detail-grid"></div>
      <section class="detail-section"><h3>Agent configuration</h3><div class="form-grid"><label class="field">Model<select id="detailModel"></select></label><label class="field">Reasoning<select id="detailReasoning"><option value="">Inherit default</option><option>minimal</option><option>low</option><option>medium</option><option>high</option><option>xhigh</option></select></label></div><div class="form-actions"><span id="detailStatus" class="form-message"></span><button id="saveAgent" class="btn" type="button">Save for next turn</button></div></section>
      <section class="detail-section"><h3>Acceptance</h3><pre id="detailAcceptance">No commands configured</pre></section>
      <section class="detail-section"><h3>Recent events</h3><pre id="detailEvents">Loading…</pre></section>
      <div class="form-actions"><button id="copyWorktree" class="btn" type="button">Copy worktree</button><button id="copyThread" class="btn" type="button">Copy thread ID</button><button id="retryTask" class="btn" type="button">Retry</button><button id="cancelTask" class="btn danger" type="button">Cancel task</button></div>
    </div>
  </dialog>

  <script>
    const LANES = [
      {id:'backlog', title:'Backlog', states:['CREATED','PENDING','WAIT_DEP']},
      {id:'ready', title:'Ready', states:['READY']},
      {id:'active', title:'Active', states:['CLAIMED','RUNNING']},
      {id:'waiting', title:'Waiting', states:['WAIT_QUOTA','RETRY_WAIT']},
      {id:'attention', title:'Needs attention', states:['BLOCKED','FAILED']},
      {id:'completed', title:'Completed', states:['SUCCEEDED','CANCELLED']}
    ];
    const state = {tasks:[], models:[], profiles:[], pool:null, selectedTask:null};
    const byId = id => document.getElementById(id);
    const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const basename = path => String(path || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || 'repository';

    async function request(path, options={}) {
      const response = await fetch(path, options);
      const data = response.status === 204 ? null : await response.json();
      if (!response.ok) throw new Error(data?.detail || `${response.status} ${response.statusText}`);
      return data;
    }

    function applyTheme(theme) {
      document.documentElement.dataset.theme = theme;
      byId('themeToggle').textContent = theme === 'dark' ? '☀' : '☾';
      byId('themeToggle').title = theme === 'dark' ? 'Use light theme' : 'Use dark theme';
      localStorage.setItem('harbor-theme', theme);
    }
    function initializeTheme() {
      const requested = new URLSearchParams(location.search).get('theme');
      const saved = localStorage.getItem('harbor-theme');
      applyTheme(['light','dark'].includes(requested) ? requested : (saved || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')));
    }

    function formatReset(value) {
      if (!value) return 'Reset time unavailable';
      const date = new Date(value);
      if (Number.isNaN(date.valueOf())) return `Resets ${value}`;
      return `Resets ${new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date)}`;
    }
    function quotaView(quota, valueId, barId, resetId, availabilityId) {
      const used = quota?.used_percent;
      byId(valueId).textContent = used == null ? 'Unknown' : `${Math.round(used)}% used`;
      byId(barId).style.width = `${Math.min(100, Math.max(0, Number(used) || 0))}%`;
      byId(resetId).textContent = formatReset(quota?.reset_at);
      byId(availabilityId).textContent = quota ? (quota.available ? `${Math.round(quota.remaining ?? 0)}% left` : 'Unavailable') : 'No data';
    }
    function taskAgent(task) { return `${task.model || 'default'} / ${task.reasoning_effort || 'default'}`; }
    function renderBoard() {
      const query = byId('searchInput').value.trim().toLowerCase();
      const filtered = state.tasks.filter(task => !query || [task.id, task.title, task.status, task.repository, task.model, task.reasoning_effort].some(value => String(value || '').toLowerCase().includes(query)));
      byId('board').innerHTML = LANES.map(lane => {
        const items = filtered.filter(task => lane.states.includes(task.status));
        const cards = items.map(task => `<button class="task-card" type="button" data-task-id="${esc(task.id)}"><span class="card-top"><span class="task-id">${esc(task.id)}</span><span class="status-chip" data-status="${esc(task.status)}">${esc(task.status)}</span></span><span class="task-title">${esc(task.title)}</span><span class="card-meta"><span class="meta-tag">${esc(taskAgent(task))}</span><span class="meta-tag">P${esc(task.priority)}</span><span class="meta-tag">${esc(basename(task.repository))}</span>${task.current_attempt ? `<span class="meta-tag">Attempt ${esc(task.current_attempt)}/${esc(task.max_attempts)}</span>` : ''}</span></button>`).join('');
        return `<section class="lane" data-lane="${lane.id}"><header class="lane-head"><span class="lane-title"><i class="lane-dot"></i>${lane.title}</span><span class="count">${items.length}</span></header><div class="card-list">${cards || '<div class="empty-lane">No tasks in this pool</div>'}</div></section>`;
      }).join('');
    }

    function renderOverview(pool, tasks, quotas, workers) {
      state.pool = pool;
      state.tasks = tasks;
      byId('poolPill').textContent = pool.state;
      byId('poolPill').dataset.state = pool.state;
      byId('weeklyFreeze').checked = Boolean(pool.freeze_on_weekly_reset);
      const maxWorkers = pool.max_workers ?? 3;
      byId('workers').textContent = `${workers.length} / ${maxWorkers}`;
      byId('workerState').textContent = workers.length ? `${workers.length} active` : 'Idle';
      const poolNotice = byId('poolNotice');
      if (pool.state === 'DRAINING') {
        const draining = tasks.filter(task => task.grandfathered && !['SUCCEEDED','FAILED','CANCELLED','BLOCKED'].includes(task.status)).length;
        poolNotice.textContent = `Weekly reset detected. ${draining} grandfathered task${draining === 1 ? '' : 's'} may continue; new tasks will not start.`;
        poolNotice.classList.add('show');
      } else if (pool.state === 'FROZEN') {
        const remaining = tasks.filter(task => !['SUCCEEDED','FAILED','CANCELLED','BLOCKED'].includes(task.status)).length;
        poolNotice.textContent = `Harbor is frozen after the weekly drain. ${remaining} task${remaining === 1 ? '' : 's'} remain queued until manual resume.`;
        poolNotice.classList.add('show');
      } else if (pool.state === 'PAUSED') {
        poolNotice.textContent = 'Scheduling is paused. Running tasks may finish, but no new task will start.';
        poolNotice.classList.add('show');
      } else {
        poolNotice.classList.remove('show');
      }
      quotaView(quotas.find(item => item.quota_type === 'PRIMARY_5H'), 'five', 'fivebar', 'fiveReset', 'fiveAvailability');
      quotaView(quotas.find(item => item.quota_type === 'WEEKLY'), 'weekly', 'weekbar', 'weekReset', 'weekAvailability');
      renderBoard();
    }

    async function refresh() {
      try {
        const [pool, tasks, quotas, workers] = await Promise.all([request('/api/pool'), request('/api/tasks'), request('/api/quota'), request('/api/workers')]);
        renderOverview(pool, tasks, quotas, workers);
        byId('errorNotice').classList.remove('show');
        byId('lastUpdated').textContent = `Updated ${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}`;
      } catch (error) {
        byId('errorNotice').textContent = `Harbor API unavailable: ${error.message}`;
        byId('errorNotice').classList.add('show');
        byId('lastUpdated').textContent = 'Disconnected';
      }
    }

    async function loadOptions() {
      const [repositories, models, profiles] = await Promise.all([request('/api/repositories'), request('/api/models'), request('/api/profiles')]);
      state.models = models;
      state.profiles = profiles;
      byId('repositorySelect').innerHTML = repositories.length ? repositories.map(repo => `<option value="${esc(repo.path)}">${esc(repo.name)} — ${esc(repo.path)}</option>`).join('') : '<option value="">Register a repository with harbor repo add</option>';
      const modelOptions = '<option value="">Inherit default</option>' + models.map(model => `<option value="${esc(model.model)}">${esc(model.display_name)}${model.is_default ? ' (default)' : ''}</option>`).join('');
      byId('modelSelect').innerHTML = modelOptions;
      byId('detailModel').innerHTML = modelOptions;
      byId('profileSelect').innerHTML = '<option value="">None</option>' + profiles.map(profile => `<option value="${esc(profile.name)}">${esc(profile.name)}</option>`).join('');
    }

    function detailItem(label, value) { return `<div class="detail-item"><span class="label">${esc(label)}</span><span class="value">${esc(value ?? '—')}</span></div>`; }
    async function showTask(taskId) {
      try {
        const [task, events] = await Promise.all([request(`/api/tasks/${encodeURIComponent(taskId)}`), request(`/api/events?task_id=${encodeURIComponent(taskId)}&limit=40`)]);
        state.selectedTask = task;
        const latest = task.latest_attempt || {};
        const activeThread = (task.threads || []).at(-1) || {};
        byId('detailTitle').textContent = `${task.id} · ${task.title}`;
        byId('detailSubtitle').textContent = `${task.status} · ${basename(task.repository)}`;
        byId('detailBody').innerHTML = [
          ['Status', task.status], ['Priority', task.priority],
          ['Requested agent', taskAgent(task)], ['Effective agent', `${latest.effective_model || '—'} / ${latest.effective_reasoning_effort || '—'}`],
          ['Pending agent', `${task.pending_model || '—'} / ${task.pending_reasoning_effort || '—'}`], ['Attempt', `${task.current_attempt} / ${task.max_attempts}`],
          ['Worker', task.worker?.worker_id || '—'], ['Dependencies', (task.depends_on || []).join(', ') || 'None'],
          ['Root thread', task.root_thread_id || '—'], ['Active thread', activeThread.thread_id || '—'],
          ['Worktree', task.worktree_path || '—'], ['Blocked reason', task.blocked_reason || '—']
        ].map(item => detailItem(item[0], item[1])).join('');
        byId('detailModel').value = task.model || '';
        byId('detailReasoning').value = task.reasoning_effort || '';
        byId('detailAcceptance').textContent = (task.acceptance_commands || []).join('\n') || 'No commands configured';
        byId('detailEvents').textContent = events.map(event => `${event.timestamp}  ${event.event_type}\n${event.payload ? JSON.stringify(event.payload, null, 2) : ''}`).join('\n\n') || 'No events recorded';
        byId('detailStatus').textContent = '';
        byId('retryTask').disabled = !['FAILED','BLOCKED','CANCELLED'].includes(task.status);
        byId('cancelTask').disabled = ['SUCCEEDED','CANCELLED'].includes(task.status);
        byId('detailDialog').showModal();
      } catch (error) { showError(error); }
    }

    function showError(error) {
      byId('errorNotice').textContent = error.message || String(error);
      byId('errorNotice').classList.add('show');
    }
    async function poolAction(action) { try { await request(`/api/pool/${action}`, {method:'POST'}); await refresh(); } catch (error) { showError(error); } }
    async function taskAction(action) {
      if (!state.selectedTask) return;
      try {
        await request(`/api/tasks/${encodeURIComponent(state.selectedTask.id)}/${action}`, {method:'POST'});
        byId('detailDialog').close();
        await refresh();
      } catch (error) { byId('detailStatus').textContent = error.message; }
    }
    async function copyValue(value, label) {
      if (!value) return;
      try { await navigator.clipboard.writeText(value); byId('detailStatus').textContent = `${label} copied`; }
      catch { byId('detailStatus').textContent = `Copy failed: ${value}`; }
    }

    async function createTask(event) {
      event.preventDefault();
      const form = event.currentTarget;
      const body = Object.fromEntries(new FormData(form));
      body.priority = Number(body.priority);
      body.max_attempts = Number(body.max_attempts);
      body.depends_on = body.depends_on ? body.depends_on.split(',').map(item => item.trim()).filter(Boolean) : [];
      body.acceptance_commands = body.acceptance_commands ? body.acceptance_commands.split('\n').map(item => item.trim()).filter(Boolean) : [];
      for (const key of ['model','reasoning_effort','profile','exclusive_group']) if (!body[key]) body[key] = null;
      byId('createStatus').textContent = 'Creating…';
      try {
        const created = await request('/api/tasks', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
        form.reset();
        byId('createStatus').textContent = '';
        byId('createDialog').close();
        await refresh();
        await showTask(created.id);
      } catch (error) { byId('createStatus').textContent = error.message; }
    }

    byId('themeToggle').addEventListener('click', () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    byId('searchInput').addEventListener('input', renderBoard);
    byId('newTaskButton').addEventListener('click', () => { byId('createStatus').textContent = ''; byId('createDialog').showModal(); });
    document.querySelectorAll('.dialog-close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    document.querySelectorAll('.pool-action').forEach(button => button.addEventListener('click', () => poolAction(button.dataset.action)));
    byId('weeklyFreeze').addEventListener('change', async event => { try { await request('/api/pool', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({freeze_on_weekly_reset:event.target.checked})}); await refresh(); } catch (error) { event.target.checked = !event.target.checked; showError(error); } });
    byId('board').addEventListener('click', event => { const card = event.target.closest('[data-task-id]'); if (card) showTask(card.dataset.taskId); });
    byId('createForm').addEventListener('submit', createTask);
    byId('saveAgent').addEventListener('click', async () => { if (!state.selectedTask) return; try { const body={model:byId('detailModel').value || null, reasoning_effort:byId('detailReasoning').value || null}; await request(`/api/tasks/${encodeURIComponent(state.selectedTask.id)}/agent`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); byId('detailStatus').textContent='Saved'; await refresh(); } catch(error) { byId('detailStatus').textContent=error.message; } });
    byId('retryTask').addEventListener('click', () => taskAction('retry'));
    byId('cancelTask').addEventListener('click', () => taskAction('cancel'));
    byId('copyWorktree').addEventListener('click', () => copyValue(state.selectedTask?.worktree_path, 'Worktree path'));
    byId('copyThread').addEventListener('click', () => copyValue(state.selectedTask?.root_thread_id, 'Thread ID'));
    document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

    initializeTheme();
    Promise.all([loadOptions(), refresh()]).catch(showError);
    setInterval(() => { if (!document.hidden) refresh(); }, 3000);
  </script>
</body>
</html>
"""
