// Shared utilities and components for the dashboard

const STAGES = ['eda', 'idea', 'literature', 'methods', 'results', 'paper'];
const STAGE_LABELS = { eda: 'EDA', idea: 'Idea', literature: 'Lit', methods: 'Methods', results: 'Results', paper: 'Paper' };

let expandedProjects = new Set();

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

function renderPipelineBar(stagesCompleted, planExecution, isBusy, scientist, project) {
    let activeStage = null;
    if (isBusy) {
        for (const stage of STAGES) {
            if (!stagesCompleted.includes(stage)) {
                activeStage = stage;
                break;
            }
        }
    }

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
        if (stagesCompleted.includes(stage)) cls = 'stage-done';
        else if (stage === activeStage) cls = 'stage-active';
        const clickable = stagesCompleted.includes(stage) && scientist && project;
        if (clickable) {
            html += `<div class="stage-pill ${cls} stage-clickable" onclick="openStageModal('${scientist}','${project}','${stage}')">${STAGE_LABELS[stage]}</div>`;
        } else {
            html += `<div class="stage-pill ${cls}">${STAGE_LABELS[stage]}</div>`;
        }
    }
    html += '</div>';
    html += experimentDetail;
    return html;
}

// --- Stage content modal ---

async function openStageModal(scientist, project, stage) {
    let modal = document.getElementById('stage-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'stage-modal';
        modal.innerHTML = `
            <div class="stage-modal-backdrop" onclick="closeStageModal()"></div>
            <div class="stage-modal-content">
                <div class="stage-modal-header">
                    <span id="stage-modal-title"></span>
                    <span class="stage-modal-close" onclick="closeStageModal()">&times;</span>
                </div>
                <div id="stage-modal-body" class="stage-modal-body">Loading...</div>
            </div>`;
        document.body.appendChild(modal);
    }

    const title = document.getElementById('stage-modal-title');
    const body = document.getElementById('stage-modal-body');
    title.textContent = STAGE_LABELS[stage] || stage;
    body.innerHTML = '<div class="text-gray-500">Loading...</div>';
    modal.style.display = 'flex';

    try {
        const resp = await fetch(`/api/stage?scientist=${encodeURIComponent(scientist)}&project=${encodeURIComponent(project)}&stage=${encodeURIComponent(stage)}`);
        if (!resp.ok) {
            body.innerHTML = '<div class="text-red-400">Content not available.</div>';
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
        body.innerHTML = '<div class="text-red-400">Failed to load content.</div>';
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

// Close modal on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeStageModal();
});

function renderPlanTable(planExecution, projectKey) {
    if (!planExecution || !planExecution.steps) return '';
    const steps = planExecution.steps;
    const planning = planExecution.planning;

    let totalCost = (planning.cost_dollars || 0);
    let totalTime = (planning.time_seconds || 0);
    steps.forEach(s => { totalCost += (s.cost_dollars || 0); totalTime += (s.time_seconds || 0); });

    const expanded = expandedProjects.has(projectKey);

    let html = `<div class="mt-2">`;
    html += `<div class="expand-btn text-xs text-gray-500 flex items-center gap-1" onclick="toggleProject('${projectKey}')">`;
    html += `<span>${expanded ? '&#9660;' : '&#9654;'}</span>`;
    html += `<span>Plan: ${steps.length} steps</span>`;
    html += `<span class="cost-badge ml-2">${formatCost(totalCost)}</span>`;
    html += `<span class="time-badge">${formatTime(totalTime)}</span>`;
    html += `</div>`;

    html += `<div id="plan-${projectKey}" class="${expanded ? 'fade-in' : 'hidden'} mt-2">`;
    html += `<table class="w-full text-xs"><thead><tr class="text-gray-500 text-left">`;
    html += `<th class="pb-1 w-8">#</th><th class="pb-1">Sub-task</th><th class="pb-1 w-16">Agent</th>`;
    html += `<th class="pb-1 w-12 text-right">Status</th><th class="pb-1 w-16 text-right">Time</th><th class="pb-1 w-16 text-right">Cost</th>`;
    html += `</tr></thead><tbody>`;

    html += `<tr class="step-row text-gray-400"><td></td><td>Planning</td><td></td>`;
    html += `<td class="text-right"><span class="text-green-500">&#10003;</span></td>`;
    html += `<td class="text-right">${formatTime(planning.time_seconds)}</td>`;
    html += `<td class="text-right">${formatCost(planning.cost_dollars)}</td></tr>`;

    for (const step of steps) {
        let attemptInfo = '';
        if (step.attempt != null && step.max_attempts != null) {
            const color = step.attempt > 3 ? 'text-amber-400' : 'text-gray-500';
            attemptInfo = ` <span class="${color}">(${step.attempt}/${step.max_attempts})</span>`;
        }
        html += `<tr class="step-row">`;
        html += `<td class="text-gray-500 py-1">${step.number}</td>`;
        html += `<td class="py-1 text-gray-300 truncate max-w-[200px]" title="${step.name}">${step.name}</td>`;
        html += `<td class="py-1 text-gray-500">${step.agent}</td>`;
        html += `<td class="py-1 text-right">${stepStatusIcon(step.status)}${attemptInfo}</td>`;
        html += `<td class="py-1 text-right text-gray-400">${formatTime(step.time_seconds)}</td>`;
        html += `<td class="py-1 text-right text-gray-400">${formatCost(step.cost_dollars)}</td>`;
        html += `</tr>`;
    }

    html += `<tr class="text-gray-300 font-medium"><td></td><td>Total</td><td></td><td></td>`;
    html += `<td class="text-right">${formatTime(totalTime)}</td>`;
    html += `<td class="text-right">${formatCost(totalCost)}</td></tr>`;

    html += `</tbody></table></div></div>`;
    return html;
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
    const nav = document.getElementById('nav');
    if (!nav) return;
    nav.innerHTML = pages.map(p => {
        const active = p.id === activePage;
        return `<a href="${p.href}" class="px-3 py-1 text-sm rounded ${active ? 'bg-white/10 text-white' : 'text-gray-500 hover:text-gray-300'}">${p.label}</a>`;
    }).join('');
}

function renderUpdateTime(timestamp) {
    const el = document.getElementById('update-time');
    if (!el || !timestamp) return;
    const ts = new Date(timestamp);
    el.textContent = 'Updated: ' + ts.toLocaleTimeString(undefined, { timeZoneName: 'short' });
}

async function fetchStatus() {
    const resp = await fetch('status.json?' + Date.now());
    if (!resp.ok) throw new Error('Failed to load');
    return resp.json();
}
