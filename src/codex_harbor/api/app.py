from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ..domain import PoolStatus, TaskSpec
from ..storage import HarborRepository


class TaskCreate(BaseModel):
    id: str | None = None
    title: str
    repository: str
    prompt: str
    description: str = ""
    execution_backend: str = "local"
    priority: int = 100
    depends_on: list[str] = Field(default_factory=list)
    exclusive_group: str | None = None
    acceptance_commands: list[str] = Field(default_factory=list)
    max_attempts: int = 5
    model: str | None = None
    reasoning_effort: str | None = None
    profile: str | None = None


class TaskPatch(BaseModel):
    model: str | None = None
    reasoning_effort: str | None = None


class RepositoryCreate(BaseModel):
    path: str


DASHBOARD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Codex Harbor</title><style>
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui;background:#07111d;color:#e8f0f7}
body{margin:0;background:radial-gradient(circle at 20% 0,#123351 0,#07111d 42%);min-height:100vh}
main{max-width:1180px;margin:auto;padding:32px}.top{display:flex;justify-content:space-between;align-items:center}
h1{letter-spacing:.12em;font-size:22px}.badge{padding:8px 14px;border:1px solid #37d6ac;border-radius:999px;color:#67f2c9}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}.card{background:#0c1b2a;border:1px solid #1b3a52;border-radius:14px;padding:18px;box-shadow:0 12px 40px #0005}
.metric{font-size:30px;font-weight:700}.muted{color:#8fa9bd}.bar{height:8px;background:#173247;border-radius:8px;overflow:hidden;margin-top:10px}.bar i{display:block;height:100%;background:#37d6ac}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:13px;border-bottom:1px solid #1b3345}th{color:#7fa2bc;font-size:12px;text-transform:uppercase}
button{background:#37d6ac;color:#062118;border:0;border-radius:8px;padding:9px 13px;font-weight:700;cursor:pointer}button.alt{background:#1a3549;color:#d8e7f1}
.actions{display:flex;gap:8px}.status{font-family:ui-monospace,SFMono-Regular,monospace;color:#68c9ff}@media(max-width:760px){.grid{grid-template-columns:1fr}.hide-mobile{display:none}}
.formgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.wide{grid-column:1/-1}label{display:flex;flex-direction:column;gap:6px;color:#8fa9bd;font-size:12px}input,textarea,select{background:#071421;color:#e8f0f7;border:1px solid #29465b;border-radius:8px;padding:10px}textarea{min-height:72px}summary{cursor:pointer;font-weight:700}.detailgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.detailgrid div{padding:8px;background:#091724;border-radius:7px}@media(max-width:760px){.formgrid,.detailgrid{grid-template-columns:1fr}}
</style></head><body><main><div class="top"><h1>CODEX HARBOR</h1><span id="pool" class="badge">LOADING</span></div>
<section class="grid"><div class="card"><div class="muted">Workers</div><div id="workers" class="metric">—</div></div><div class="card"><div class="muted">5H usage</div><div id="five" class="metric">—</div><div class="bar"><i id="fivebar"></i></div></div><div class="card"><div class="muted">Weekly usage</div><div id="weekly" class="metric">—</div><div class="bar"><i id="weekbar"></i></div></div></section>
<details class="card"><summary>Create task</summary><form id="createForm" class="formgrid" onsubmit="createTask(event)"><label>Title<input name="title" required></label><label>Repository<input name="repository" required></label><label>Backend<select name="execution_backend"><option>local</option><option>linux</option><option>wsl</option><option>windows</option></select></label><label>Priority<input name="priority" type="number" value="100"></label><label>Dependencies (comma-separated)<input name="depends_on"></label><label>Exclusive group<input name="exclusive_group"></label><label>Model<input name="model"></label><label>Reasoning<select name="reasoning_effort"><option value="">inherit</option><option>minimal</option><option>low</option><option>medium</option><option>high</option><option>xhigh</option></select></label><label>Profile<input name="profile"></label><label>Max attempts<input name="max_attempts" type="number" value="5" min="1"></label><label class="wide">Description<textarea name="description"></textarea></label><label class="wide">Prompt<textarea name="prompt" required></textarea></label><label class="wide">Acceptance commands (one per line)<textarea name="acceptance_commands"></textarea></label><div><button type="submit">Create Task</button> <span id="createStatus" class="muted"></span></div></form></details>
<section class="card"><div class="top"><h2>Tasks</h2><div class="actions"><button class="alt" onclick="poolAction('pause')">Pause</button><button class="alt" onclick="poolAction('freeze')">Freeze</button><button onclick="poolAction('resume')">Resume</button></div></div><table><thead><tr><th>ID</th><th>Status</th><th>Agent</th><th>Title</th><th class="hide-mobile">Priority</th></tr></thead><tbody id="tasks"></tbody></table></section>
<section id="detail" class="card" hidden><div class="top"><h2 id="detailTitle">Task</h2><div class="actions"><button class="alt" onclick="taskAction('retry')">Retry</button><button class="alt" onclick="taskAction('cancel')">Cancel</button></div></div><div id="detailBody" class="detailgrid"></div><h3>Recent events</h3><pre id="detailEvents"></pre></section>
</main><script>
const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
async function get(p){return (await fetch(p)).json()} async function poolAction(a){await fetch('/api/pool/'+a,{method:'POST'});refresh()}
let selectedTask=null;async function createTask(e){e.preventDefault();let f=new FormData(e.target),body=Object.fromEntries(f);body.priority=Number(body.priority);body.max_attempts=Number(body.max_attempts);body.depends_on=body.depends_on?body.depends_on.split(',').map(x=>x.trim()).filter(Boolean):[];body.acceptance_commands=body.acceptance_commands?body.acceptance_commands.split('\n').map(x=>x.trim()).filter(Boolean):[];for(let k of ['model','reasoning_effort','profile','exclusive_group'])if(!body[k])body[k]=null;let r=await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let data=await r.json();createStatus.textContent=r.ok?'Created '+data.id:(data.detail||'Failed');if(r.ok){e.target.reset();showTask(data.id);refresh()}}
async function showTask(id){selectedTask=id;let [t,e]=await Promise.all([get('/api/tasks/'+id),get('/api/events?task_id='+id+'&limit=20')]);detail.hidden=false;detailTitle.textContent=t.id+' · '+t.title;let thread=(t.threads||[]).at(-1)||{};detailBody.innerHTML=[['Status',t.status],['Requested agent',(t.model||'default')+'/'+(t.reasoning_effort||'default')],['Pending agent',(t.pending_model||'—')+'/'+(t.pending_reasoning_effort||'—')],['Attempt',t.current_attempt+' / '+t.max_attempts],['Root thread',t.root_thread_id||'—'],['Active thread',thread.thread_id||'—'],['Worktree',t.worktree_path||'—'],['Blocked reason',t.blocked_reason||'—']].map(x=>`<div><span class="muted">${esc(x[0])}</span><br>${esc(x[1])}</div>`).join('');detailEvents.textContent=e.map(x=>x.timestamp+' '+x.event_type+' '+JSON.stringify(x.payload||{})).join('\n');detail.scrollIntoView({behavior:'smooth'})}
async function taskAction(action){if(!selectedTask)return;let r=await fetch('/api/tasks/'+selectedTask+'/'+action,{method:'POST'});if(!r.ok)alert((await r.json()).detail||'Action failed');await showTask(selectedTask);refresh()}
async function refresh(){let [p,t,q,w]=await Promise.all([get('/api/pool'),get('/api/tasks'),get('/api/quota'),get('/api/workers')]);
pool.textContent=p.state;workers.textContent=w.length+' active';let f=q.find(x=>x.quota_type==='PRIMARY_5H')||{},x=q.find(x=>x.quota_type==='WEEKLY')||{};
five.textContent=f.used_percent==null?'Unknown':f.used_percent+'%';weekly.textContent=x.used_percent==null?'Unknown':x.used_percent+'%';fivebar.style.width=(f.used_percent||0)+'%';weekbar.style.width=(x.used_percent||0)+'%';
tasks.innerHTML=t.map(i=>`<tr><td><a href="#detail" onclick="showTask('${esc(i.id)}')" class="status">${esc(i.id)}</a></td><td class="status">${esc(i.status)}</td><td>${esc(i.model||'default')}/${esc(i.reasoning_effort||'default')}</td><td>${esc(i.title)}</td><td class="hide-mobile">${esc(i.priority)}</td></tr>`).join('')||'<tr><td colspan="5" class="muted">No tasks</td></tr>'}
refresh();setInterval(refresh,3000)</script></body></html>"""


def create_app(repository: HarborRepository, *, model_registry: Any = None) -> FastAPI:
    app = FastAPI(title="Codex Harbor", version="0.1.0")

    def guard(call: Any) -> Any:
        try:
            return call()
        except KeyError as error:
            raise HTTPException(404, f"not found: {error.args[0]}") from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return DASHBOARD

    @app.get("/api/tasks")
    async def list_tasks() -> list[dict[str, Any]]:
        return repository.list_tasks()

    @app.get("/api/repositories")
    async def list_repositories() -> list[dict[str, Any]]:
        return repository.list_repositories()

    @app.post("/api/repositories", status_code=201)
    async def add_repository(body: RepositoryCreate) -> dict[str, Any]:
        return guard(lambda: repository.add_repository(body.path))

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.get_task(task_id))

    @app.post("/api/tasks", status_code=201)
    async def create_task(body: TaskCreate) -> dict[str, Any]:
        return guard(
            lambda: repository.create_task(
                TaskSpec(
                    task_id=body.id,
                    title=body.title,
                    repository=body.repository,
                    prompt=body.prompt,
                    description=body.description,
                    execution_backend=body.execution_backend,
                    priority=body.priority,
                    depends_on=body.depends_on,
                    exclusive_group=body.exclusive_group,
                    acceptance_commands=body.acceptance_commands,
                    max_attempts=body.max_attempts,
                    model=body.model,
                    reasoning_effort=body.reasoning_effort,
                    profile=body.profile,
                )
            )
        )

    @app.patch("/api/tasks/{task_id}")
    @app.patch("/api/tasks/{task_id}/agent")
    async def patch_task(task_id: str, body: TaskPatch) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "model" in body.model_fields_set:
            updates["model"] = body.model
        if "reasoning_effort" in body.model_fields_set:
            updates["reasoning"] = body.reasoning_effort
        return guard(lambda: repository.update_agent_config(task_id, **updates))

    @app.delete("/api/tasks/{task_id}", status_code=204)
    async def delete_task(task_id: str) -> None:
        guard(lambda: repository.delete_task(task_id))

    @app.post("/api/tasks/{task_id}/retry")
    async def retry_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.retry_task(task_id))

    @app.post("/api/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> dict[str, Any]:
        return guard(lambda: repository.cancel_task(task_id))

    @app.get("/api/pool")
    async def get_pool() -> dict[str, Any]:
        return repository.get_pool()

    @app.post("/api/pool/{action}")
    async def pool_action(action: str) -> dict[str, Any]:
        states = {
            "pause": PoolStatus.PAUSED,
            "freeze": PoolStatus.FROZEN,
            "resume": PoolStatus.RUNNING,
        }
        if action not in states:
            raise HTTPException(404, "unknown pool action")
        repository.set_pool(states[action], event_type=f"POOL_{action.upper()}D")
        return repository.get_pool()

    @app.get("/api/quota")
    async def quota() -> list[dict[str, Any]]:
        return repository.list_quotas()

    @app.get("/api/models")
    async def models() -> list[dict[str, Any]]:
        if model_registry is None:
            return []
        return [
            {
                "model": item.model,
                "display_name": item.display_name,
                "is_default": item.is_default,
                "reasoning_efforts": sorted(item.reasoning_efforts),
            }
            for item in model_registry.models.values()
        ]

    @app.get("/api/workers")
    async def workers() -> list[dict[str, Any]]:
        return repository.list_workers()

    @app.get("/api/events")
    async def events(
        task_id: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        return repository.list_events(task_id, min(max(limit, 1), 1000))

    return app
