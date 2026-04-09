// Shared utilities and components for the dashboard

const STAGES = ['eda', 'idea', 'literature', 'methods', 'results', 'paper'];
const STAGE_LABELS = { eda: 'EDA', idea: 'Idea', literature: 'Lit', methods: 'Methods', results: 'Results', paper: 'Paper' };

let expandedProjects = new Set();

// --- Data store (avoids inlining JSON in onclick attributes) ---
const _planStore = {};
let _planStoreId = 0;
function storePlan(plan) {
    const id = '_p' + (++_planStoreId);
    _planStore[id] = plan;
    return id;
}

const _configStore = {};
let _configStoreId = 0;
function storeConfig(config) {
    const id = '_c' + (++_configStoreId);
    _configStore[id] = config;
    return id;
}

// --- Card iteration navigation ---
const _cardProjects = {};  // key -> { scientist, proj, currentIter }

function registerCardProject(key, scientist, proj) {
    const maxIter = proj.iteration_count > 0 ? proj.iteration_count - 1 : 0;
    // Preserve current iteration if user navigated away from latest
    const prev = _cardProjects[key];
    const currentIter = prev != null ? Math.min(prev.currentIter, maxIter) : maxIter;
    _cardProjects[key] = { scientist, proj, currentIter };
}

function cardIterPrev(key) {
    const cp = _cardProjects[key];
    if (!cp || cp.currentIter <= 0) return;
    cp.currentIter--;
    updateCardIteration(key);
}

function cardIterNext(key) {
    const cp = _cardProjects[key];
    if (!cp || cp.currentIter >= cp.proj.iteration_count - 1) return;
    cp.currentIter++;
    updateCardIteration(key);
}

function updateCardIteration(key) {
    const cp = _cardProjects[key];
    if (!cp) return;
    const { proj, currentIter, scientist } = cp;
    const maxIter = proj.iteration_count - 1;

    // Update label
    const label = document.getElementById('iter-label-' + key);
    if (label) label.textContent = `${currentIter}/${maxIter}`;

    // Update pipeline bar
    const pipeline = document.getElementById('pipeline-' + key);
    if (pipeline) {
        const stages = proj.stages_by_iteration ? proj.stages_by_iteration[currentIter] || [] : proj.stages_completed;
        const iterPlan = (proj.plan_by_iteration && proj.plan_by_iteration[currentIter]) || null;
        pipeline.innerHTML = renderPipelineBar(stages, iterPlan, false, scientist, proj.name, proj.iteration_count, currentIter);
    }

    // Update plan summary
    const planSummary = document.getElementById('plan-summary-' + key);
    if (planSummary) {
        const iterPlan = (proj.plan_by_iteration && proj.plan_by_iteration[currentIter]) || null;
        planSummary.innerHTML = iterPlan ? renderPlanTable(iterPlan, key) : '';
    }
}

function toggleProject(key) {
    const el = document.getElementById('plan-' + key);
    if (!el) return;
    if (expandedProjects.has(key)) {
        expandedProjects.delete(key);
        el.classList.add('hidden');
    } else {
        expandedProjects.add(key);
        el.classList.remove('hidden');
        el.classList.add('fade-in');
    }
}

function statusColor(status) {
    return { idle: 'status-idle', busy: 'status-busy', error: 'status-error', offline: 'status-offline' }[status] || 'status-offline';
}

function statusLabel(status) {
    return { idle: 'Idle', busy: 'Busy', error: 'Error', offline: 'Offline' }[status] || 'Unknown';
}

function formatCost(dollars) {
    if (dollars == null) return '';
    if (dollars < 0.01) return `$${dollars.toFixed(4)}`;
    return `$${dollars.toFixed(2)}`;
}

function formatTime(seconds) {
    if (seconds == null) return '';
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}

function stepStatusIcon(status) {
    if (status === 'completed') return '<span class="text-green-500">&#10003;</span>';
    if (status === 'in_progress') return '<span class="text-amber-400">&#9679;</span>';
    return '<span class="text-gray-600">&mdash;</span>';
}

function renderPipelineBar(stagesCompleted, planExecution, isBusy, scientist, project, iterCount, currentIter) {
    let experimentDetail = '';
    if (planExecution && planExecution.steps) {
        const done = planExecution.steps.filter(s => s.status === 'completed').length;
        const total = planExecution.steps.length;
        const inProgress = planExecution.steps.find(s => s.status === 'in_progress');
        if (inProgress) {
            experimentDetail = `<div class="text-xs text-amber-400 mt-1">${inProgress.name} (${done}/${total})</div>`;
        } else if (done === total) {
            experimentDetail = `<div class="text-xs text-green-600 mt-1">${done}/${total} steps</div>`;
        }
    }

    let html = '<div class="progress-bar">';
    for (const stage of STAGES) {
        let cls = 'stage-pending';
        if (stagesCompleted.includes(stage)) cls = stage === 'paper' ? 'stage-paper' : 'stage-done';
        const clickable = stagesCompleted.includes(stage) && scientist && project;
        if (clickable) {
            const startIter = currentIter != null ? currentIter : (iterCount || 1) - 1;
            html += `<div class="stage-pill ${cls} stage-clickable" onclick="openStageModal('${scientist}','${project}','${stage}',${iterCount || 0},${startIter})">${STAGE_LABELS[stage]}</div>`;
        } else {
            html += `<div class="stage-pill ${cls}">${STAGE_LABELS[stage]}</div>`;
        }
    }
    html += '</div>';
    html += experimentDetail;
    return html;
}

// --- Stage content modal ---

// Current modal state
let _modal = { scientist: '', project: '', stage: '', iteration: 0, iterCount: 0 };

// Per-iteration stages (EDA and paper are not per-iteration)
const PER_ITERATION_STAGES = new Set(['idea', 'literature', 'methods', 'results']);

async function openStageModal(scientist, project, stage, iterCount, startIter) {
    let modal = document.getElementById('stage-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'stage-modal';
        modal.innerHTML = `
            <div class="stage-modal-backdrop" onclick="closeStageModal()"></div>
            <div class="stage-modal-content">
                <div class="stage-modal-header">
                    <div class="stage-modal-nav">
                        <span id="stage-modal-prev" class="stage-modal-arrow" onclick="modalPrev()">&larr;</span>
                        <span id="stage-modal-title"></span>
                        <span id="stage-modal-next" class="stage-modal-arrow" onclick="modalNext()">&rarr;</span>
                    </div>
                    <span class="stage-modal-close" onclick="closeStageModal()">&times;</span>
                </div>
                <div id="stage-modal-body" class="stage-modal-body">Loading...</div>
            </div>`;
        document.body.appendChild(modal);
    }

    const initIter = startIter != null ? startIter : Math.max(0, (iterCount || 1) - 1);
    _modal = { scientist, project, stage, iteration: initIter, iterCount: iterCount || 1 };
    modal.style.display = 'flex';
    await loadStageContent();
}

async function loadStageContent() {
    const { scientist, project, stage, iteration, iterCount } = _modal;
    const title = document.getElementById('stage-modal-title');
    const body = document.getElementById('stage-modal-body');
    const prev = document.getElementById('stage-modal-prev');
    const next = document.getElementById('stage-modal-next');

    const hasNav = PER_ITERATION_STAGES.has(stage) && iterCount > 1;
    prev.style.visibility = hasNav && iteration > 0 ? 'visible' : 'hidden';
    next.style.visibility = hasNav && iteration < iterCount - 1 ? 'visible' : 'hidden';

    const label = STAGE_LABELS[stage] || stage;
    title.textContent = hasNav ? `${label}  ${iteration}/${iterCount - 1}` : label;

    body.innerHTML = '<div style="color:#999">Loading...</div>';

    try {
        let url = `/api/stage?scientist=${encodeURIComponent(scientist)}&project=${encodeURIComponent(project)}&stage=${encodeURIComponent(stage)}`;
        if (PER_ITERATION_STAGES.has(stage)) url += `&iteration=${iteration}`;
        const resp = await fetch(url);
        if (!resp.ok) {
            body.innerHTML = '<div style="color:#c44">Content not available.</div>';
            return;
        }
        const data = await resp.json();
        if (data.filename && data.filename.endsWith('.tex')) {
            body.innerHTML = `<pre class="stage-tex-content">${escapeHtml(data.content)}</pre>`;
        } else if (typeof marked !== 'undefined') {
            body.innerHTML = `<div class="stage-md-content">${marked.parse(data.content)}</div>`;
            renderMath(body);
        } else {
            body.innerHTML = `<pre class="stage-tex-content">${escapeHtml(data.content)}</pre>`;
        }
    } catch (e) {
        body.innerHTML = '<div style="color:#c44">Failed to load content.</div>';
    }
}

function modalPrev() {
    if (_modal.iteration > 0) {
        _modal.iteration--;
        loadStageContent();
    }
}

function modalNext() {
    if (_modal.iteration < _modal.iterCount - 1) {
        _modal.iteration++;
        loadStageContent();
    }
}

function closeStageModal() {
    const modal = document.getElementById('stage-modal');
    if (modal) modal.style.display = 'none';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMath(container) {
    if (typeof renderMathInElement === 'function') {
        renderMathInElement(container, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false },
                { left: '\\(', right: '\\)', display: false },
                { left: '\\[', right: '\\]', display: true },
            ],
            throwOnError: false,
        });
    }
}

// Keyboard navigation for modal
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeStageModal();
    if (e.key === 'ArrowLeft') modalPrev();
    if (e.key === 'ArrowRight') modalNext();
});

function renderPlanTable(planExecution, projectKey) {
    if (!planExecution || !planExecution.steps) return '';
    const steps = planExecution.steps;
    const planning = planExecution.planning;

    let totalCost = (planning.cost_dollars || 0);
    let totalTime = (planning.time_seconds || 0);
    steps.forEach(s => { totalCost += (s.cost_dollars || 0); totalTime += (s.time_seconds || 0); });

    const done = steps.filter(s => s.status === 'completed').length;
    const inProgress = steps.find(s => s.status === 'in_progress');
    let statusText = `${done}/${steps.length} steps`;
    if (inProgress) statusText = `${inProgress.name} (${done}/${steps.length})`;

    const planId = storePlan(planExecution);
    let html = `<div class="mt-2">`;
    html += `<div class="expand-btn text-xs text-gray-500 flex items-center gap-1" onclick="openPlanModal('${planId}')">`;
    html += `<span>&#9654;</span>`;
    html += `<span>Plan: ${statusText}</span>`;
    html += `<span class="cost-badge ml-2">${formatCost(totalCost)}</span>`;
    html += `<span class="time-badge">${formatTime(totalTime)}</span>`;
    html += `</div></div>`;
    return html;
}

function openPlanModal(planId) {
    const plan = _planStore[planId];
    if (!plan) return;
    const steps = plan.steps;
    const planning = plan.planning;

    let totalCost = (planning.cost_dollars || 0);
    let totalTime = (planning.time_seconds || 0);
    steps.forEach(s => { totalCost += (s.cost_dollars || 0); totalTime += (s.time_seconds || 0); });

    let html = `<table class="w-full text-sm"><thead><tr class="text-gray-400 text-left border-b border-gray-700">`;
    html += `<th class="pb-2 w-8">#</th><th class="pb-2">Sub-task</th><th class="pb-2 w-20">Agent</th>`;
    html += `<th class="pb-2 w-16 text-right">Status</th><th class="pb-2 w-20 text-right">Time</th><th class="pb-2 w-20 text-right">Cost</th>`;
    html += `</tr></thead><tbody>`;

    html += `<tr class="text-gray-400 border-b border-gray-800"><td class="py-2"></td><td class="py-2">Planning</td><td></td>`;
    html += `<td class="py-2 text-right"><span class="text-green-500">&#10003;</span></td>`;
    html += `<td class="py-2 text-right">${formatTime(planning.time_seconds)}</td>`;
    html += `<td class="py-2 text-right">${formatCost(planning.cost_dollars)}</td></tr>`;

    for (const step of steps) {
        let attemptInfo = '';
        if (step.attempt != null && step.max_attempts != null) {
            const color = step.attempt > 3 ? 'text-amber-400' : 'text-gray-500';
            attemptInfo = ` <span class="${color}">(${step.attempt}/${step.max_attempts})</span>`;
        }
        html += `<tr class="border-b border-gray-800">`;
        html += `<td class="text-gray-500 py-2">${step.number}</td>`;
        html += `<td class="py-2 text-gray-200">${step.name}</td>`;
        html += `<td class="py-2 text-gray-500">${step.agent}</td>`;
        html += `<td class="py-2 text-right">${stepStatusIcon(step.status)}${attemptInfo}</td>`;
        html += `<td class="py-2 text-right text-gray-400">${formatTime(step.time_seconds)}</td>`;
        html += `<td class="py-2 text-right text-gray-400">${formatCost(step.cost_dollars)}</td>`;
        html += `</tr>`;
    }

    html += `<tr class="text-gray-200 font-medium"><td class="pt-2"></td><td class="pt-2">Total</td><td></td><td></td>`;
    html += `<td class="pt-2 text-right">${formatTime(totalTime)}</td>`;
    html += `<td class="pt-2 text-right">${formatCost(totalCost)}</td></tr>`;

    html += `</tbody></table>`;

    let modal = document.getElementById('plan-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'plan-modal';
        modal.innerHTML = `
            <div class="plan-modal-backdrop" onclick="closePlanModal()"></div>
            <div class="plan-modal-content">
                <div class="plan-modal-header">
                    <span>Execution Plan</span>
                    <span class="plan-modal-close" onclick="closePlanModal()">&times;</span>
                </div>
                <div id="plan-modal-body" class="plan-modal-body"></div>
            </div>`;
        document.body.appendChild(modal);
    }
    document.getElementById('plan-modal-body').innerHTML = html;
    modal.style.display = 'flex';
}

function closePlanModal() {
    const modal = document.getElementById('plan-modal');
    if (modal) modal.style.display = 'none';
}

function shortModel(model) {
    if (!model) return '?';
    // Strip provider prefix (e.g. "anthropic/claude-sonnet-4-6" -> "claude-sonnet-4-6")
    const parts = model.split('/');
    return parts[parts.length - 1];
}

function renderConfig(config, scientistName) {
    if (!config) return '';
    const configId = storeConfig({ ...config, _name: scientistName });
    let html = '<div class="config-section mt-2 pt-2 border-t border-gray-800">';

    // Models row
    const gateway = config.gateway_model ? shortModel(config.gateway_model) : null;
    const research = config.research_model ? shortModel(config.research_model) : null;
    const paper = config.paper_model ? shortModel(config.paper_model) : null;

    if (gateway) html += `<div class="text-xs text-gray-500 flex items-center gap-1 mt-0.5"><span class="text-gray-600">Gateway:</span> <span class="config-badge">${gateway}</span></div>`;
    if (research) html += `<div class="text-xs text-gray-500 flex items-center gap-1 mt-0.5"><span class="text-gray-600">Research:</span> <span class="config-badge">${research}</span></div>`;
    if (paper && paper !== research) html += `<div class="text-xs text-gray-500 flex items-center gap-1 mt-0.5"><span class="text-gray-600">Paper:</span> <span class="config-badge">${paper}</span></div>`;

    // Params row: max_iterations, timeout, vlm, temperature
    const badges = [];
    if (config.max_iterations) badges.push(`${config.max_iterations} iters`);
    if (config.analysis_timeout) badges.push(`timeout ${config.analysis_timeout}s`);
    if (config.research_temperature != null) badges.push(`t=${config.research_temperature}`);
    if (config.analysis_vlm_review) badges.push('VLM');
    if (config.channels && config.channels.length) badges.push(config.channels.join(', '));
    if (badges.length) html += `<div class="text-xs text-gray-600 mt-1 flex flex-wrap gap-1">${badges.map(b => `<span class="param-badge">${b}</span>`).join('')}</div>`;

    html += `<div class="mt-1"><span class="expand-btn text-xs text-gray-600 hover:text-gray-400" onclick="openConfigModal('${configId}')">Full Config &#9654;</span></div>`;
    html += '</div>';
    return html;
}

function openConfigModal(configId) {
    const config = _configStore[configId];
    if (!config) return;

    let modal = document.getElementById('config-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'config-modal';
        modal.innerHTML = `
            <div class="plan-modal-backdrop" onclick="closeConfigModal()"></div>
            <div class="plan-modal-content" style="max-width:700px">
                <div class="plan-modal-header">
                    <span id="config-modal-title">Configuration</span>
                    <span class="plan-modal-close" onclick="closeConfigModal()">&times;</span>
                </div>
                <div id="config-modal-body" class="plan-modal-body"></div>
            </div>`;
        document.body.appendChild(modal);
    }

    document.getElementById('config-modal-title').textContent = `${config._name} — Configuration`;

    const params = config.params || {};
    let html = '';

    // --- Gateway section ---
    html += `<div class="mb-4">`;
    html += `<h3 class="text-sm font-semibold text-gray-300 mb-2 border-b border-gray-700 pb-1">Gateway (OpenClaw)</h3>`;
    html += `<table class="w-full text-xs"><tbody>`;
    html += configRow('Model', config.gateway_model);
    html += configRow('Timeout', config.timeout_seconds ? `${config.timeout_seconds}s` : null);
    html += configRow('Channels', config.channels ? config.channels.join(', ') : null);
    html += configRow('Plugins', config.plugins ? config.plugins.join(', ') : null);
    html += configRow('MCP Servers', config.mcp_servers ? config.mcp_servers.join(', ') : null);
    html += `</tbody></table></div>`;

    // --- Pipeline section ---
    html += `<div class="mb-4">`;
    html += `<h3 class="text-sm font-semibold text-gray-300 mb-2 border-b border-gray-700 pb-1">Pipeline</h3>`;
    html += `<table class="w-full text-xs"><tbody>`;
    html += configRow('Max Iterations', params.max_iterations);
    html += `</tbody></table></div>`;

    // --- Per-module agent tables ---
    const moduleOrder = ['EDA module', 'Idea module', 'Literature module', 'Methods module', 'Analysis module', 'Evaluator module', 'Paper module', 'Classifier module', 'Reviewer module'];
    for (const modName of moduleOrder) {
        const mod = params[modName];
        if (!mod) continue;

        html += `<div class="mb-4">`;
        html += `<h3 class="text-sm font-semibold text-gray-300 mb-2 border-b border-gray-700 pb-1">${modName.replace(' module', '')}</h3>`;

        // Module-level settings
        const moduleSettings = [];
        if (mod.max_n_steps != null) moduleSettings.push(['Max Steps', mod.max_n_steps]);
        if (mod.max_n_attempts != null) moduleSettings.push(['Max Attempts', mod.max_n_attempts]);
        if (mod.code_execution_timeout != null) moduleSettings.push(['Code Timeout', `${mod.code_execution_timeout}s`]);
        if (mod.enable_vlm_review != null) moduleSettings.push(['VLM Review', mod.enable_vlm_review ? 'Yes' : 'No']);

        if (moduleSettings.length) {
            html += `<table class="w-full text-xs mb-2"><tbody>`;
            for (const [k, v] of moduleSettings) html += configRow(k, v);
            html += `</tbody></table>`;
        }

        // Agent table
        const agents = Object.entries(mod).filter(([k, v]) => typeof v === 'object' && v && v.model);
        if (agents.length) {
            html += `<table class="w-full text-xs"><thead><tr class="text-gray-500 border-b border-gray-800"><th class="text-left pb-1 font-normal">Agent</th><th class="text-left pb-1 font-normal">Model</th><th class="text-right pb-1 font-normal">Temp</th></tr></thead><tbody>`;
            for (const [agent, agentCfg] of agents) {
                html += `<tr class="border-b border-gray-800/50"><td class="py-1 text-gray-400">${agent}</td><td class="py-1"><span class="config-badge">${shortModel(agentCfg.model)}</span></td><td class="py-1 text-right text-gray-500">${agentCfg.temperature ?? ''}</td></tr>`;
            }
            html += `</tbody></table>`;
        }
        html += `</div>`;
    }

    document.getElementById('config-modal-body').innerHTML = html;
    modal.style.display = 'flex';
}

function configRow(label, value) {
    if (value == null) return '';
    return `<tr class="border-b border-gray-800/50"><td class="py-1 text-gray-500 w-32">${label}</td><td class="py-1 text-gray-300">${value}</td></tr>`;
}

function closeConfigModal() {
    const modal = document.getElementById('config-modal');
    if (modal) modal.style.display = 'none';
}

function renderUsageBar(used, limit, label, unit) {
    const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
    let color = '#22c55e';
    if (pct > 80) color = '#ef4444';
    else if (pct > 60) color = '#f59e0b';
    return `<div class="flex items-center gap-2 text-xs text-gray-500">
        <span class="w-8">${label}</span>
        <div class="usage-bar flex-1"><div class="usage-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="w-20 text-right">${used}${unit} / ${limit}${unit}</span>
    </div>`;
}

function renderNav(activePage) {
    const pages = [
        { id: 'fleet', label: 'Fleet', href: 'index.html' },
        { id: 'papers', label: 'Papers', href: 'papers.html' },
        { id: 'activity', label: 'Activity', href: 'activity.html' },
    ];
    const external = [
        { label: 'Parallel ArXiv', href: 'https://papers.parallelscience.org' },
        { label: 'Portal', href: 'https://parallelscience.org' },
    ];
    const nav = document.getElementById('nav');
    if (!nav) return;
    const internal = pages.map(p => {
        const active = p.id === activePage;
        return `<a href="${p.href}" class="px-3 py-1 text-sm rounded ${active ? 'bg-white/10 text-white' : 'text-gray-500 hover:text-gray-300'}">${p.label}</a>`;
    }).join('');
    const ext = external.map(p =>
        `<a href="${p.href}" target="_blank" rel="noopener" class="px-3 py-1 text-sm text-gray-600 hover:text-gray-300">${p.label}</a>`
    ).join('');
    nav.innerHTML = internal + `<span class="flex-1"></span>` + ext;
}

let _fleetStartedAt = null;
let _uptimeInterval = null;

function renderUpdateTime(timestamp) {
    const el = document.getElementById('update-time');
    if (!el || !timestamp) return;
    const ts = new Date(timestamp);
    el.textContent = 'Updated: ' + ts.toLocaleTimeString(undefined, { timeZoneName: 'short' });
}

function updateMissionCost(scientists) {
    const el = document.getElementById('mission-cost');
    if (!el) return;
    const total = (scientists || []).reduce((sum, s) =>
        sum + (s.projects || []).reduce((ps, p) => ps + ((p.cost && p.cost.total_dollars) || 0), 0), 0);
    if (total > 0) {
        el.textContent = 'Mission Cost: ' + formatCost(total);
        el.className = 'mt-1 cost-badge';
    }
}

function updateFleetUptime(scientists) {
    // Find the earliest container started_at (longest running = fleet uptime)
    let earliest = null;
    for (const sci of (scientists || [])) {
        const c = sci.container;
        if (!c || !c.running || !c.started_at) continue;
        const t = new Date(c.started_at).getTime();
        if (!isNaN(t) && (earliest === null || t < earliest)) earliest = t;
    }
    if (earliest) {
        _fleetStartedAt = earliest;
        if (!_uptimeInterval) {
            _uptimeInterval = setInterval(tickUptime, 1000);
            tickUptime();
        }
    }
}

function tickUptime() {
    const el = document.getElementById('uptime');
    if (!el || !_fleetStartedAt) return;
    const secs = Math.floor((Date.now() - _fleetStartedAt) / 1000);
    const d = Math.floor(secs / 86400);
    const h = Math.floor((secs % 86400) / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const parts = [];
    if (d > 0) parts.push(`${d}d`);
    if (d > 0 || h > 0) parts.push(`${String(h).padStart(d > 0 ? 2 : 1, '0')}h`);
    parts.push(`${String(m).padStart(2, '0')}m`);
    parts.push(`${String(s).padStart(2, '0')}s`);
    el.textContent = 'Uptime: ' + parts.join(' ');
}

async function fetchStatus() {
    const resp = await fetch('status.json?' + Date.now());
    if (!resp.ok) throw new Error('Failed to load');
    return resp.json();
}
