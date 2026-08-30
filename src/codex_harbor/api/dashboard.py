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
    .language-select { width: auto; min-width: 96px; height: 36px; padding: 6px 28px 6px 9px; font-size: 12px; }
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
    .capacity-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 7px; color: var(--faint); font-size: 11px; }
    .capacity-control { display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
    .capacity-control input { width: 58px; height: 30px; padding: 4px 7px; text-align: center; font-size: 12px; }
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
        <span id="lastUpdated" class="updated" data-i18n="runtime.connecting">Connecting…</span>
        <label class="sr-only" for="languageSelect" data-i18n="language.label">Language</label>
        <select id="languageSelect" class="language-select" aria-label="Language"><option value="en">English</option><option value="zh-CN">简体中文</option></select>
        <button id="themeToggle" class="icon-btn" type="button" aria-label="Switch theme" title="Switch theme">◐</button>
      </div>
    </header>

    <main class="page">
      <section class="hero">
        <div><h1 data-i18n="hero.title">Task board</h1><p data-i18n="hero.subtitle">Persistent Codex work, organized by lifecycle and kept safe across processes.</p></div>
        <span id="poolPill" class="pool-pill" data-state="LOADING">LOADING</span>
      </section>

      <div id="errorNotice" class="notice" role="alert"></div>
      <div id="poolNotice" class="notice" role="status"></div>

      <section class="metrics" aria-label="Runtime overview" data-i18n-aria-label="metrics.label">
        <article class="metric-card">
          <div class="metric-head"><span data-i18n="metrics.workers">Workers</span><span id="workerState">Idle</span></div>
          <div id="workers" class="metric-value">—</div>
          <div class="capacity-row"><span data-i18n="metrics.capacity">Active scheduler capacity</span><label class="capacity-control"><span data-i18n="metrics.maxParallel">Max parallel</span><input id="maxWorkersInput" type="number" min="1" max="64" value="3" aria-label="Maximum parallel tasks" data-i18n-aria-label="metrics.maxParallelTasks"></label></div>
        </article>
        <article class="metric-card">
          <div class="metric-head"><span data-i18n="metrics.fiveHour">5-hour usage</span><span id="fiveAvailability" data-i18n="quota.checking">Checking</span></div>
          <div id="five" class="metric-value">—</div>
          <div class="progress"><i id="fivebar"></i></div>
          <div id="fiveReset" class="metric-sub" data-i18n="quota.resetUnavailable">Reset time unavailable</div>
        </article>
        <article class="metric-card">
          <div class="metric-head"><span data-i18n="metrics.weekly">Weekly usage</span><span id="weekAvailability" data-i18n="quota.checking">Checking</span></div>
          <div id="weekly" class="metric-value">—</div>
          <div class="progress"><i id="weekbar"></i></div>
          <div id="weekReset" class="metric-sub" data-i18n="quota.resetUnavailable">Reset time unavailable</div>
        </article>
      </section>

      <section class="toolbar" aria-label="Board controls">
        <div class="toolbar-left">
          <label class="search"><span>⌕</span><span class="sr-only" data-i18n="board.search">Search tasks</span><input id="searchInput" type="search" placeholder="Search tasks" data-i18n-placeholder="board.search"></label>
          <button id="newTaskButton" class="btn primary" type="button" data-i18n="board.newTask">＋ New task</button>
        </div>
        <div class="toolbar-right">
          <label class="switch-label"><input id="weeklyFreeze" type="checkbox"><span data-i18n="pool.freezeOnReset">Freeze on weekly reset</span></label>
          <button class="btn pool-action" data-action="pause" type="button" data-i18n="actions.pause">Pause</button>
          <button class="btn pool-action" data-action="freeze" type="button" data-i18n="actions.freeze">Freeze</button>
          <button class="btn pool-action" data-action="resume" type="button" data-i18n="actions.resume">Resume</button>
        </div>
      </section>

      <section id="board" class="board" aria-label="Task status board">
        <div class="lane skeleton"></div><div class="lane skeleton"></div><div class="lane skeleton"></div>
      </section>
    </main>
  </div>

  <dialog id="createDialog" class="modal">
    <div class="modal-head"><div><h2 data-i18n="create.title">Create Harbor task</h2><span class="updated" data-i18n="create.repoHint">The repository must already be registered.</span></div><button class="icon-btn dialog-close" type="button" aria-label="Close" data-i18n-aria-label="actions.close">×</button></div>
    <form id="createForm" class="modal-body">
      <div class="form-grid">
        <label class="field wide"><span data-i18n="fields.title">Title</span><input name="title" required placeholder="A concrete task title" data-i18n-placeholder="placeholders.taskTitle"></label>
        <label class="field"><span data-i18n="fields.repository">Repository</span><select id="repositorySelect" name="repository" required></select></label>
        <label class="field"><span data-i18n="fields.backend">Execution backend</span><select name="execution_backend"><option value="local" data-i18n="backend.local">Local</option><option value="linux">Linux</option><option value="wsl">WSL2</option><option value="windows">Windows</option></select></label>
        <label class="field"><span data-i18n="fields.priority">Priority</span><input name="priority" type="number" value="100"></label>
        <label class="field"><span data-i18n="fields.maxAttempts">Maximum attempts</span><input name="max_attempts" type="number" value="5" min="1"></label>
        <label class="field"><span data-i18n="fields.model">Model</span><select id="modelSelect" name="model"><option value="">Inherit default</option></select></label>
        <label class="field"><span data-i18n="fields.reasoning">Reasoning</span><select name="reasoning_effort"><option value="" data-i18n="common.inheritDefault">Inherit default</option><option>minimal</option><option>low</option><option>medium</option><option>high</option><option>xhigh</option></select></label>
        <label class="field"><span data-i18n="fields.profile">Profile</span><select id="profileSelect" name="profile"><option value="">None</option></select></label>
        <label class="field"><span data-i18n="fields.exclusiveGroup">Exclusive group</span><input name="exclusive_group" placeholder="Optional" data-i18n-placeholder="common.optional"></label>
        <label class="field wide"><span data-i18n="fields.dependencies">Dependencies</span><input name="depends_on" placeholder="T001, T002"></label>
        <label class="field wide"><span data-i18n="fields.description">Description</span><textarea name="description" placeholder="Useful context for operators" data-i18n-placeholder="placeholders.description"></textarea></label>
        <label class="field wide"><span data-i18n="fields.prompt">Prompt</span><textarea name="prompt" required placeholder="Objective, constraints, and expected outcome" data-i18n-placeholder="placeholders.prompt"></textarea></label>
        <label class="field wide"><span data-i18n="fields.acceptanceCommands">Acceptance commands</span><textarea name="acceptance_commands" placeholder="One command per line" data-i18n-placeholder="placeholders.acceptance"></textarea></label>
      </div>
      <div class="form-actions"><span id="createStatus" class="form-message"></span><button class="btn dialog-close" type="button" data-i18n="actions.cancel">Cancel</button><button class="btn primary" type="submit" data-i18n="actions.createTask">Create task</button></div>
    </form>
  </dialog>

  <dialog id="detailDialog" class="modal drawer">
    <div class="modal-head"><div><h2 id="detailTitle">Task</h2><span id="detailSubtitle" class="updated"></span></div><button class="icon-btn dialog-close" type="button" aria-label="Close" data-i18n-aria-label="actions.close">×</button></div>
    <div class="modal-body">
      <div id="detailBody" class="detail-grid"></div>
      <section class="detail-section"><h3 data-i18n="detail.agentConfiguration">Agent configuration</h3><div class="form-grid"><label class="field"><span data-i18n="fields.model">Model</span><select id="detailModel"></select></label><label class="field"><span data-i18n="fields.reasoning">Reasoning</span><select id="detailReasoning"><option value="" data-i18n="common.inheritDefault">Inherit default</option><option>minimal</option><option>low</option><option>medium</option><option>high</option><option>xhigh</option></select></label></div><div class="form-actions"><span id="detailStatus" class="form-message"></span><button id="saveAgent" class="btn" type="button" data-i18n="actions.saveNextTurn">Save for next turn</button></div></section>
      <section class="detail-section"><h3 data-i18n="detail.acceptance">Acceptance</h3><pre id="detailAcceptance">No commands configured</pre></section>
      <section class="detail-section"><h3 data-i18n="detail.recentEvents">Recent events</h3><pre id="detailEvents">Loading…</pre></section>
      <div class="form-actions"><button id="copyWorktree" class="btn" type="button" data-i18n="actions.copyWorktree">Copy worktree</button><button id="copyThread" class="btn" type="button" data-i18n="actions.copyThread">Copy thread ID</button><button id="retryTask" class="btn" type="button" data-i18n="actions.retry">Retry</button><button id="cancelTask" class="btn danger" type="button" data-i18n="actions.cancelTask">Cancel task</button></div>
    </div>
  </dialog>

  <script>
    const I18N = {
      en: {
        'language.label':'Language', 'hero.title':'Task board', 'hero.subtitle':'Persistent Codex work, organized by lifecycle and kept safe across processes.',
        'metrics.label':'Runtime overview', 'metrics.workers':'Workers', 'metrics.capacity':'Active scheduler capacity', 'metrics.maxParallel':'Max parallel', 'metrics.maxParallelTasks':'Maximum parallel tasks', 'metrics.fiveHour':'5-hour usage', 'metrics.weekly':'Weekly usage',
        'quota.checking':'Checking', 'quota.unknown':'Unknown', 'quota.noData':'No data', 'quota.unavailable':'Unavailable', 'quota.used':'{value}% used', 'quota.remaining':'{value}% remaining', 'quota.resetUnavailable':'Reset time unavailable', 'quota.resets':'Resets {value}',
        'board.search':'Search tasks', 'board.newTask':'＋ New task', 'board.empty':'No tasks in this pool',
        'lane.backlog':'Backlog', 'lane.ready':'Ready', 'lane.active':'Active', 'lane.waiting':'Waiting', 'lane.attention':'Needs attention', 'lane.completed':'Completed',
        'pool.freezeOnReset':'Freeze on weekly reset', 'pool.draining':'Weekly reset detected. {count} grandfathered {tasks} may continue; new tasks will not start.', 'pool.frozen':'Harbor is frozen after the weekly drain. {count} {tasks} remain queued until manual resume.', 'pool.paused':'Scheduling is paused. Running tasks may finish, but no new task will start.',
        'actions.pause':'Pause', 'actions.freeze':'Freeze', 'actions.resume':'Resume', 'actions.close':'Close', 'actions.cancel':'Cancel', 'actions.createTask':'Create task', 'actions.saveNextTurn':'Save for next turn', 'actions.copyWorktree':'Copy worktree', 'actions.copyThread':'Copy thread ID', 'actions.retry':'Retry', 'actions.cancelTask':'Cancel task',
        'create.title':'Create Harbor task', 'create.repoHint':'The repository must already be registered.',
        'fields.title':'Title', 'fields.repository':'Repository', 'fields.backend':'Execution backend', 'fields.priority':'Priority', 'fields.maxAttempts':'Failure retry limit', 'fields.model':'Model', 'fields.reasoning':'Reasoning', 'fields.profile':'Profile', 'fields.exclusiveGroup':'Exclusive group', 'fields.dependencies':'Dependencies', 'fields.description':'Description', 'fields.prompt':'Prompt', 'fields.acceptanceCommands':'Acceptance commands',
        'placeholders.taskTitle':'A concrete task title', 'placeholders.description':'Useful context for operators', 'placeholders.prompt':'Objective, constraints, and expected outcome', 'placeholders.acceptance':'One command per line',
        'backend.local':'Local', 'common.inheritDefault':'Inherit default', 'common.optional':'Optional', 'common.none':'None', 'common.default':'default', 'common.noCommands':'No commands configured', 'common.noEvents':'No events recorded',
        'detail.agentConfiguration':'Agent configuration', 'detail.acceptance':'Acceptance', 'detail.recentEvents':'Recent events', 'detail.status':'Status', 'detail.priority':'Priority', 'detail.requestedAgent':'Requested agent', 'detail.effectiveAgent':'Effective agent', 'detail.pendingAgent':'Pending agent', 'detail.turn':'Execution turns', 'detail.failures':'Counted failures', 'detail.latestTurn':'Latest Codex turn', 'detail.worker':'Worker', 'detail.dependencies':'Dependencies', 'detail.rootThread':'Root thread', 'detail.activeThread':'Active thread', 'detail.worktree':'Worktree', 'detail.blockedReason':'Blocked reason',
        'runtime.idle':'Idle', 'runtime.active':'{count} active', 'runtime.connecting':'Connecting…', 'runtime.updated':'Updated {time}', 'runtime.disconnected':'Disconnected', 'runtime.apiUnavailable':'Harbor API unavailable: {message}',
        'options.registerRepo':'Register a repository with harbor repo add', 'options.defaultMarker':'default',
        'messages.creating':'Creating…', 'messages.saved':'Saved', 'messages.copied':'{label} copied', 'messages.copyFailed':'Copy failed: {value}', 'messages.worktreePath':'Worktree path', 'messages.threadId':'Thread ID',
        'task.turnFailures':'Turn {turn} · failures {failures}/{max}', 'task.taskOne':'task', 'task.taskMany':'tasks',
        'theme.useLight':'Use light theme', 'theme.useDark':'Use dark theme',
        'status.CREATED':'Created', 'status.PENDING':'Pending', 'status.WAIT_DEP':'Waiting for dependencies', 'status.READY':'Ready', 'status.CLAIMED':'Claimed', 'status.RUNNING':'Running', 'status.WAIT_QUOTA':'Waiting for quota', 'status.RETRY_WAIT':'Retry waiting', 'status.BLOCKED':'Blocked', 'status.SUCCEEDED':'Succeeded', 'status.FAILED':'Failed', 'status.CANCELLED':'Cancelled',
        'poolState.RUNNING':'Running', 'poolState.PAUSED':'Paused', 'poolState.DRAINING':'Draining', 'poolState.FROZEN':'Frozen'
      },
      'zh-CN': {
        'language.label':'语言', 'hero.title':'任务看板', 'hero.subtitle':'按生命周期组织持久化 Codex 任务，并确保任务可跨进程安全恢复。',
        'metrics.label':'运行状态概览', 'metrics.workers':'工作进程', 'metrics.capacity':'调度器可用容量', 'metrics.maxParallel':'最大并行', 'metrics.maxParallelTasks':'最大并行任务数', 'metrics.fiveHour':'5 小时额度', 'metrics.weekly':'周额度',
        'quota.checking':'检查中', 'quota.unknown':'未知', 'quota.noData':'暂无数据', 'quota.unavailable':'不可用', 'quota.used':'已使用 {value}%', 'quota.remaining':'剩余 {value}%', 'quota.resetUnavailable':'暂无重置时间', 'quota.resets':'重置时间 {value}',
        'board.search':'搜索任务', 'board.newTask':'＋ 新建任务', 'board.empty':'该状态池暂无任务',
        'lane.backlog':'待处理', 'lane.ready':'就绪', 'lane.active':'执行中', 'lane.waiting':'等待中', 'lane.attention':'需要处理', 'lane.completed':'已完成',
        'pool.freezeOnReset':'周额度重置后冻结', 'pool.draining':'检测到周额度重置。{count} 个存量任务可继续执行；新任务暂不启动。', 'pool.frozen':'周额度排空后 Harbor 已冻结。仍有 {count} 个任务排队，需手动恢复。', 'pool.paused':'调度已暂停。运行中的任务可以完成，但不会启动新任务。',
        'actions.pause':'暂停', 'actions.freeze':'冻结', 'actions.resume':'恢复', 'actions.close':'关闭', 'actions.cancel':'取消', 'actions.createTask':'创建任务', 'actions.saveNextTurn':'保存并在下一轮生效', 'actions.copyWorktree':'复制工作树路径', 'actions.copyThread':'复制线程 ID', 'actions.retry':'重试', 'actions.cancelTask':'取消任务',
        'create.title':'创建 Harbor 任务', 'create.repoHint':'仓库必须已经在 Harbor 中注册。',
        'fields.title':'标题', 'fields.repository':'仓库', 'fields.backend':'执行后端', 'fields.priority':'优先级', 'fields.maxAttempts':'失败重试上限', 'fields.model':'模型', 'fields.reasoning':'推理等级', 'fields.profile':'配置模板', 'fields.exclusiveGroup':'互斥组', 'fields.dependencies':'依赖任务', 'fields.description':'说明', 'fields.prompt':'任务提示词', 'fields.acceptanceCommands':'验收命令',
        'placeholders.taskTitle':'输入明确的任务标题', 'placeholders.description':'供管理者查看的补充信息', 'placeholders.prompt':'目标、约束和预期结果', 'placeholders.acceptance':'每行一条命令',
        'backend.local':'本机', 'common.inheritDefault':'继承默认值', 'common.optional':'可选', 'common.none':'无', 'common.default':'默认', 'common.noCommands':'未配置验收命令', 'common.noEvents':'暂无事件记录',
        'detail.agentConfiguration':'Agent 配置', 'detail.acceptance':'验收命令', 'detail.recentEvents':'最近事件', 'detail.status':'状态', 'detail.priority':'优先级', 'detail.requestedAgent':'请求配置', 'detail.effectiveAgent':'实际配置', 'detail.pendingAgent':'待生效配置', 'detail.turn':'执行轮次', 'detail.failures':'计入预算的失败', 'detail.latestTurn':'最近 Codex Turn', 'detail.worker':'工作进程', 'detail.dependencies':'依赖任务', 'detail.rootThread':'根线程', 'detail.activeThread':'活动线程', 'detail.worktree':'工作树', 'detail.blockedReason':'阻塞原因',
        'runtime.idle':'空闲', 'runtime.active':'{count} 个活动', 'runtime.connecting':'连接中…', 'runtime.updated':'更新于 {time}', 'runtime.disconnected':'连接已断开', 'runtime.apiUnavailable':'Harbor API 不可用：{message}',
        'options.registerRepo':'请先使用 harbor repo add 注册仓库', 'options.defaultMarker':'默认',
        'messages.creating':'正在创建…', 'messages.saved':'已保存', 'messages.copied':'已复制{label}', 'messages.copyFailed':'复制失败：{value}', 'messages.worktreePath':'工作树路径', 'messages.threadId':'线程 ID',
        'task.turnFailures':'第 {turn} 轮 · 失败 {failures}/{max}', 'task.taskOne':'任务', 'task.taskMany':'任务',
        'theme.useLight':'切换到白天模式', 'theme.useDark':'切换到黑夜模式',
        'status.CREATED':'已创建', 'status.PENDING':'待调度', 'status.WAIT_DEP':'等待依赖', 'status.READY':'就绪', 'status.CLAIMED':'已领取', 'status.RUNNING':'运行中', 'status.WAIT_QUOTA':'等待额度', 'status.RETRY_WAIT':'等待重试', 'status.BLOCKED':'已阻塞', 'status.SUCCEEDED':'已成功', 'status.FAILED':'已失败', 'status.CANCELLED':'已取消',
        'poolState.RUNNING':'运行中', 'poolState.PAUSED':'已暂停', 'poolState.DRAINING':'排空中', 'poolState.FROZEN':'已冻结'
      }
    };
    const LANES = [
      {id:'backlog', titleKey:'lane.backlog', states:['CREATED','PENDING','WAIT_DEP']},
      {id:'ready', titleKey:'lane.ready', states:['READY']},
      {id:'active', titleKey:'lane.active', states:['CLAIMED','RUNNING']},
      {id:'waiting', titleKey:'lane.waiting', states:['WAIT_QUOTA','RETRY_WAIT']},
      {id:'attention', titleKey:'lane.attention', states:['BLOCKED','FAILED']},
      {id:'completed', titleKey:'lane.completed', states:['SUCCEEDED','CANCELLED']}
    ];
    const state = {tasks:[], models:[], profiles:[], repositories:[], quotas:[], workers:[], pool:null, selectedTask:null, language:'en'};
    const byId = id => document.getElementById(id);
    const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const basename = path => String(path || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || 'repository';
    const t = (key, values={}) => {
      const template = I18N[state.language]?.[key] ?? I18N.en[key] ?? key;
      return Object.entries(values).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), template);
    };

    async function request(path, options={}) {
      const response = await fetch(path, options);
      const data = response.status === 204 ? null : await response.json();
      if (!response.ok) throw new Error(data?.detail || `${response.status} ${response.statusText}`);
      return data;
    }

    function applyTheme(theme) {
      document.documentElement.dataset.theme = theme;
      byId('themeToggle').textContent = theme === 'dark' ? '☀' : '☾';
      byId('themeToggle').title = theme === 'dark' ? t('theme.useLight') : t('theme.useDark');
      byId('themeToggle').setAttribute('aria-label', byId('themeToggle').title);
      localStorage.setItem('harbor-theme', theme);
    }
    function initializeTheme() {
      const requested = new URLSearchParams(location.search).get('theme');
      const saved = localStorage.getItem('harbor-theme');
      applyTheme(['light','dark'].includes(requested) ? requested : (saved || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')));
    }

    function applyLanguage(language, persist=true) {
      state.language = language === 'zh-CN' ? 'zh-CN' : 'en';
      document.documentElement.lang = state.language;
      byId('languageSelect').value = state.language;
      document.querySelectorAll('[data-i18n]').forEach(element => { element.textContent = t(element.dataset.i18n); });
      document.querySelectorAll('[data-i18n-placeholder]').forEach(element => { element.placeholder = t(element.dataset.i18nPlaceholder); });
      document.querySelectorAll('[data-i18n-aria-label]').forEach(element => { element.setAttribute('aria-label', t(element.dataset.i18nAriaLabel)); });
      if (persist) localStorage.setItem('harbor-language', state.language);
      if (document.documentElement.dataset.theme) applyTheme(document.documentElement.dataset.theme);
      renderOptions();
      if (state.pool) renderOverview(state.pool, state.tasks, state.quotas, state.workers);
      if (state.selectedTask && byId('detailDialog').open) showTask(state.selectedTask.id);
    }
    function initializeLanguage() {
      const requested = new URLSearchParams(location.search).get('lang');
      const saved = localStorage.getItem('harbor-language');
      const detected = navigator.language?.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
      applyLanguage(['en','zh-CN'].includes(requested) ? requested : (saved || detected), false);
    }

    function formatReset(value) {
      if (!value) return t('quota.resetUnavailable');
      const date = new Date(value);
      if (Number.isNaN(date.valueOf())) return t('quota.resets', {value});
      const formatted = new Intl.DateTimeFormat(state.language,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
      return t('quota.resets', {value:formatted});
    }
    function quotaView(quota, valueId, barId, resetId, availabilityId) {
      const used = quota?.used_percent;
      const remaining = quota?.remaining ?? (used == null ? null : Math.max(0, 100 - used));
      byId(valueId).textContent = remaining == null ? t('quota.unknown') : t('quota.remaining', {value:Math.round(remaining)});
      byId(barId).style.width = `${Math.min(100, Math.max(0, Number(remaining) || 0))}%`;
      byId(resetId).textContent = formatReset(quota?.reset_at);
      byId(availabilityId).textContent = quota ? (quota.available ? t('quota.used', {value:Math.round(used ?? 0)}) : t('quota.unavailable')) : t('quota.noData');
    }
    function taskAgent(task) { return `${task.model || t('common.default')} / ${task.reasoning_effort || t('common.default')}`; }
    function renderBoard() {
      const query = byId('searchInput').value.trim().toLowerCase();
      const filtered = state.tasks.filter(task => !query || [task.id, task.title, task.status, t(`status.${task.status}`), task.repository, task.model, task.reasoning_effort].some(value => String(value || '').toLowerCase().includes(query)));
      byId('board').innerHTML = LANES.map(lane => {
        const items = filtered.filter(task => lane.states.includes(task.status));
        const cards = items.map(task => `<button class="task-card" type="button" data-task-id="${esc(task.id)}"><span class="card-top"><span class="task-id">${esc(task.id)}</span><span class="status-chip" data-status="${esc(task.status)}">${esc(t(`status.${task.status}`))}</span></span><span class="task-title">${esc(task.title)}</span><span class="card-meta"><span class="meta-tag">${esc(taskAgent(task))}</span><span class="meta-tag">P${esc(task.priority)}</span><span class="meta-tag">${esc(basename(task.repository))}</span>${task.current_attempt ? `<span class="meta-tag">${esc(t('task.turnFailures', {turn:task.current_attempt, failures:task.failure_count || 0, max:task.max_attempts}))}</span>` : ''}</span></button>`).join('');
        return `<section class="lane" data-lane="${lane.id}"><header class="lane-head"><span class="lane-title"><i class="lane-dot"></i>${esc(t(lane.titleKey))}</span><span class="count">${items.length}</span></header><div class="card-list">${cards || `<div class="empty-lane">${esc(t('board.empty'))}</div>`}</div></section>`;
      }).join('');
    }

    function renderOverview(pool, tasks, quotas, workers) {
      state.pool = pool;
      state.tasks = tasks;
      state.quotas = quotas;
      state.workers = workers;
      byId('poolPill').textContent = t(`poolState.${pool.state}`);
      byId('poolPill').dataset.state = pool.state;
      byId('weeklyFreeze').checked = Boolean(pool.freeze_on_weekly_reset);
      const maxWorkers = pool.max_workers ?? 3;
      byId('workers').textContent = `${workers.length} / ${maxWorkers}`;
      if (document.activeElement !== byId('maxWorkersInput')) byId('maxWorkersInput').value = maxWorkers;
      byId('workerState').textContent = workers.length ? t('runtime.active', {count:workers.length}) : t('runtime.idle');
      const poolNotice = byId('poolNotice');
      if (pool.state === 'DRAINING') {
        const draining = tasks.filter(task => task.grandfathered && !['SUCCEEDED','FAILED','CANCELLED','BLOCKED'].includes(task.status)).length;
        poolNotice.textContent = t('pool.draining', {count:draining, tasks:t(draining === 1 ? 'task.taskOne' : 'task.taskMany')});
        poolNotice.classList.add('show');
      } else if (pool.state === 'FROZEN') {
        const remaining = tasks.filter(task => !['SUCCEEDED','FAILED','CANCELLED','BLOCKED'].includes(task.status)).length;
        poolNotice.textContent = t('pool.frozen', {count:remaining, tasks:t(remaining === 1 ? 'task.taskOne' : 'task.taskMany')});
        poolNotice.classList.add('show');
      } else if (pool.state === 'PAUSED') {
        poolNotice.textContent = t('pool.paused');
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
        const time = new Date().toLocaleTimeString(state.language, {hour:'2-digit', minute:'2-digit', second:'2-digit'});
        byId('lastUpdated').textContent = t('runtime.updated', {time});
      } catch (error) {
        byId('errorNotice').textContent = t('runtime.apiUnavailable', {message:error.message});
        byId('errorNotice').classList.add('show');
        byId('lastUpdated').textContent = t('runtime.disconnected');
      }
    }

    function renderOptions() {
      const repositorySelect = byId('repositorySelect');
      const modelSelect = byId('modelSelect');
      const detailModel = byId('detailModel');
      const profileSelect = byId('profileSelect');
      const selected = {
        repository: repositorySelect.value,
        model: modelSelect.value,
        detailModel: detailModel.value,
        profile: profileSelect.value
      };
      repositorySelect.innerHTML = state.repositories.length
        ? state.repositories.map(repo => `<option value="${esc(repo.path)}">${esc(repo.name)} — ${esc(repo.path)}</option>`).join('')
        : `<option value="">${esc(t('options.registerRepo'))}</option>`;
      const modelOptions = `<option value="">${esc(t('common.inheritDefault'))}</option>` + state.models.map(model => `<option value="${esc(model.model)}">${esc(model.display_name)}${model.is_default ? ` (${esc(t('options.defaultMarker'))})` : ''}</option>`).join('');
      modelSelect.innerHTML = modelOptions;
      detailModel.innerHTML = modelOptions;
      profileSelect.innerHTML = `<option value="">${esc(t('common.none'))}</option>` + state.profiles.map(profile => `<option value="${esc(profile.name)}">${esc(profile.name)}</option>`).join('');
      if ([...repositorySelect.options].some(option => option.value === selected.repository)) repositorySelect.value = selected.repository;
      if ([...modelSelect.options].some(option => option.value === selected.model)) modelSelect.value = selected.model;
      if ([...detailModel.options].some(option => option.value === selected.detailModel)) detailModel.value = selected.detailModel;
      if ([...profileSelect.options].some(option => option.value === selected.profile)) profileSelect.value = selected.profile;
    }

    async function loadOptions() {
      const [repositories, models, profiles] = await Promise.all([request('/api/repositories'), request('/api/models'), request('/api/profiles')]);
      state.repositories = repositories;
      state.models = models;
      state.profiles = profiles;
      renderOptions();
    }

    function detailItem(label, value) { return `<div class="detail-item"><span class="label">${esc(label)}</span><span class="value">${esc(value ?? '—')}</span></div>`; }
    async function showTask(taskId) {
      try {
        const [task, events] = await Promise.all([request(`/api/tasks/${encodeURIComponent(taskId)}`), request(`/api/events?task_id=${encodeURIComponent(taskId)}&limit=40`)]);
        state.selectedTask = task;
        const latest = task.latest_attempt || {};
        const activeThread = (task.threads || []).at(-1) || {};
        byId('detailTitle').textContent = `${task.id} · ${task.title}`;
        byId('detailSubtitle').textContent = `${t(`status.${task.status}`)} · ${basename(task.repository)}`;
        byId('detailBody').innerHTML = [
          [t('detail.status'), t(`status.${task.status}`)], [t('detail.priority'), task.priority],
          [t('detail.requestedAgent'), taskAgent(task)], [t('detail.effectiveAgent'), `${latest.effective_model || '—'} / ${latest.effective_reasoning_effort || '—'}`],
          [t('detail.pendingAgent'), `${task.pending_model || '—'} / ${task.pending_reasoning_effort || '—'}`], [t('detail.turn'), task.current_attempt],
          [t('detail.failures'), `${task.failure_count || 0} / ${task.max_attempts}`], [t('detail.latestTurn'), latest.turn_id || '—'],
          [t('detail.worker'), task.worker?.worker_id || '—'], [t('detail.dependencies'), (task.depends_on || []).join(', ') || t('common.none')],
          [t('detail.rootThread'), task.root_thread_id || '—'], [t('detail.activeThread'), activeThread.thread_id || '—'],
          [t('detail.worktree'), task.worktree_path || '—'], [t('detail.blockedReason'), task.blocked_reason || '—']
        ].map(item => detailItem(item[0], item[1])).join('');
        byId('detailModel').value = task.model || '';
        byId('detailReasoning').value = task.reasoning_effort || '';
        byId('detailAcceptance').textContent = (task.acceptance_commands || []).join('\n') || t('common.noCommands');
        byId('detailEvents').textContent = events.map(event => `${event.timestamp}  ${event.event_type}\n${event.payload ? JSON.stringify(event.payload, null, 2) : ''}`).join('\n\n') || t('common.noEvents');
        byId('detailStatus').textContent = '';
        byId('retryTask').disabled = !['FAILED','BLOCKED','CANCELLED'].includes(task.status);
        byId('cancelTask').disabled = ['SUCCEEDED','CANCELLED'].includes(task.status);
        if (!byId('detailDialog').open) byId('detailDialog').showModal();
      } catch (error) { showError(error); }
    }

    function showError(error) {
      byId('errorNotice').textContent = error.message || String(error);
      byId('errorNotice').classList.add('show');
    }
    async function poolAction(action) { try { await request(`/api/pool/${action}`, {method:'POST'}); await refresh(); } catch (error) { showError(error); } }
    async function updateMaxWorkers(event) {
      const input = event.currentTarget;
      const maxWorkers = Number(input.value);
      if (!Number.isInteger(maxWorkers) || maxWorkers < 1 || maxWorkers > 64) {
        input.value = state.pool?.max_workers ?? 3;
        return;
      }
      input.disabled = true;
      try {
        await request('/api/pool', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({max_workers:maxWorkers})});
        await refresh();
      } catch (error) {
        input.value = state.pool?.max_workers ?? 3;
        showError(error);
      } finally {
        input.disabled = false;
      }
    }
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
      try { await navigator.clipboard.writeText(value); byId('detailStatus').textContent = t('messages.copied', {label}); }
      catch { byId('detailStatus').textContent = t('messages.copyFailed', {value}); }
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
      byId('createStatus').textContent = t('messages.creating');
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
    byId('languageSelect').addEventListener('change', event => applyLanguage(event.target.value));
    byId('searchInput').addEventListener('input', renderBoard);
    byId('newTaskButton').addEventListener('click', () => { byId('createStatus').textContent = ''; byId('createDialog').showModal(); });
    document.querySelectorAll('.dialog-close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
    document.querySelectorAll('.pool-action').forEach(button => button.addEventListener('click', () => poolAction(button.dataset.action)));
    byId('weeklyFreeze').addEventListener('change', async event => { try { await request('/api/pool', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({freeze_on_weekly_reset:event.target.checked})}); await refresh(); } catch (error) { event.target.checked = !event.target.checked; showError(error); } });
    byId('maxWorkersInput').addEventListener('change', updateMaxWorkers);
    byId('board').addEventListener('click', event => { const card = event.target.closest('[data-task-id]'); if (card) showTask(card.dataset.taskId); });
    byId('createForm').addEventListener('submit', createTask);
    byId('saveAgent').addEventListener('click', async () => { if (!state.selectedTask) return; try { const body={model:byId('detailModel').value || null, reasoning_effort:byId('detailReasoning').value || null}; await request(`/api/tasks/${encodeURIComponent(state.selectedTask.id)}/agent`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); byId('detailStatus').textContent=t('messages.saved'); await refresh(); } catch(error) { byId('detailStatus').textContent=error.message; } });
    byId('retryTask').addEventListener('click', () => taskAction('retry'));
    byId('cancelTask').addEventListener('click', () => taskAction('cancel'));
    byId('copyWorktree').addEventListener('click', () => copyValue(state.selectedTask?.worktree_path, t('messages.worktreePath')));
    byId('copyThread').addEventListener('click', () => copyValue(state.selectedTask?.root_thread_id, t('messages.threadId')));
    document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); }));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });

    initializeLanguage();
    initializeTheme();
    Promise.all([loadOptions(), refresh()]).catch(showError);
    setInterval(() => { if (!document.hidden) refresh(); }, 3000);
  </script>
</body>
</html>
"""
