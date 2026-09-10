// Shared desktop/browser navigation. All data comes from the existing local API.
(() => {
  const copy = {
    'zh-CN': {tasks:'任务中心',recovery:'恢复保护',repositories:'工作空间',activity:'运行记录',settings:'偏好设置',local:'任务留在本机，工作持续向前。',subtitle:'让每一项工作，从容抵达。',refresh:'刷新',empty:'这里还没有记录',cancel:'取消保护',add:'添加',path:'Git 仓库绝对路径',reserve:'允许在额度耗尽时使用储备模型补写续接摘要',scheduling:'调度与额度',desktop:'桌面与后台',desktopHelp:'关闭桌面窗口后，任务继续运行。点击系统托盘图标重新打开；右键可暂停、恢复、设置登录后启动或退出。退出应用会停止它启动的服务；独立启动的服务继续运行。',appearance:'外观与语言',appearanceHelp:'使用右上角切换语言和明暗主题，偏好自动保存在本机。',protect:'登记恢复保护',thread:'原对话 Thread ID',model:'原主模型',reasoning:'推理等级',prompt:'恢复后继续执行的任务',repo:'工作目录（可选）',save:'登记保护',recoveryHelp:'额度耗尽后，回到原对话继续工作。登记时请填写原主模型和推理等级。',loading:'正在加载…'},
    en: {tasks:'Tasks',recovery:'Recovery',repositories:'Workspaces',activity:'Activity',settings:'Preferences',local:'Local work. Lasting progress.',subtitle:'A calm place for work that keeps moving.',refresh:'Refresh',empty:'No records yet',cancel:'Cancel protection',add:'Add',path:'Absolute Git repository path',reserve:'Allow reserve model to prepare a recovery summary',scheduling:'Scheduling & quota',desktop:'Desktop & background',desktopHelp:'Close the desktop window to keep tasks running. Click its tray icon to reopen; right-click to pause, resume, enable Windows login startup, or quit. Quitting stops the service started by this app. Independently started services remain running.',appearance:'Appearance & language',appearanceHelp:'Use the top-right controls to change language and theme. Preferences are saved locally.',protect:'Protect a conversation',thread:'Original conversation Thread ID',model:'Original model',reasoning:'Reasoning effort',prompt:'Work to continue after recovery',repo:'Working directory (optional)',save:'Register protection',recoveryHelp:'Continue in the original conversation after quota recovery. Use the original model and reasoning effort.',loading:'Loading…'}
  };
  let selected = 'tasks';
  let generation = 0;
  const c = key => copy[state.language][key] || key;
  const content = byId('panelContent');
  const settings = document.createElement('div');
  settings.className = 'settings-controls';
  const parking = document.createElement('div');
  parking.hidden = true;
  document.body.append(parking);
  parking.append(settings);
  for (const id of ['weeklyFreeze','weeklyPing']) settings.append(byId(id).closest('label'));
  settings.append(byId('weeklyPingStatus'));
  settings.append(byId('maxWorkersInput').closest('label'));
  const heading = () => {
    document.querySelectorAll('[data-copy]').forEach(el => el.textContent = c(el.dataset.copy));
    document.querySelector('.hero h1').textContent = c(selected);
    document.querySelector('.hero p').textContent = c('subtitle');
  };
  const card = (title, body) => `<article class="panel-card"><h2>${esc(title)}</h2>${body}</article>`;
  const empty = () => `<div class="panel-empty">${esc(c('empty'))}</div>`;
  async function show(page) {
    selected = page;
    const ticket = ++generation;
    document.querySelector('.page').dataset.currentPage = page;
    document.querySelectorAll('[data-page]').forEach(el => {el.classList.toggle('active', el.dataset.page === page);el.setAttribute('aria-current', el.dataset.page === page ? 'page' : 'false');});
    byId('desktopPanel').hidden = page === 'tasks';
    heading();
    if (page === 'tasks') return;
    parking.append(settings);
    content.replaceChildren();
    content.innerHTML = `<p class="muted">${esc(c('loading'))}</p>`;
    try {
      if (page === 'settings') {
        const data = await request('/api/recovery-settings');
        if (ticket !== generation) return;
        content.innerHTML = card(c('scheduling'), '<div id="schedulerSettings"></div>') + card(c('desktop'), `<p>${esc(c('desktopHelp'))}</p>`) + card(c('appearance'), `<p>${esc(c('appearanceHelp'))}</p>`);
        byId('schedulerSettings').append(settings);
        const label = document.createElement('label');
        label.className='switch-label';
        label.innerHTML=`<input type="checkbox" ${data.allow_luna_reserve ? 'checked' : ''}><span>${esc(c('reserve'))}</span>`;
        byId('schedulerSettings').append(label);
        label.style.marginTop='22px';
        label.firstChild.onchange = async event => {
          event.target.disabled=true;
          try {await request('/api/recovery-settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({allow_luna_reserve:event.target.checked})});}
          catch(error){event.target.checked=!event.target.checked;showError(error);}
          finally{event.target.disabled=false;}
        };
      } else if (page === 'recovery') {
        const watches = await request('/api/recovery-watches');
        if (ticket !== generation) return;
        content.innerHTML = card(c('recovery'), `<div class="panel-heading"><p>${esc(c('recoveryHelp'))}</p><button class="btn" id="panelRefresh">${esc(c('refresh'))}</button></div>` + (watches.length ? watches.map(w => `<div class="panel-row"><div class="row-body"><strong>${esc(w.title || w.id)}</strong><small>${esc(w.state)} · ${esc(w.model)} · ${esc(w.reasoning_effort)}</small><small>${esc(w.thread_id)}${w.task_id ? ' · '+esc(w.task_id) : ''}</small></div>${['ARMED','WAITING'].includes(w.state) ? `<button class="btn danger" data-cancel-watch="${esc(w.id)}">${esc(c('cancel'))}</button>` : ''}</div>`).join('') : empty())) + card(c('protect'), `<form id="protectForm" class="panel-form">${[['thread_id','thread'],['model','model'],['reasoning_effort','reasoning'],['repository','repo']].map(([name,key])=>`<label>${esc(c(key))}<input name="${name}" ${name==='repository'?'':'required'}></label>`).join('')}<label>${esc(c('prompt'))}<textarea name="prompt" required></textarea></label><span class="panel-status" role="status"></span><button class="btn primary" type="submit">${esc(c('save'))}</button></form>`);
        byId('protectForm').onsubmit = async event => {
          event.preventDefault();const form=event.target;const button=form.querySelector('button');button.disabled=true;
          const body=Object.fromEntries(new FormData(form));if(!body.repository)delete body.repository;
          try{await request('/api/recovery-watches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});show(page);}
          catch(error){form.querySelector('.panel-status').textContent=error.message;button.disabled=false;}
        };
      } else if (page === 'repositories') {
        const repos = await request('/api/repositories');
        if (ticket !== generation) return;
        content.innerHTML=card(c('repositories'),`<form id="repoForm" class="inline-form"><input name="path" required aria-label="${esc(c('path'))}" placeholder="${esc(c('path'))}"><button class="btn primary">${esc(c('add'))}</button></form><div class="panel-status" role="status"></div>`+(repos.length?repos.map(r=>`<div class="panel-row"><div class="row-body"><strong>${esc(r.name || basename(r.path))}</strong><small>${esc(r.path)}</small></div></div>`).join(''):empty()));
        byId('repoForm').onsubmit=async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{await request('/api/repositories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});show(page);}catch(error){content.querySelector('.panel-status').textContent=error.message;button.disabled=false;}};
      } else {
        const events = await request('/api/events?limit=100');
        if (ticket !== generation) return;
        content.innerHTML=card(c('activity'),`<button class="btn" id="panelRefresh">${esc(c('refresh'))}</button>`+(events.length?events.map(e=>`<details class="panel-row"><summary>${esc(e.event_type || e.type)} · ${esc(e.task_id || 'Harbor')} <small>${esc(e.created_at)}</small></summary><pre>${esc(JSON.stringify(e,null,2))}</pre></details>`).join(''):empty()));
      }
      if(byId('panelRefresh'))byId('panelRefresh').onclick=()=>show(page);
    } catch(error) {if(ticket===generation)content.innerHTML=card(c(page),`<p class="panel-status">${esc(error.message)}</p><button class="btn" id="retryPanel">${esc(c('refresh'))}</button>`);if(byId('retryPanel'))byId('retryPanel').onclick=()=>show(page);}
  }
  document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>show(el.dataset.page));
  content.addEventListener('click',async event=>{const button=event.target.closest('[data-cancel-watch]');if(!button)return;button.disabled=true;try{await request(`/api/recovery-watches/${encodeURIComponent(button.dataset.cancelWatch)}/cancel`,{method:'POST'});show('recovery');}catch(error){showError(error);button.disabled=false;}});
  byId('languageSelect').addEventListener('change',()=>show(selected));
  document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='k'){event.preventDefault();show('tasks');byId('searchInput').focus();}});
  heading();
})();
