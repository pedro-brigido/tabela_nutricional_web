/**
 * Terracota Compliance — Nutritional Table Wizard
 * Two-phase flow: Preview (free recalculations) → Generate (consumes quota)
 */

const state = {
    currentStep: 0,
    product: {
        name: '',
        portionSize: '',
        portionDesc: '',
        allergens: '',
        allergenKeys: [],
        customAllergens: '',
        gluten: 'Não contém glúten',
        glutenStatus: 'gluten_free',
        foodForm: 'solid',
        portionUnit: 'g',
        groupCode: ''
    },
    ingredients: [],
    calculatedData: null,
    quotaInfo: null,        // { canCreate, tablesCreated, tablesLimit, planName, planSlug }
    isFinalized: false,     // true after "Gerar Tabela" succeeds
    savedTableId: null,
    isSavingTable: false,
    saveTableError: '',
    currentIdempotencyKey: null,  // generated once per calculation session
    lastTable: null,        // most recent table (shown when quota exhausted)
    toastTimeout: null,
    allergenRegistry: null, // cached from /api/allergens
    portionGroups: null     // cached from /api/portion-references
};

// ---- Helpers ----------------------------------------------------------------

function generateIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return `tbl_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function getCsrfToken() {
    const el = document.querySelector('meta[name="csrf-token"]');
    return el?.getAttribute('content') || '';
}

function withCsrfHeaders(headers = {}) {
    const token = getCsrfToken();
    if (!token) return headers;
    return { ...headers, 'X-CSRFToken': token };
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function printTable() {
    const printArea = document.getElementById('nutritional-table-print-area');
    if (!printArea) { showToast('Nenhuma tabela para imprimir.', 'warning'); return; }
    const html = printArea.outerHTML;
    const win = window.open('', '_blank', 'width=800,height=600');
    if (!win) { showToast('Popup bloqueado. Permita popups para imprimir.', 'warning'); return; }
    win.document.write(`<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Tabela Nutricional</title>
<style>
  @page { margin: 1cm; }
  body { margin: 0; padding: 1cm; font-family: 'Helvetica Neue', Arial, sans-serif; background: #fff; color: #000; }
  #nutritional-table-print-area { max-width: 100% !important; border: none !important; border-radius: 0 !important; padding: 0 !important; }
</style>
</head>
<body>${html}</body>
</html>`);
    win.document.close();
    win.focus();
    setTimeout(() => {
        win.print();
        win.onafterprint = () => win.close();
    }, 250);
}

function showToast(message, type = 'success', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed top-24 right-6 z-[9999] flex flex-col gap-3 pointer-events-none';
        document.body.appendChild(container);
    }
    const colors = {
        success: 'bg-emerald-500/90 border-emerald-400',
        error: 'bg-red-500/90 border-red-400',
        warning: 'bg-yellow-500/90 border-yellow-400 text-black',
        info: 'bg-terracota-cyan/90 border-terracota-cyan text-black'
    };
    const toast = document.createElement('div');
    toast.className = `pointer-events-auto px-5 py-3 rounded-xl border text-sm font-medium shadow-lg backdrop-blur-sm transition-all duration-300 opacity-0 translate-x-4 ${colors[type] || colors.info}`;
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => { toast.classList.remove('opacity-0', 'translate-x-4'); });
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-x-4');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function quotaBadgeHtml() {
    const q = state.quotaInfo;
    if (!q) return '';
    const limitText = q.tablesLimit === null ? '∞' : q.tablesLimit;
    const remaining = q.tablesLimit === null ? '∞' : Math.max(0, q.tablesLimit - q.tablesCreated);
    return `<div class="text-center mt-2 text-xs text-terracota-textMuted">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10">
            <span class="w-2 h-2 rounded-full ${q.canCreate ? 'bg-emerald-400' : 'bg-red-400'}"></span>
            ${q.tablesCreated}/${limitText} tabelas este mês · <span class="text-terracota-cyan">${q.planName}</span>
        </span>
    </div>`;
}

// ---- API calls --------------------------------------------------------------

async function fetchQuota() {
    try {
        const res = await fetch('/api/quota', { headers: withCsrfHeaders() });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        if (!res.ok) return null;
        state.quotaInfo = await res.json();
        return state.quotaInfo;
    } catch (e) { console.error('fetchQuota error', e); return null; }
}

async function fetchLatestTable() {
    try {
        const res = await fetch('/api/tables/latest', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.lastTable = data.table;
        return data.table;
    } catch (e) { console.error('fetchLatestTable error', e); return null; }
}

async function fetchAllergenRegistry() {
    if (state.allergenRegistry) return state.allergenRegistry;
    try {
        const res = await fetch('/api/allergens', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.allergenRegistry = data;
        return data;
    } catch (e) { console.error('fetchAllergenRegistry error', e); return null; }
}

async function fetchPortionGroups() {
    if (state.portionGroups) return state.portionGroups;
    try {
        const res = await fetch('/api/portion-references', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.portionGroups = data.groups;
        return data.groups;
    } catch (e) { console.error('fetchPortionGroups error', e); return null; }
}

async function saveCurrentTable() {
    if (!state.calculatedData) return { ok: false, error: 'Sem tabela para salvar.' };
    if (state.isSavingTable) return { ok: false, error: 'Salvamento em andamento.' };

    state.isSavingTable = true;
    state.saveTableError = '';

    // Reuse the same idempotency key for retries of the same calculation
    if (!state.currentIdempotencyKey) {
        state.currentIdempotencyKey = generateIdempotencyKey();
    }

    const payload = {
        title: state.product.name || 'Tabela sem título',
        product: state.product,
        ingredients: state.ingredients,
        calculatedData: state.calculatedData,
        idempotencyKey: state.currentIdempotencyKey
    };

    try {
        const res = await fetch('/api/tables', {
            method: 'POST',
            headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(payload)
        });

        if (res.status === 401) {
            window.location.href = '/login';
            return { ok: false, error: 'Sessão expirada.' };
        }

        const data = await res.json();
        if (!res.ok) {
            state.saveTableError = data.error || 'Não foi possível salvar a tabela.';
            return { ok: false, error: state.saveTableError, code: data.code };
        }

        state.savedTableId = data.id;
        state.saveTableError = '';
        return { ok: true, data };
    } catch (e) {
        console.error(e);
        state.saveTableError = 'Erro ao salvar. Verifique a conexão e tente novamente.';
        return { ok: false, error: state.saveTableError };
    } finally {
        state.isSavingTable = false;
    }
}

// ---- Initialization ---------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => { initApp(); });

async function initApp() {
    await Promise.all([fetchQuota(), fetchAllergenRegistry(), fetchPortionGroups()]);
    const duplicated = await preloadDuplicateIfAny();
    if (duplicated) {
        setupNavigation();
        return;
    }

    if (state.quotaInfo && !state.quotaInfo.canCreate) {
        await fetchLatestTable();
        renderQuotaExhausted();
    } else {
        renderWelcome();
    }
    setupNavigation();
}

async function preloadDuplicateIfAny() {
    const params = new URLSearchParams(window.location.search);
    const duplicateId = params.get('duplicate');
    if (!duplicateId) return false;
    try {
        const res = await fetch(`/api/tables/${duplicateId}`, { headers: withCsrfHeaders() });
        if (!res.ok) {
            showToast('Não foi possível carregar a tabela para duplicação.', 'warning');
            return false;
        }
        const data = await res.json();
        state.product = {
            name: data.product_data?.name || '',
            portionSize: data.product_data?.portionSize || data.product_data?.portion_size || '',
            portionDesc: data.product_data?.portionDesc || data.product_data?.portion_desc || '',
            allergens: data.product_data?.allergens || '',
            allergenKeys: Array.isArray(data.product_data?.allergenKeys) ? data.product_data.allergenKeys : [],
            customAllergens: data.product_data?.customAllergens || '',
            gluten: data.product_data?.gluten || data.product_data?.gluten_status || 'Não contém glúten',
            glutenStatus: data.product_data?.glutenStatus || (data.product_data?.gluten === 'Contém glúten' ? 'contains_gluten' : 'gluten_free'),
            foodForm: data.product_data?.foodForm || 'solid',
            portionUnit: data.product_data?.portionUnit || data.product_data?.portion_unit || 'g',
            groupCode: data.product_data?.groupCode || '',
        };
        state.ingredients = Array.isArray(data.ingredients_data) ? data.ingredients_data : [];
        state.calculatedData = null;
        state.isFinalized = false;
        state.currentIdempotencyKey = null;
        goToStep(1);
        showToast('Tabela carregada para duplicação.', 'info');
        return true;
    } catch (err) {
        console.error(err);
        return false;
    }
}

function setupNavigation() {
    document.getElementById('btn-back').addEventListener('click', () => {
        if (state.isFinalized) return; // no back from finalized
        if (state.currentStep > 1) {
            goToStep(state.currentStep - 1);
        }
    });

    document.getElementById('btn-next').addEventListener('click', () => {
        if (validateStep(state.currentStep)) {
            if (state.currentStep === 2) {
                calculateResult();
                return;
            }
            goToStep(state.currentStep + 1);
        }
    });
}

function goToStep(step) {
    state.currentStep = step;
    updateUI();
}

function updateUI() {
    const content = document.getElementById('wizard-content');
    const btnBack = document.getElementById('btn-back');
    const btnNext = document.getElementById('btn-next');
    const progress = document.getElementById('wizard-progress');

    const showBack = state.currentStep === 2;
    btnBack.style.display = showBack ? 'block' : 'none';
    btnBack.disabled = !showBack;

    btnNext.style.display = state.currentStep > 0 && state.currentStep < 3 ? 'block' : 'none';
    btnNext.disabled = false;

    if (state.currentStep > 0 && state.currentStep <= 3) {
        progress.innerHTML = renderProgressBar(state.currentStep);
        progress.style.display = 'block';
    } else {
        progress.style.display = 'none';
    }

    switch (state.currentStep) {
        case 1:
            renderStep1(content);
            btnNext.innerHTML = 'Próximo: Ingredientes <i class="ph ph-arrow-right ml-2"></i>';
            btnBack.innerHTML = '<i class="ph ph-arrow-left mr-2"></i> Voltar';
            break;
        case 2:
            renderStep2(content);
            btnNext.innerHTML = 'Calcular Tabela <i class="ph ph-arrow-right ml-2"></i>';
            btnBack.innerHTML = '<i class="ph ph-arrow-left mr-2"></i> Voltar: Produto';
            break;
        case 3:
            renderStep3(content);
            break;
        default:
            renderWelcome();
    }
}

function renderProgressBar(step) {
    const steps = ['Produto', 'Ingredientes', 'Tabela'];
    const items = steps.map((label, idx) => {
        const s = idx + 1;
        const active = s <= step;
        const current = s === step;
        const canClick = s < step || (s === 3 && state.calculatedData);
        const bgCircle = active ? 'bg-terracota-cyan text-terracota-deepDark shadow-[0_0_15px_rgba(0,196,204,0.4)]' : 'bg-terracota-deepDark border border-white/20 text-terracota-textLight';
        const ring = current ? 'ring-4 ring-terracota-cyan/20' : '';
        const textClass = active ? 'text-terracota-cyan' : 'text-terracota-textLight/50';
        const clickClass = canClick ? 'cursor-pointer hover:scale-110' : '';
        const clickAttr = canClick ? `onclick="goToStep(${s})"` : '';
        return `
            <div class="relative z-10 flex flex-col items-center ${clickClass}" ${clickAttr}>
                <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all duration-300 ${bgCircle} ${ring}">${s}</div>
                <span class="mt-3 text-xs font-medium uppercase tracking-wider ${textClass}">${label}</span>
            </div>
        `;
    }).join('');
    return `<div class="flex items-center justify-between relative">
        <div class="absolute w-full top-1/2 transform -translate-y-1/2 h-0.5 bg-white/10 -z-0"></div>
        ${items}
    </div>${quotaBadgeHtml()}`;
}

// ---- Quota Exhausted View ---------------------------------------------------

function renderQuotaExhausted() {
    const content = document.getElementById('wizard-content');
    const progress = document.getElementById('wizard-progress');
    const btnBack = document.getElementById('btn-back');
    const btnNext = document.getElementById('btn-next');

    progress.style.display = 'none';
    btnBack.style.display = 'none';
    btnNext.style.display = 'none';
    state.currentStep = 0;

    const q = state.quotaInfo;
    const limitText = q ? (q.tablesLimit === null ? '∞' : q.tablesLimit) : '?';
    const planName = q ? q.planName : 'seu plano';

    let tableHtml = '';
    if (state.lastTable && state.lastTable.result_data) {
        const tbl = state.lastTable;
        tableHtml = `
            <div class="mt-6 mb-2">
                <p class="text-sm text-terracota-textMuted mb-3">Sua última tabela: <span class="text-white font-medium">${escapeHtml(tbl.title)}</span></p>
                ${buildNutritionTableHtml(tbl.result_data, tbl.product_data || {})}
            </div>
            <div class="flex justify-center gap-4 mt-6 no-print">
                <button onclick="printTable()" class="px-8 py-3 bg-terracota-cyan text-terracota-deepDark font-bold rounded-lg hover:bg-white shadow-[0_0_20px_rgba(0,196,204,0.3)] transition-all flex items-center">
                    <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                    Imprimir Tabela
                </button>
            </div>
        `;
    } else {
        tableHtml = '<p class="text-terracota-textMuted text-sm mt-4">Nenhuma tabela gerada ainda neste período.</p>';
    }

    content.innerHTML = `
        <div class="text-center py-8">
            <div class="mb-6 inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-red-500/20 to-orange-500/20 border border-red-500/30 text-red-400">
                <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m0 0v2m0-2h2m-2 0H9m3-10V7a4 4 0 00-8 0v4h8z"></path></svg>
            </div>
            <h2 class="text-2xl font-bold text-white mb-3 font-heading">Limite de Tabelas Atingido</h2>
            <p class="text-terracota-textMuted mb-2">
                Você já utilizou <span class="text-white font-bold">${q ? q.tablesCreated : '?'}/${limitText}</span> tabelas disponíveis no plano <span class="text-terracota-cyan font-semibold">${escapeHtml(planName)}</span> este mês.
            </p>
            <p class="text-terracota-textMuted text-sm mb-6">
                Faça upgrade para gerar mais tabelas ou aguarde o próximo período.
            </p>
            <a href="/account/upgrade" class="inline-block px-10 py-4 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white text-lg font-bold rounded-xl hover:scale-105 shadow-[0_0_30px_rgba(123,44,191,0.3)] transition-all">
                Fazer Upgrade
            </a>
            <div class="mt-3">
                <a href="/account/" class="text-sm text-terracota-textMuted hover:text-white transition-colors underline">Minha Conta →</a>
            </div>
            ${tableHtml}
        </div>
    `;
}

// ---- Welcome ----------------------------------------------------------------

function renderWelcome() {
    const content = document.getElementById('wizard-content');
    document.getElementById('wizard-progress').style.display = 'none';
    document.getElementById('btn-back').style.display = 'none';
    document.getElementById('btn-next').style.display = 'none';

    content.innerHTML = `
        <div class="text-center py-10">
            <div class="mb-8 inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-terracota-purple to-terracota-cyan shadow-lg shadow-terracota-cyan/20 text-white transform rotate-3 hover:rotate-6 transition-transform">
                <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
            </div>
            <h2 class="text-4xl font-bold text-white mb-6 font-heading">Calculadora Nutricional</h2>
            <p class="text-xl text-terracota-textLight mb-10 max-w-lg mx-auto font-light leading-relaxed">
                Gere tabelas nutricionais em conformidade com a <span class="text-terracota-cyan font-medium">RDC 429/2020</span> com a inteligência e design da Terracota.
            </p>
            ${quotaBadgeHtml()}
            <button onclick="goToStep(1)" class="mt-6 px-10 py-4 bg-terracota-cyan text-terracota-deepDark text-lg font-bold rounded-xl hover:bg-white hover:scale-105 shadow-[0_0_30px_rgba(0,196,204,0.3)] transition-all">
                Iniciar Novo Produto
            </button>
        </div>
    `;
}

// ---- Step 1: Product Info ---------------------------------------------------

function renderStep1(container) {
    const inputClass = "w-full px-4 py-3 bg-black/20 border border-white/10 rounded-lg text-white placeholder-white/30 focus:ring-2 focus:ring-terracota-cyan focus:border-transparent outline-none transition-all";
    const labelClass = "block text-sm font-medium text-terracota-textLight mb-2 uppercase tracking-wide text-[10px]";
    const isLiquid = state.product.foodForm === 'liquid';
    const portionUnitLabel = isLiquid ? 'ml' : 'g';

    // Build allergen checkboxes HTML
    let allergenCheckboxesHtml = '';
    if (state.allergenRegistry && state.allergenRegistry.allergens) {
        const groups = {};
        for (const a of state.allergenRegistry.allergens) {
            if (!groups[a.group]) groups[a.group] = [];
            groups[a.group].push(a);
        }
        for (const [group, items] of Object.entries(groups)) {
            const checkboxes = items.map(a => {
                const checked = state.product.allergenKeys.includes(a.key) ? 'checked' : '';
                return `<label class="flex items-center gap-2 text-sm text-terracota-textLight cursor-pointer hover:text-white transition-colors">
                    <input type="checkbox" value="${a.key}" ${checked} class="allergen-checkbox rounded border-white/20 bg-black/20 text-terracota-cyan focus:ring-terracota-cyan">
                    <span class="capitalize">${escapeHtml(a.label)}</span>
                </label>`;
            }).join('');
            allergenCheckboxesHtml += `
                <div class="mb-3">
                    <p class="text-[10px] font-bold text-terracota-cyan/70 uppercase tracking-wider mb-1">${escapeHtml(group)}</p>
                    <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">${checkboxes}</div>
                </div>`;
        }
    } else {
        allergenCheckboxesHtml = `<textarea id="input-allergens-fallback" rows="2" class="${inputClass}" placeholder="Ex: CONTÉM OVO E TRIGO">${escapeHtml(state.product.allergens)}</textarea>`;
    }

    // Build gluten options from registry
    let glutenOptionsHtml = '';
    if (state.allergenRegistry && state.allergenRegistry.glutenOptions) {
        glutenOptionsHtml = state.allergenRegistry.glutenOptions.map(o =>
            `<option value="${o.key}" class="bg-terracota-deepDark" ${state.product.glutenStatus === o.key ? 'selected' : ''}>${escapeHtml(o.label)}</option>`
        ).join('');
    } else {
        glutenOptionsHtml = `
            <option value="gluten_free" class="bg-terracota-deepDark" ${state.product.glutenStatus === 'gluten_free' ? 'selected' : ''}>NÃO CONTÉM GLÚTEN</option>
            <option value="contains_gluten" class="bg-terracota-deepDark" ${state.product.glutenStatus === 'contains_gluten' ? 'selected' : ''}>CONTÉM GLÚTEN</option>`;
    }

    // Build portion reference dropdown
    let portionGroupHtml = '';
    if (state.portionGroups && state.portionGroups.length > 0) {
        const options = state.portionGroups.map(g =>
            `<option value="${g.code}" class="bg-terracota-deepDark" ${state.product.groupCode === g.code ? 'selected' : ''}>${escapeHtml(g.name)} (${g.portion_g}${portionUnitLabel} — ${escapeHtml(g.household_measure)})</option>`
        ).join('');
        portionGroupHtml = `
            <div>
                <label class="${labelClass}">Grupo de Alimento (Anexo V)</label>
                <select id="input-group-code" class="${inputClass} appearance-none cursor-pointer">
                    <option value="" class="bg-terracota-deepDark">— Selecione (opcional) —</option>
                    ${options}
                </select>
                <p class="text-[10px] text-terracota-textMuted mt-1">Porção de referência regulatória para validação</p>
            </div>`;
    }

    container.innerHTML = `
        <div class="space-y-8 max-w-lg mx-auto">
            <h3 class="text-2xl font-bold text-white font-heading text-center mb-8">Informações do Produto</h3>
            <div>
                <label class="${labelClass}">Nome do Produto</label>
                <input type="text" id="input-name" value="${escapeHtml(state.product.name)}" class="${inputClass}" placeholder="Ex: Bolo de Chocolate">
            </div>
            <div>
                <label class="${labelClass}">Tipo de Produto</label>
                <select id="input-food-form" class="${inputClass} appearance-none cursor-pointer">
                    <option value="solid" class="bg-terracota-deepDark" ${state.product.foodForm === 'solid' ? 'selected' : ''}>Sólido</option>
                    <option value="liquid" class="bg-terracota-deepDark" ${state.product.foodForm === 'liquid' ? 'selected' : ''}>Líquido</option>
                </select>
            </div>
            ${portionGroupHtml}
            <div class="grid grid-cols-2 gap-6">
                <div>
                    <label class="${labelClass}">Porção (${portionUnitLabel})</label>
                    <input type="number" id="input-portion" value="${escapeHtml(state.product.portionSize)}" class="${inputClass}" placeholder="Ex: 60" min="0.1" step="0.1">
                </div>
                <div>
                    <label class="${labelClass}">Medida Caseira</label>
                    <input type="text" id="input-desc" value="${escapeHtml(state.product.portionDesc)}" class="${inputClass}" placeholder="Ex: 1 fatia">
                </div>
            </div>
            <div>
                <label class="${labelClass}">Declaração de Alérgenos (RDC 26/2015)</label>
                <div class="bg-black/20 border border-white/10 rounded-lg p-4">
                    ${allergenCheckboxesHtml}
                    <div class="mt-3 pt-3 border-t border-white/10">
                        <label class="${labelClass}">Outros alérgenos</label>
                        <input type="text" id="input-custom-allergens" value="${escapeHtml(state.product.customAllergens)}" class="${inputClass}" placeholder="Ex: kiwi, gergelim">
                    </div>
                </div>
            </div>
            <div>
                <label class="${labelClass}">Glúten</label>
                <select id="input-gluten-status" class="${inputClass} appearance-none cursor-pointer">
                    ${glutenOptionsHtml}
                </select>
            </div>
        </div>
    `;

    // Event listeners
    document.getElementById('input-name').addEventListener('input', (e) => state.product.name = e.target.value);
    document.getElementById('input-portion').addEventListener('input', (e) => state.product.portionSize = e.target.value);
    document.getElementById('input-desc').addEventListener('input', (e) => state.product.portionDesc = e.target.value);
    document.getElementById('input-custom-allergens')?.addEventListener('input', (e) => state.product.customAllergens = e.target.value);

    // Allergen checkboxes
    document.querySelectorAll('.allergen-checkbox').forEach(cb => {
        cb.addEventListener('change', () => {
            const checked = [...document.querySelectorAll('.allergen-checkbox:checked')].map(c => c.value);
            state.product.allergenKeys = checked;
            _syncAllergenText();
        });
    });

    // Fallback allergens textarea
    const fallbackTextarea = document.getElementById('input-allergens-fallback');
    if (fallbackTextarea) {
        fallbackTextarea.addEventListener('input', (e) => state.product.allergens = e.target.value);
    }

    // Gluten
    const glutenSelect = document.getElementById('input-gluten-status');
    if (glutenSelect) {
        glutenSelect.addEventListener('change', (e) => {
            state.product.glutenStatus = e.target.value;
            const label = state.allergenRegistry?.glutenOptions?.find(o => o.key === e.target.value)?.label;
            state.product.gluten = label || (e.target.value === 'contains_gluten' ? 'Contém glúten' : 'Não contém glúten');
        });
    }

    // Group code
    const groupCodeSelect = document.getElementById('input-group-code');
    if (groupCodeSelect) {
        groupCodeSelect.addEventListener('change', (e) => {
            state.product.groupCode = e.target.value;
            // Auto-fill portion if group selected and portion empty
            if (e.target.value && !state.product.portionSize && state.portionGroups) {
                const group = state.portionGroups.find(g => g.code === e.target.value);
                if (group) {
                    state.product.portionSize = group.portion_g;
                    state.product.portionDesc = group.household_measure;
                    document.getElementById('input-portion').value = group.portion_g;
                    document.getElementById('input-desc').value = group.household_measure;
                }
            }
        });
    }

    // Food form toggle
    document.getElementById('input-food-form').addEventListener('change', (e) => {
        state.product.foodForm = e.target.value;
        state.product.portionUnit = state.product.foodForm === 'liquid' ? 'ml' : 'g';
        renderStep1(container);
    });
}

/** Sync allergenKeys → legacy allergens text for template rendering */
function _syncAllergenText() {
    if (!state.allergenRegistry) return;
    const labels = state.product.allergenKeys
        .map(k => state.allergenRegistry.allergens.find(a => a.key === k)?.label)
        .filter(Boolean)
        .map(l => l.toUpperCase());
    if (state.product.customAllergens?.trim()) {
        labels.push(state.product.customAllergens.trim().toUpperCase());
    }
    state.product.allergens = labels.length > 0
        ? `ALÉRGICOS: CONTÉM ${labels.join(', ')}.`
        : '';
}

// ---- TACO Autocomplete ------------------------------------------------------

let _tacoDebounceTimer = null;
let _activeTacoDropdown = null;
let _tacoHighlightIndex = -1;
let _tacoSearching = false;

async function tacoSearch(query) {
    if (!query || query.length < 2) return [];
    try {
        const res = await fetch(`/api/taco/search?q=${encodeURIComponent(query)}&limit=8`, { headers: withCsrfHeaders() });
        if (!res.ok) return [];
        const data = await res.json();
        return data.results || [];
    } catch { return []; }
}

function closeTacoDropdown() {
    if (_activeTacoDropdown) {
        _activeTacoDropdown.remove();
        _activeTacoDropdown = null;
    }
    _tacoHighlightIndex = -1;
    _removeTacoLoader();
}

function _showTacoLoader(inputEl) {
    _removeTacoLoader();
    const wrapper = inputEl.closest('.relative');
    if (!wrapper) return;
    const loader = document.createElement('div');
    loader.id = 'taco-loader';
    loader.className = 'absolute right-2 top-1/2 -translate-y-1/2 z-40 pointer-events-none';
    loader.innerHTML = '<div class="w-4 h-4 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin"></div>';
    wrapper.appendChild(loader);
}

function _removeTacoLoader() {
    document.getElementById('taco-loader')?.remove();
}

function _highlightTacoItem(direction) {
    if (!_activeTacoDropdown) return;
    const items = _activeTacoDropdown.querySelectorAll('[data-taco-item]');
    if (!items.length) return;
    items.forEach(it => it.classList.remove('bg-terracota-cyan/20'));
    if (direction === 'down') {
        _tacoHighlightIndex = (_tacoHighlightIndex + 1) % items.length;
    } else {
        _tacoHighlightIndex = (_tacoHighlightIndex - 1 + items.length) % items.length;
    }
    items[_tacoHighlightIndex].classList.add('bg-terracota-cyan/20');
    items[_tacoHighlightIndex].scrollIntoView({ block: 'nearest' });
}

function _selectHighlightedTacoItem() {
    if (!_activeTacoDropdown || _tacoHighlightIndex < 0) return false;
    const items = _activeTacoDropdown.querySelectorAll('[data-taco-item]');
    if (items[_tacoHighlightIndex]) {
        items[_tacoHighlightIndex].dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
        return true;
    }
    return false;
}

function showTacoDropdown(inputEl, results, index) {
    closeTacoDropdown();

    const dd = document.createElement('div');
    dd.className = 'absolute z-50 left-0 right-0 top-full mt-1 bg-terracota-surface border border-white/20 rounded-lg shadow-xl max-h-56 overflow-y-auto';
    dd.id = 'taco-dropdown';
    _activeTacoDropdown = dd;

    if (!results.length) {
        dd.innerHTML = '<div class="px-3 py-3 text-sm text-terracota-textMuted text-center">Nenhum resultado encontrado</div>';
        const wrapper = inputEl.closest('.relative');
        if (wrapper) wrapper.appendChild(dd);
        return;
    }

    for (const food of results) {
        const item = document.createElement('button');
        item.type = 'button';
        item.setAttribute('data-taco-item', '');
        item.className = 'w-full text-left px-3 py-2 hover:bg-terracota-cyan/20 transition-colors flex flex-col border-b border-white/5 last:border-0';
        item.innerHTML = `<span class="text-sm text-white truncate">${escapeHtml(food.name)}</span><span class="text-[10px] text-terracota-textMuted">${escapeHtml(food.category)} · ${food.per100g.energyKcal ?? '?'} kcal</span>`;
        item.addEventListener('mousedown', (e) => {
            e.preventDefault();
            applyTacoFood(index, food);
            closeTacoDropdown();
        });
        dd.appendChild(item);
    }

    const wrapper = inputEl.closest('.relative');
    if (wrapper) wrapper.appendChild(dd);
}

function applyTacoFood(index, food) {
    const ing = state.ingredients[index];
    ing.name = food.name;
    ing._tacoId = food.id;
    const n = food.per100g;
    ing.nutritionalInfo = {
        energyKcal: n.energyKcal ?? '',
        carbs: n.carbs ?? '',
        proteins: n.proteins ?? '',
        totalFat: n.totalFat ?? '',
        saturatedFat: n.saturatedFat ?? '',
        transFat: n.transFat ?? '',
        fiber: n.fiber ?? '',
        sodium: n.sodium ?? '',
        totalSugars: n.totalSugars ?? '',
        addedSugars: n.addedSugars ?? '',
    };
    renderStep2(document.getElementById('wizard-content'));

    requestAnimationFrame(() => {
        const row = document.querySelector(`[data-ing-index="${index}"]`);
        if (row) {
            row.classList.add('border-emerald-400/50');
            row.style.transition = 'border-color 0.3s ease';
            setTimeout(() => row.classList.remove('border-emerald-400/50'), 1200);
        }
    });
    showToast(`"${food.name}" preenchido via TACO`, 'success', 2500);
}

// ---- Auto Kcal Estimation ---------------------------------------------------

function estimateKcal(nutri) {
    const carbs = parseFloat(nutri.carbs) || 0;
    const proteins = parseFloat(nutri.proteins) || 0;
    const totalFat = parseFloat(nutri.totalFat) || 0;
    const fiber = parseFloat(nutri.fiber) || 0;
    if (carbs === 0 && proteins === 0 && totalFat === 0) return null;
    return Math.round(carbs * 4 + proteins * 4 + totalFat * 9 + fiber * 2);
}

// ---- Inline Consistency Validation ------------------------------------------

function getIngredientWarnings(nutri) {
    const warnings = [];
    const sat = parseFloat(nutri.saturatedFat);
    const trans = parseFloat(nutri.transFat);
    const totalFat = parseFloat(nutri.totalFat);
    if (!isNaN(sat) && !isNaN(trans) && !isNaN(totalFat) && totalFat > 0) {
        if (sat + trans > totalFat) {
            warnings.push({ fields: ['saturatedFat', 'transFat', 'totalFat'], msg: 'Sat + Trans excede Gorduras Totais' });
        }
    }
    const addedSugars = parseFloat(nutri.addedSugars);
    const totalSugars = parseFloat(nutri.totalSugars);
    const carbs = parseFloat(nutri.carbs);
    if (!isNaN(addedSugars) && !isNaN(totalSugars) && addedSugars > totalSugars) {
        warnings.push({ fields: ['addedSugars', 'totalSugars'], msg: 'Açúcares Adic. excede Açúcares Totais' });
    }
    if (!isNaN(totalSugars) && !isNaN(carbs) && totalSugars > carbs && carbs > 0) {
        warnings.push({ fields: ['totalSugars', 'carbs'], msg: 'Açúcares Totais excede Carboidratos' });
    }
    return warnings;
}

// ---- Running Totals ---------------------------------------------------------

function computeRunningTotals() {
    let totalWeight = 0;
    const sums = { energyKcal: 0, carbs: 0, proteins: 0, totalFat: 0, fiber: 0, sodium: 0 };
    for (const ing of state.ingredients) {
        const qty = parseFloat(ing.quantity) || 0;
        if (qty <= 0) continue;
        totalWeight += qty;
        const n = ing.nutritionalInfo || {};
        const f = qty / 100;
        sums.energyKcal += (parseFloat(n.energyKcal) || (estimateKcal(n) || 0)) * f;
        sums.carbs += (parseFloat(n.carbs) || 0) * f;
        sums.proteins += (parseFloat(n.proteins) || 0) * f;
        sums.totalFat += (parseFloat(n.totalFat) || 0) * f;
        sums.fiber += (parseFloat(n.fiber) || 0) * f;
        sums.sodium += (parseFloat(n.sodium) || 0) * f;
    }
    if (totalWeight <= 0) return null;
    const per100 = {};
    for (const k of Object.keys(sums)) {
        per100[k] = (sums[k] / totalWeight) * 100;
    }
    return { totalWeight, count: state.ingredients.length, per100 };
}

function renderRunningTotals() {
    const el = document.getElementById('running-totals');
    if (!el) return;
    const totals = computeRunningTotals();
    if (!totals) {
        el.innerHTML = '';
        return;
    }
    const unit = state.product.portionUnit || 'g';
    const p = totals.per100;
    const fmt = (v, d = 1) => v.toFixed(d);
    el.innerHTML = `
        <div class="bg-black/30 border border-white/[0.12] rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
                <span class="text-[10px] font-bold text-terracota-cyan uppercase tracking-wider">Resumo da Receita</span>
                <span class="text-xs text-terracota-textMuted">${totals.count} ingrediente${totals.count > 1 ? 's' : ''} · ${fmt(totals.totalWeight, 0)}${unit} total</span>
            </div>
            <div class="grid grid-cols-3 sm:grid-cols-6 gap-3 text-center">
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Kcal</div>
                    <div class="text-sm font-bold text-white">${fmt(p.energyKcal, 0)}</div>
                </div>
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Carb</div>
                    <div class="text-sm font-bold text-white">${fmt(p.carbs)}g</div>
                </div>
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Prot</div>
                    <div class="text-sm font-bold text-white">${fmt(p.proteins)}g</div>
                </div>
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Gord</div>
                    <div class="text-sm font-bold text-white">${fmt(p.totalFat)}g</div>
                </div>
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Fibra</div>
                    <div class="text-sm font-bold text-white">${fmt(p.fiber)}g</div>
                </div>
                <div>
                    <div class="text-[10px] text-terracota-textMuted uppercase">Sódio</div>
                    <div class="text-sm font-bold text-white">${fmt(p.sodium, 0)}mg</div>
                </div>
            </div>
            <div class="text-[10px] text-terracota-textMuted mt-2 text-right">valores por 100${unit} da receita</div>
        </div>
    `;
}

// ---- Step 2: Ingredients ----------------------------------------------------

function renderStep2(container) {
    const unit = state.product.portionUnit || 'g';
    const hasIngredients = state.ingredients.length > 0;

    const emptyStateHtml = !hasIngredients ? `
        <div class="text-center py-8">
            <div class="mb-4 inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-terracota-cyan/10 border border-terracota-cyan/20 text-terracota-cyan">
                <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </div>
            <p class="text-terracota-textLight text-sm mb-1">Comece adicionando ingredientes</p>
            <p class="text-terracota-textMuted text-xs mb-5">Busque na Tabela TACO ou insira manualmente</p>
            <div class="flex justify-center gap-3">
                <button onclick="addIngredientWithFocus()" class="px-5 py-2.5 bg-terracota-cyan/20 border border-terracota-cyan/40 text-terracota-cyan text-xs font-bold uppercase tracking-wider rounded-lg hover:bg-terracota-cyan/30 transition-all">
                    <span class="inline-flex items-center gap-1.5"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg> Buscar na TACO</span>
                </button>
                <button onclick="addIngredient()" class="px-5 py-2.5 bg-white/10 border border-white/20 text-white text-xs font-bold uppercase tracking-wider rounded-lg hover:bg-white/20 transition-all">
                    + Adicionar Manual
                </button>
            </div>
        </div>` : '';

    container.innerHTML = `
        <div class="space-y-5">
            <div class="flex justify-between items-center">
                <h3 class="text-2xl font-bold text-white font-heading">Ingredientes</h3>
                ${hasIngredients ? `<button onclick="addIngredient()" class="text-xs font-bold uppercase tracking-wider px-4 py-2 bg-white/10 text-terracota-cyan rounded-full hover:bg-terracota-cyan hover:text-terracota-deepDark transition-colors">+ Adicionar</button>` : ''}
            </div>
            <div id="drop-zone" class="border-2 border-dashed border-white/20 rounded-xl p-6 text-center transition-all bg-white/5 hover:bg-white/10 hover:border-terracota-cyan group relative">
                <input type="file" id="file-upload" class="hidden" accept=".xlsx" onchange="handleExcelUpload(this.files[0])">
                <div class="pointer-events-none flex items-center justify-center gap-4">
                    <svg class="w-8 h-8 text-terracota-textLight group-hover:text-terracota-cyan transition-colors flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    <div class="text-left">
                        <p class="text-terracota-textLight text-sm">Importar Excel (.xlsx)</p>
                        <p class="text-[10px] text-terracota-textLight/50">Arraste aqui ou <button onclick="document.getElementById('file-upload').click()" class="text-terracota-cyan underline pointer-events-auto">selecione</button></p>
                    </div>
                </div>
                <div id="upload-loading" class="absolute inset-0 bg-terracota-deepDark/90 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center hidden">
                    <div class="w-8 h-8 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin mb-3"></div>
                    <p class="text-xs text-terracota-cyan font-bold uppercase tracking-wider">Processando...</p>
                </div>
            </div>
            <div id="ingredients-list" class="space-y-4">
                ${emptyStateHtml}
            </div>
            <div id="running-totals"></div>
        </div>
    `;

    if (hasIngredients) {
        const list = document.getElementById('ingredients-list');
        list.innerHTML = '';
        state.ingredients.forEach((ing, index) => {
            list.appendChild(createIngredientRow(ing, index));
        });
        renderRunningTotals();
    }
    setupDragAndDrop();
}

function createIngredientRow(ing, index) {
    const inputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1.5";
    const smInputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1";
    const labelClass = "block text-[10px] text-slate-400 mb-0.5 uppercase tracking-wider";
    const nutri = ing.nutritionalInfo || {};
    const unit = state.product.portionUnit || 'g';
    const warnings = getIngredientWarnings(nutri);
    const warnFields = new Set(warnings.flatMap(w => w.fields));
    const hasTaco = !!ing._tacoId;
    const estimated = estimateKcal(nutri);
    const hasManualKcal = nutri.energyKcal !== '' && nutri.energyKcal !== null && nutri.energyKcal !== undefined;
    const kcalDisplay = hasManualKcal ? nutri.energyKcal : (estimated ?? '');
    const kcalIsAuto = !hasManualKcal && estimated !== null;

    const warnClass = (field) => warnFields.has(field) ? 'border-yellow-500/60 bg-yellow-500/5' : '';

    const el = document.createElement('div');
    el.className = 'bg-white/[0.08] border border-white/[0.15] rounded-xl p-4 relative group hover:bg-white/[0.12] transition-colors';
    el.setAttribute('data-ing-index', index);

    el.innerHTML = `
        <div class="flex gap-3 items-start mb-3">
            <div class="flex-1 relative">
                <label class="${labelClass}">Nome do Ingrediente ${hasTaco ? '<span class="text-[10px] px-1.5 py-0.5 bg-emerald-500/20 text-emerald-300 rounded ml-1">TACO</span>' : ''}</label>
                <input type="text" class="${inputClass} ingredient-name-input" value="${escapeHtml(ing.name)}" data-index="${index}" placeholder="Digite para buscar na TACO..." autocomplete="off">
            </div>
            <div class="w-28 flex-shrink-0">
                <label class="${labelClass}">Qtd (${unit})</label>
                <input type="number" class="${inputClass}" value="${escapeHtml(ing.quantity)}" oninput="updateIngredient(${index}, 'quantity', this.value); renderRunningTotals();" placeholder="100" min="0" step="0.1">
            </div>
        </div>
        <div class="bg-black/30 p-3 rounded-lg border border-white/[0.08]">
            <div class="text-[10px] font-bold text-terracota-cyan uppercase tracking-wider mb-2">Nutricional (por 100${unit})</div>
            <div class="grid grid-cols-3 sm:grid-cols-5 gap-x-2 gap-y-1.5">
                <div class="relative">
                    <label class="${labelClass}">Kcal ${kcalIsAuto ? '<span class="text-[10px] text-terracota-cyan/80">auto</span>' : ''}</label>
                    <input type="number" class="${smInputClass} ${kcalIsAuto ? 'text-terracota-cyan' : ''}" value="${kcalDisplay}" oninput="updateIngredientNutri(${index}, 'energyKcal', this.value)" title="Energia é recalculada automaticamente pelo motor ANVISA" min="0" step="0.1">
                </div>
                <div>
                    <label class="${labelClass}">Carb (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('carbs')}" value="${nutri.carbs ?? ''}" oninput="updateIngredientNutri(${index}, 'carbs', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass}">Prot (g)</label>
                    <input type="number" class="${smInputClass}" value="${nutri.proteins ?? ''}" oninput="updateIngredientNutri(${index}, 'proteins', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass}">Gord Tot (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('totalFat')}" value="${nutri.totalFat ?? ''}" oninput="updateIngredientNutri(${index}, 'totalFat', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass}">Fibra (g)</label>
                    <input type="number" class="${smInputClass}" value="${nutri.fiber ?? ''}" oninput="updateIngredientNutri(${index}, 'fiber', this.value)" min="0" step="0.01">
                </div>
            </div>
            <div class="grid grid-cols-3 sm:grid-cols-5 gap-x-2 gap-y-1.5 mt-2 pt-2 border-t border-white/[0.08]">
                <div>
                    <label class="${labelClass} text-slate-400">↳ Sat (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('saturatedFat')}" value="${nutri.saturatedFat ?? ''}" oninput="updateIngredientNutri(${index}, 'saturatedFat', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass} text-slate-400">↳ Trans (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('transFat')}" value="${nutri.transFat ?? ''}" oninput="updateIngredientNutri(${index}, 'transFat', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass} text-slate-400">↳ Aç Tot (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('totalSugars')}" value="${nutri.totalSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'totalSugars', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass} text-slate-400">↳ Aç Adic (g)</label>
                    <input type="number" class="${smInputClass} ${warnClass('addedSugars')}" value="${nutri.addedSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'addedSugars', this.value)" min="0" step="0.01">
                </div>
                <div>
                    <label class="${labelClass}">Sódio (mg)</label>
                    <input type="number" class="${smInputClass}" value="${nutri.sodium ?? ''}" oninput="updateIngredientNutri(${index}, 'sodium', this.value)" min="0" step="0.01">
                </div>
            </div>
            <div class="ing-warnings">${warnings.length > 0 ? warnings.map(w => `<p class="text-[11px] text-yellow-400 flex items-center gap-1 mt-1"><svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path></svg>${escapeHtml(w.msg)}</p>`).join('') : ''}</div>
        </div>
        <div class="absolute -top-2 -right-2 flex gap-1 opacity-70 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
            <button onclick="copyIngredient(${index})" class="bg-terracota-cyan/80 text-terracota-deepDark rounded-full p-1.5 shadow-lg hover:bg-terracota-cyan" title="Duplicar ingrediente">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>
            </button>
            <button onclick="removeIngredient(${index})" class="bg-red-500/80 text-white rounded-full p-1.5 shadow-lg hover:bg-red-600" title="Remover ingrediente">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
    `;

    // Autocomplete for ingredient name
    const nameInput = el.querySelector('.ingredient-name-input');
    nameInput.addEventListener('input', (e) => {
        const val = e.target.value;
        state.ingredients[index].name = val;
        state.ingredients[index]._tacoId = null;

        clearTimeout(_tacoDebounceTimer);
        if (val.length >= 2) {
            _showTacoLoader(nameInput);
            _tacoDebounceTimer = setTimeout(async () => {
                const results = await tacoSearch(val);
                _removeTacoLoader();
                if (state.ingredients[index]?.name === val) {
                    showTacoDropdown(nameInput, results, index);
                }
            }, 300);
        } else {
            closeTacoDropdown();
        }
    });
    nameInput.addEventListener('blur', () => {
        setTimeout(closeTacoDropdown, 200);
    });
    nameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { closeTacoDropdown(); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); _highlightTacoItem('down'); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); _highlightTacoItem('up'); return; }
        if (e.key === 'Enter' && _activeTacoDropdown) {
            e.preventDefault();
            _selectHighlightedTacoItem();
        }
    });

    return el;
}

function addIngredient() {
    state.ingredients.push({
        id: Date.now(),
        name: '',
        quantity: '',
        _tacoId: null,
        nutritionalInfo: {
            energyKcal: '',
            carbs: '',
            proteins: '',
            totalFat: '',
            saturatedFat: '',
            transFat: '',
            fiber: '',
            sodium: '',
            totalSugars: '',
            addedSugars: '',
        }
    });
    renderStep2(document.getElementById('wizard-content'));
}

function addIngredientWithFocus() {
    addIngredient();
    requestAnimationFrame(() => {
        const inputs = document.querySelectorAll('.ingredient-name-input');
        const last = inputs[inputs.length - 1];
        if (last) last.focus();
    });
}

function copyIngredient(index) {
    const original = state.ingredients[index];
    if (!original) return;
    const copy = JSON.parse(JSON.stringify(original));
    copy.id = Date.now();
    copy.name = copy.name ? copy.name + ' (cópia)' : '';
    copy._tacoId = original._tacoId || null;
    state.ingredients.splice(index + 1, 0, copy);
    renderStep2(document.getElementById('wizard-content'));
    showToast('Ingrediente duplicado.', 'info', 2000);
}

function removeIngredient(index) {
    state.ingredients.splice(index, 1);
    renderStep2(document.getElementById('wizard-content'));
}

function updateIngredient(index, field, value) {
    state.ingredients[index][field] = value;
}

function updateIngredientNutri(index, field, value) {
    const v = parseFloat(value);
    state.ingredients[index].nutritionalInfo[field] = isNaN(v) ? '' : v;
    _refreshIngredientFeedback(index);
}

function _refreshIngredientFeedback(index) {
    const row = document.querySelector(`[data-ing-index="${index}"]`);
    if (!row) return;
    const nutri = state.ingredients[index].nutritionalInfo;

    // Auto kcal
    const estimated = estimateKcal(nutri);
    const hasManual = nutri.energyKcal !== '' && nutri.energyKcal !== null && nutri.energyKcal !== undefined;
    const kcalInput = row.querySelector('input[oninput*="energyKcal"]');
    if (kcalInput && !hasManual && estimated !== null) {
        kcalInput.value = estimated;
        kcalInput.classList.add('text-terracota-cyan');
    } else if (kcalInput && hasManual) {
        kcalInput.classList.remove('text-terracota-cyan');
    }

    // Inline warnings
    const warnings = getIngredientWarnings(nutri);
    const warnContainer = row.querySelector('.ing-warnings');
    const warnFields = new Set(warnings.flatMap(w => w.fields));
    const allFields = ['saturatedFat', 'transFat', 'totalFat', 'addedSugars', 'totalSugars', 'carbs'];
    for (const f of allFields) {
        const input = row.querySelector(`input[oninput*="'${f}'"]`);
        if (!input) continue;
        input.classList.toggle('border-yellow-500/60', warnFields.has(f));
        input.classList.toggle('bg-yellow-500/5', warnFields.has(f));
    }

    if (warnContainer) {
        if (warnings.length > 0) {
            warnContainer.innerHTML = warnings.map(w => `<p class="text-[11px] text-yellow-400 flex items-center gap-1 mt-1"><svg class="w-3 h-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path></svg>${escapeHtml(w.msg)}</p>`).join('');
        } else {
            warnContainer.innerHTML = '';
        }
    }

    renderRunningTotals();
}

// ---- Validation -------------------------------------------------------------

function validateStep(step) {
    if (step === 1) {
        if (!state.product.name) { showToast('Informe o nome do produto.', 'warning'); return false; }
        if (!state.product.portionSize) { showToast('Informe o tamanho da porção.', 'warning'); return false; }
        if ((parseFloat(state.product.portionSize) || 0) <= 0) {
            showToast('A porção deve ser um número positivo.', 'warning');
            return false;
        }
        if (!state.product.portionDesc?.trim()) {
            showToast('Medida caseira não informada (ex: "1 fatia"). Preencha para conformidade regulatória.', 'info', 4000);
        }
        if ((!state.product.allergenKeys || state.product.allergenKeys.length === 0) && !state.product.allergens?.trim() && !state.product.customAllergens?.trim()) {
            showToast('Declaração de alérgenos não preenchida. Obrigatória conforme RDC 26/2015.', 'info', 4000);
        }
        if (!state.product.groupCode) {
            showToast('Grupo de alimento não selecionado. Opcional, mas recomendado para validação da porção.', 'info', 3000);
        }
        return true;
    }
    if (step === 2) {
        if (state.ingredients.length === 0) {
            showToast('Adicione pelo menos um ingrediente.', 'warning');
            return false;
        }
        const issues = [];
        let firstBadIndex = -1;
        state.ingredients.forEach((ing, idx) => {
            const problems = [];
            if (!ing.name || !ing.name.trim()) problems.push('sem nome');
            const qty = parseFloat(ing.quantity);
            if (!ing.quantity || isNaN(qty) || qty <= 0) problems.push('sem quantidade');
            const n = ing.nutritionalInfo || {};
            const hasSomeNutri = ['carbs', 'proteins', 'totalFat'].some(f => {
                const v = parseFloat(n[f]);
                return !isNaN(v) && v > 0;
            });
            if (!hasSomeNutri) problems.push('sem dados nutricionais');
            if (problems.length > 0) {
                issues.push(`#${idx + 1}: ${problems.join(', ')}`);
                if (firstBadIndex < 0) firstBadIndex = idx;
                const row = document.querySelector(`[data-ing-index="${idx}"]`);
                if (row) row.classList.add('border-red-400/50', 'bg-red-500/5');
            }
        });
        if (issues.length > 0) {
            showToast(`Corrija os ingredientes: ${issues.join(' | ')}`, 'warning', 6000);
            return false;
        }
        return true;
    }
    return true;
}

// ---- Calculate (Preview only — no save) -------------------------------------

async function calculateResult() {
    const btn = document.getElementById('btn-next');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '<div class="w-5 h-5 border-2 border-terracota-base border-t-transparent rounded-full animate-spin mr-2"></div> Calculando...';
    btn.disabled = true;

    const payload = {
        product: state.product,
        ingredients: state.ingredients.map(ing => ({
            id: ing.id,
            name: ing.name,
            quantity: parseFloat(ing.quantity) || 0,
            nutritionalInfo: {
                energyKcal: parseFloat(ing.nutritionalInfo?.energyKcal) || 0,
                carbs: parseFloat(ing.nutritionalInfo?.carbs) || 0,
                proteins: parseFloat(ing.nutritionalInfo?.proteins) || 0,
                totalFat: parseFloat(ing.nutritionalInfo?.totalFat) || 0,
                saturatedFat: parseFloat(ing.nutritionalInfo?.saturatedFat) || 0,
                transFat: parseFloat(ing.nutritionalInfo?.transFat) || 0,
                fiber: parseFloat(ing.nutritionalInfo?.fiber) || 0,
                sodium: parseFloat(ing.nutritionalInfo?.sodium) || 0,
                totalSugars: parseFloat(ing.nutritionalInfo?.totalSugars) || 0,
                addedSugars: parseFloat(ing.nutritionalInfo?.addedSugars) || 0,
            }
        }))
    };

    try {
        const res = await fetch('/api/calculate', {
            method: 'POST',
            headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify(payload)
        });
        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }
        const data = await res.json();

        if (!res.ok) {
            showToast(data.error || 'Erro ao calcular.', 'error');
            return;
        }

        state.calculatedData = data.calculatedData;
        state.isFinalized = false;
        state.savedTableId = null;
        state.saveTableError = '';
        state.currentIdempotencyKey = generateIdempotencyKey();

        // Show calculation warnings (validation, portion, etc.)
        if (data.calculationWarnings && data.calculationWarnings.length > 0) {
            for (const w of data.calculationWarnings) {
                showToast(w, 'warning');
            }
        }

        // Check for quota warning from server
        if (data.warning === 'QUOTA_EXHAUSTED') {
            state.quotaInfo = state.quotaInfo || {};
            state.quotaInfo.canCreate = false;
        }

        goToStep(3);
    } catch (e) {
        console.error(e);
        showToast('Erro ao calcular. Verifique a conexão.', 'error');
    } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
    }
}

// ---- Step 3: Result (Preview / Finalized) -----------------------------------

function renderStep3(container) {
    if (!state.calculatedData) {
        container.innerHTML = '<div class="text-red-400 text-center">Erro ao carregar dados calculados.</div>';
        return;
    }

    if (state.isFinalized) {
        renderStep3Finalized(container);
    } else {
        renderStep3Preview(container);
    }
}

function renderStep3Preview(container) {
    const allData = state.calculatedData;
    const product = state.product;
    const canGenerate = !state.quotaInfo || state.quotaInfo.canCreate !== false;

    const warningHtml = !canGenerate
        ? `<div class="mb-4 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl text-center">
                <p class="text-yellow-300 text-sm font-medium">Limite de tabelas atingido no seu plano.</p>
                <p class="text-yellow-300/70 text-xs mt-1">Você pode visualizar esta prévia, mas para gerar e salvar, faça upgrade.</p>
                <a href="/account/upgrade" class="inline-block mt-3 px-6 py-2 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white text-sm font-bold rounded-lg hover:scale-105 transition-all">Fazer Upgrade</a>
           </div>`
        : '';

    container.innerHTML = `
        <div class="text-center mb-4">
            <p class="text-sm text-terracota-textMuted">
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>
                    Prévia — revise antes de gerar
                </span>
            </p>
        </div>
        ${warningHtml}
        ${buildNutritionTableHtml(allData, product)}
        <div class="flex justify-center gap-4 mt-8 no-print flex-wrap">
            ${canGenerate ? `
            <button id="btn-generate" onclick="finalizeTable()" class="px-10 py-3.5 bg-gradient-to-r from-terracota-purple to-purple-600 text-white font-bold rounded-lg hover:scale-105 shadow-[0_0_25px_rgba(123,44,191,0.4)] transition-all flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                Gerar Tabela
            </button>` : ''}
            <button onclick="goToStep(2)" class="px-8 py-3.5 bg-white/10 border border-white/20 text-white font-bold rounded-lg hover:bg-white/20 transition-all flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                Editar Ingredientes
            </button>
            <button onclick="goToStep(1)" class="px-8 py-3.5 bg-white/10 border border-white/20 text-terracota-textMuted font-bold rounded-lg hover:bg-white/20 hover:text-white transition-all flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                Editar Produto
            </button>
        </div>
    `;
}

function renderStep3Finalized(container) {
    const allData = state.calculatedData;
    const product = state.product;
    const q = state.quotaInfo;
    const canCreateMore = q && q.canCreate;

    container.innerHTML = `
        <div class="text-center mb-4">
            <div class="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded-full">
                <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                <span class="text-emerald-300 text-sm font-semibold">Tabela gerada e salva com sucesso!</span>
            </div>
        </div>
        ${quotaBadgeHtml()}
        ${buildNutritionTableHtml(allData, product)}
        <div class="flex justify-center gap-4 mt-8 no-print flex-wrap">
            <button onclick="printTable()" class="px-8 py-3.5 bg-terracota-cyan text-terracota-deepDark font-bold rounded-lg hover:bg-white shadow-[0_0_20px_rgba(0,196,204,0.3)] transition-all flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                Imprimir / PDF
            </button>
            ${canCreateMore ? `
            <button onclick="startNewTable()" class="px-8 py-3.5 bg-terracota-purple text-white font-bold rounded-lg hover:bg-purple-600 shadow-sm transition-all flex items-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                Nova Tabela
            </button>` : `
            <a href="/account/upgrade" class="px-8 py-3.5 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white font-bold rounded-lg hover:scale-105 shadow-[0_0_25px_rgba(123,44,191,0.3)] transition-all flex items-center gap-2 no-underline">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path></svg>
                Fazer Upgrade
            </a>`}
            <a href="/account/" class="px-6 py-3.5 bg-white/10 border border-white/20 text-white font-bold rounded-lg hover:bg-white/20 transition-all flex items-center gap-2 no-underline">
                Minha Conta
            </a>
        </div>
    `;
}

// ---- Finalize (save table + consume quota) ----------------------------------

async function finalizeTable() {
    const btn = document.getElementById('btn-generate');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = `
        <div class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
        Gerando...
    `;

    const result = await saveCurrentTable();

    if (result.ok) {
        state.isFinalized = true;
        showToast('Tabela gerada com sucesso!', 'success');
        // Re-fetch quota so buttons update
        await fetchQuota();
        renderStep3(document.getElementById('wizard-content'));
    } else if (result.code === 'QUOTA_EXCEEDED') {
        showToast('Limite de tabelas atingido. Faça upgrade para continuar.', 'error', 6000);
        if (state.quotaInfo) state.quotaInfo.canCreate = false;
        renderStep3(document.getElementById('wizard-content'));
    } else {
        showToast(result.error || 'Erro ao gerar tabela.', 'error');
        btn.disabled = false;
        btn.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
            Tentar Novamente
        `;
    }
}

// ---- Start New Table --------------------------------------------------------

function startNewTable() {
    state.product = {
        name: '',
        portionSize: '',
        portionDesc: '',
        allergens: '',
        gluten: 'Não contém glúten',
        foodForm: 'solid',
        portionUnit: 'g',
        allergenKeys: [],
        customAllergens: '',
        glutenStatus: 'gluten_free',
        groupCode: '',
    };
    state.ingredients = [];
    state.calculatedData = null;
    state.isFinalized = false;
    state.savedTableId = null;
    state.saveTableError = '';
    state.currentIdempotencyKey = null;
    goToStep(1);
}

// ---- Shared Nutrition Table HTML Builder ------------------------------------

function buildNutritionTableHtml(allData, product) {
    const per100 = allData.per100g || allData.per100_base || {};
    const portion = allData.perPortion || allData;
    const energyKj = Math.round((portion.energy?.raw ?? 0) * 4.184);
    const transVd = portion.transFat?.vd === '' ? '**' : (portion.transFat?.vd ?? '**');
    const totalSugarsVd = portion.totalSugars?.vd === '' ? '**' : (portion.totalSugars?.vd ?? '**');

    const portionSize = product.portionSize || product.portion_size || '';
    const portionDesc = product.portionDesc || product.portion_desc || '';
    const glutenText = product.gluten || product.gluten_status || '';
    const allergensText = product.allergens || '';
    const portionUnit = product.portionUnit || product.portion_unit || 'g';
    const baseLabel = portionUnit === 'ml' ? '100 ml' : '100 g';

    return `
        <div id="nutritional-table-print-area" style="max-width: 36rem; margin: 0 auto; padding: 2rem; background: #ffffff; color: #000000; border-radius: 0.75rem; border: 1px solid #e5e7eb;">
            <h3 style="font-size: 1.25rem; font-weight: 700; color: #000; border-bottom: 2px solid #000; padding-bottom: 0.5rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.05em;">Informação Nutricional</h3>
            <div style="margin-bottom: 1rem; font-size: 0.875rem; color: #000; font-weight: 500;">
                <p>Porção de: <strong>${escapeHtml(portionSize)} ${portionUnit}</strong> (${escapeHtml(portionDesc || '-')})</p>
            </div>
            <table style="width: 100%; font-size: 0.875rem; margin-bottom: 1.5rem; border-collapse: collapse; color: #000; background: #fff;">
                <thead>
                    <tr style="border-bottom: 2px solid #000;">
                        <th style="padding: 0.25rem 0; text-align: left; font-weight: 700; color: #000; background: #fff;">Nutriente</th>
                        <th style="padding: 0.25rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${baseLabel}</th>
                        <th style="padding: 0.25rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">Por porção</th>
                        <th style="padding: 0.25rem 0; text-align: right; font-weight: 700; color: #000; background: #fff; min-width: 60px;">% VD (*)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Valor Energético</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.energy?.display ?? 0} kcal</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.energy?.display ?? 0} kcal = ${energyKj} kJ</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.energy?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Carboidratos</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.carbs?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.carbs?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.carbs?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Açúcares Totais</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.totalSugars?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.totalSugars?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${totalSugarsVd}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Açúcares Adicionados</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.addedSugars?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.addedSugars?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.addedSugars?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Proteínas</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.proteins?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.proteins?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.proteins?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Gorduras Totais</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.totalFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.totalFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.totalFat?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Gorduras Saturadas</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.saturatedFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.saturatedFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.saturatedFat?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Gorduras Trans</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.transFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.transFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${transVd}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Fibra Alimentar</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.fiber?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.fiber?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.fiber?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Sódio</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100.sodium?.display ?? 0} mg</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.sodium?.display ?? 0} mg</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.sodium?.vd ?? 0}</td>
                    </tr>
                </tbody>
            </table>
            <p style="font-size: 10px; line-height: 1.4; color: #4b5563; margin-bottom: 1.5rem;">
                (*) % Valores Diários de referência com base em uma dieta de 2.000 kcal ou 8.400 kJ. Seus valores diários podem ser maiores ou menores dependendo de suas necessidades energéticas. (**) VD não estabelecido.
            </p>
            <div style="border-top: 1px solid #d1d5db; padding-top: 1rem;">
                <p style="font-size: 0.875rem; font-weight: 700; color: #000; text-transform: uppercase; margin-bottom: 0.25rem;">${escapeHtml(glutenText)}</p>
                ${allergensText ? `<p style="font-size: 0.875rem; font-weight: 700; color: #000; text-transform: uppercase;">${escapeHtml(allergensText)}</p>` : ''}
            </div>
        </div>
    `;
}

// ---- Drag & Drop + Excel Import ---------------------------------------------

function setupDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
        dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }, false);
    });
    ['dragenter', 'dragover'].forEach(ev => {
        dropZone.addEventListener(ev, () => { dropZone.classList.add('border-terracota-cyan', 'bg-white/10'); }, false);
    });
    ['dragleave', 'drop'].forEach(ev => {
        dropZone.addEventListener(ev, () => { dropZone.classList.remove('border-terracota-cyan', 'bg-white/10'); }, false);
    });
    dropZone.addEventListener('drop', e => {
        const file = e.dataTransfer?.files?.[0];
        if (file) handleExcelUpload(file);
    }, false);
}

async function handleExcelUpload(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
        showToast('Use um arquivo Excel (.xlsx)', 'warning');
        return;
    }

    const loading = document.getElementById('upload-loading');
    if (loading) loading.classList.remove('hidden');

    try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/api/import-excel', {
            method: 'POST',
            headers: withCsrfHeaders({}),
            body: formData
        });
        if (res.status === 401) {
            window.location.href = '/login';
            return;
        }
        const data = await res.json();

        if (!res.ok) {
            showToast(data.error || 'Erro ao importar.', 'error');
            return;
        }

        state.ingredients = state.ingredients.concat(data.ingredients);
        showToast(`${data.ingredients.length} ingredientes importados!`, 'success');
        if (data.warnings && data.warnings.length > 0) {
            for (const w of data.warnings) {
                showToast(w, 'warning');
            }
        } else if (data.warning) {
            showToast(data.warning, 'warning');
        }
        renderStep2(document.getElementById('wizard-content'));
    } catch (e) {
        console.error(e);
        showToast('Erro ao ler o arquivo Excel.', 'error');
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}
