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
        groupCode: '',
        servingsPerPackage: '',
        packageWeight: ''
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

function announceToSR(message) {
    const el = document.getElementById('sr-announcer');
    if (!el) return;
    el.textContent = '';
    requestAnimationFrame(() => { el.textContent = message; });
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

    // Cap at 3 visible toasts — remove oldest
    while (container.children.length >= 3) {
        container.firstElementChild.remove();
    }

    const icons = {
        success: 'ph-check-circle',
        error: 'ph-x-circle',
        warning: 'ph-warning',
        info: 'ph-info'
    };
    const colors = {
        success: 'bg-emerald-500/90 border-emerald-400',
        error: 'bg-red-500/90 border-red-400',
        warning: 'bg-yellow-500/90 border-yellow-400 text-black',
        info: 'bg-terracota-cyan/90 border-terracota-cyan text-black'
    };
    const toast = document.createElement('div');
    toast.className = `pointer-events-auto relative px-5 py-3 rounded-xl border text-sm font-medium shadow-lg backdrop-blur-sm transition-all duration-300 opacity-0 translate-x-4 overflow-hidden flex items-center gap-2 ${colors[type] || colors.info}`;
    toast.style.setProperty('--toast-duration', `${duration}ms`);
    toast.innerHTML = `
        <i class="ph-bold ${icons[type] || icons.info} text-base flex-shrink-0"></i>
        <span class="flex-1">${escapeHtml(message)}</span>
        <button class="toast-close flex-shrink-0 ml-2 opacity-60 hover:opacity-100" onclick="this.closest('.pointer-events-auto').remove()">
            <i class="ph ph-x text-base"></i>
        </button>
        <div class="toast-progress"></div>
    `;
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
        const res = await fetch('/app/api/quota', { headers: withCsrfHeaders() });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        if (!res.ok) return null;
        state.quotaInfo = await res.json();
        return state.quotaInfo;
    } catch (e) { console.error('fetchQuota error', e); return null; }
}

async function fetchLatestTable() {
    try {
        const res = await fetch('/app/api/tables/latest', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.lastTable = data.table;
        return data.table;
    } catch (e) { console.error('fetchLatestTable error', e); return null; }
}

async function fetchAllergenRegistry() {
    if (state.allergenRegistry) return state.allergenRegistry;
    try {
        const res = await fetch('/app/api/allergens', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.allergenRegistry = data;
        return data;
    } catch (e) { console.error('fetchAllergenRegistry error', e); return null; }
}

async function fetchPortionGroups() {
    if (state.portionGroups) return state.portionGroups;
    try {
        const res = await fetch('/app/api/portion-references', { headers: withCsrfHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        state.portionGroups = data.groups;
        return data.groups;
    } catch (e) { console.error('fetchPortionGroups error', e); return null; }
}

/**
 * Return portion groups filtered by current foodForm.
 * Groups with food_form "both" are always included.
 */
function getFilteredPortionGroups() {
    const all = state.portionGroups || [];
    const form = state.product.foodForm;
    return all.filter(g => g.food_form === form || g.food_form === 'both');
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
        const res = await fetch('/app/api/tables', {
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
        // Check for autosaved draft before showing welcome
        const hasDraft = _checkDraftOnLoad();
        if (!hasDraft) {
            renderWelcome();
        }
    }
    setupNavigation();
}

async function preloadDuplicateIfAny() {
    const params = new URLSearchParams(window.location.search);
    const duplicateId = params.get('duplicate');
    if (!duplicateId) return false;
    try {
        const res = await fetch(`/app/api/tables/${duplicateId}`, { headers: withCsrfHeaders() });
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
            servingsPerPackage: data.product_data?.servingsPerPackage || data.product_data?.servings_per_package || '',
            packageWeight: data.product_data?.packageWeight || data.product_data?.package_weight || '',
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
    const content = document.getElementById('wizard-content');
    const prevStep = state.currentStep;
    if (prevStep === step) { updateUI(); return; }

    // Fade out → swap → fade in
    content.classList.remove('wizard-fade-in');
    content.classList.add('wizard-fade-out');
    const onFadeOut = () => {
        content.removeEventListener('animationend', onFadeOut);
        state.currentStep = step;
        updateUI();
        content.classList.remove('wizard-fade-out');
        content.classList.add('wizard-fade-in');
        // Auto-scroll wizard into view
        const container = document.getElementById('app-container');
        if (container) container.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Announce step change to screen readers
        announceToSR(`Passo ${step} de 3${step === 1 ? ': Dados do Produto' : step === 2 ? ': Ingredientes' : ': Tabela Nutricional'}`);
    };
    content.addEventListener('animationend', onFadeOut);
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
    const steps = [
        { label: 'Produto', icon: 'ph-package' },
        { label: 'Ingredientes', icon: 'ph-bowl-food' },
        { label: 'Tabela', icon: 'ph-table' }
    ];
    const fillPercent = step === 1 ? 0 : step === 2 ? 50 : 100;
    const ingredientCount = state.ingredients.length;

    const items = steps.map((s, idx) => {
        const sNum = idx + 1;
        const completed = sNum < step;
        const active = sNum <= step;
        const current = sNum === step;
        const canClick = sNum < step || (sNum === 3 && state.calculatedData);
        const bgCircle = active
            ? 'bg-terracota-cyan text-terracota-deepDark shadow-[0_0_15px_rgba(0,196,204,0.4)]'
            : 'bg-terracota-deepDark border border-white/20 text-terracota-textLight';
        const ring = current ? 'ring-4 ring-terracota-cyan/20' : '';
        const textClass = active ? 'text-terracota-cyan' : 'text-terracota-textLight/50';
        const clickClass = canClick ? 'cursor-pointer hover:scale-110' : '';
        const clickAttr = canClick ? `onclick="goToStep(${sNum})"` : '';

        // Inner content: checkmark for completed, number for current/future
        const inner = completed
            ? '<i class="ph-bold ph-check text-base"></i>'
            : sNum;

        // Badge on step 2 circle showing ingredient count
        const badge = sNum === 2 && ingredientCount > 0
            ? `<span class="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold bg-terracota-purple text-white rounded-full px-1">${ingredientCount}</span>`
            : '';

        return `
            <div class="relative z-10 flex flex-col items-center ${clickClass}" ${clickAttr}>
                <div class="relative">
                    <div class="progress-step-circle w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm ${bgCircle} ${ring}">${inner}</div>
                    ${badge}
                </div>
                <span class="mt-3 text-xs font-medium uppercase tracking-wider flex items-center gap-1 ${textClass}">
                    <i class="${s.icon} text-sm"></i> ${s.label}
                </span>
            </div>
        `;
    }).join('');

    return `<nav aria-label="Progresso da calculadora" class="flex items-center justify-between relative" role="navigation">
        <div class="absolute w-full top-5 h-0.5 bg-white/10 -z-0"></div>
        <div class="progress-line absolute top-5 h-0.5 bg-terracota-cyan -z-0" style="width: ${fillPercent}%" role="progressbar" aria-valuenow="${step}" aria-valuemin="1" aria-valuemax="3"></div>
        ${items}
    </nav>
    <div class="flex justify-between items-center mt-1">
        ${quotaBadgeHtml()}
        <span id="autosave-indicator" class="text-[10px] text-terracota-textMuted opacity-0 transition-opacity duration-300"></span>
    </div>`;
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
                    <i class="ph-bold ph-printer text-xl mr-2"></i>
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
                <i class="ph-bold ph-lock text-3xl"></i>
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
                <i class="ph-bold ph-file-text text-4xl"></i>
            </div>
            <h2 class="text-4xl font-bold text-white mb-6 font-heading">Calculadora Nutricional</h2>
            <p class="text-xl text-terracota-textLight mb-10 max-w-lg mx-auto font-light leading-relaxed">
                Gere tabelas nutricionais em conformidade com a <span class="text-terracota-cyan font-medium">RDC 429/2020</span> com a inteligência e design da Terracota.
            </p>
            ${quotaBadgeHtml()}
            <button onclick="goToStep(1)" class="mt-6 px-10 py-4 bg-terracota-cyan text-terracota-deepDark text-lg font-bold rounded-xl hover:bg-white hover:scale-105 shadow-[0_0_30px_rgba(0,196,204,0.3)] transition-all inline-flex items-center gap-2">
                <i class="ph-bold ph-play text-xl"></i> Iniciar Novo Produto
            </button>
        </div>
    `;
}

// ---- Step 1 Feedback Helpers ------------------------------------------------

function _refreshPortionFeedback() {
    const el = document.getElementById('portion-feedback');
    if (!el) return;
    const portion = parseFloat(state.product.portionSize);
    if (isNaN(portion) || portion <= 0) { el.innerHTML = ''; return; }

    const msgs = [];
    if (portion < 0.1) {
        msgs.push({ text: `Porção (${portion}${state.product.portionUnit}) abaixo do mínimo regulatório (0,1${state.product.portionUnit})`, color: 'text-red-400', icon: 'ph-x-circle' });
    } else if (portion > 10000) {
        msgs.push({ text: `Porção muito elevada (${portion}${state.product.portionUnit})`, color: 'text-yellow-400', icon: 'ph-warning' });
    }

    // Compare against selected group reference (±30% tolerance)
    if (state.product.groupCode && state.portionGroups) {
        const group = state.portionGroups.find(g => g.code === state.product.groupCode);
        if (group) {
            const ref = parseFloat(group.portion_g);
            const low = ref * 0.7, high = ref * 1.3;
            if (portion < low || portion > high) {
                msgs.push({ text: `Porção (${portion}) fora da faixa de referência do grupo "${group.name}" (${ref}${state.product.portionUnit} ±30%)`, color: 'text-yellow-400', icon: 'ph-warning' });
            } else {
                msgs.push({ text: `Porção dentro da faixa do grupo "${group.name}" (ref: ${ref}${state.product.portionUnit})`, color: 'text-emerald-400', icon: 'ph-check-circle' });
            }
        }
    }

    el.innerHTML = msgs.map(m => `<p class="text-[10px] ${m.color} flex items-center gap-1 mt-0.5"><i class="ph ${m.icon} text-xs flex-shrink-0"></i>${m.text}</p>`).join('');
}

function _refreshPackageFeedback() {
    const el = document.getElementById('package-feedback');
    if (!el) return;
    const portion = parseFloat(state.product.portionSize) || 0;
    const pkgWeight = parseFloat(state.product.packageWeight) || 0;
    const servings = parseFloat(state.product.servingsPerPackage) || 0;

    if (portion <= 0 || pkgWeight <= 0 || servings <= 0) {
        el.innerHTML = '';
        el.classList.add('hidden');
        return;
    }

    const msgs = [];
    const totalUsed = portion * servings;
    if (totalUsed > pkgWeight * 1.05) {
        msgs.push({ text: `Porção × porções (${totalUsed.toFixed(1)}) excede o peso da embalagem (${pkgWeight})`, color: 'text-red-400', icon: 'ph-x-circle' });
    } else if (totalUsed < pkgWeight * 0.5) {
        msgs.push({ text: `Porção × porções (${totalUsed.toFixed(1)}) é menos da metade do peso da embalagem (${pkgWeight}). Verifique.`, color: 'text-yellow-400', icon: 'ph-warning' });
    }

    if (msgs.length > 0) {
        el.classList.remove('hidden');
        el.innerHTML = msgs.map(m => `<p class="text-[10px] ${m.color} flex items-center gap-1"><i class="ph ${m.icon} text-xs flex-shrink-0"></i>${m.text}</p>`).join('');
    } else {
        el.innerHTML = '';
        el.classList.add('hidden');
    }
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

    // Build portion reference dropdown (filtered by foodForm)
    let portionGroupHtml = '';
    const filteredGroups = getFilteredPortionGroups();
    const allGroups = state.portionGroups || [];
    const totalGroupCount = allGroups.length;
    const filteredCount = filteredGroups.length;
    if (filteredGroups.length > 0) {
        const options = filteredGroups.map(g =>
            `<option value="${g.code}" class="bg-terracota-deepDark" ${state.product.groupCode === g.code ? 'selected' : ''}>${escapeHtml(g.name)} (${g.portion_g}${portionUnitLabel} — ${escapeHtml(g.household_measure)})</option>`
        ).join('');
        const filterBadge = totalGroupCount !== filteredCount
            ? `<span class="text-[9px] text-terracota-cyan/70 ml-1">(${filteredCount} de ${totalGroupCount} categorias para produto ${isLiquid ? 'líquido' : 'sólido'})</span>`
            : `<span class="text-[9px] text-terracota-textMuted ml-1">(${filteredCount} categorias)</span>`;
        portionGroupHtml = `
            <div>
                <label class="${labelClass}">Grupo de Alimento (Anexo V) ${filterBadge}</label>
                <select id="input-group-code" class="${inputClass} appearance-none cursor-pointer">
                    <option value="" class="bg-terracota-deepDark">— Selecione (opcional) —</option>
                    ${options}
                </select>
                <p class="text-[10px] text-terracota-textMuted mt-1"><i class="ph ph-info text-xs mr-0.5"></i>Grupos filtrados conforme tipo de produto. A porção de referência valida conformidade com Anexo V.</p>
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
                    <div id="portion-feedback" class="mt-1"></div>
                </div>
                <div>
                    <label class="${labelClass}">Medida Caseira</label>
                    <input type="text" id="input-desc" value="${escapeHtml(state.product.portionDesc)}" class="${inputClass}" placeholder="Ex: 1 fatia">
                </div>
            </div>
            <div id="package-feedback" class="hidden"></div>
            <div>
                <label class="${labelClass}">Peso Líquido da Embalagem (${portionUnitLabel})</label>
                <input type="number" id="input-package-weight" value="${escapeHtml(state.product.packageWeight || '')}" class="${inputClass}" placeholder="Ex: 500" min="0.1" step="0.1">
                <p class="text-[10px] text-terracota-textMuted mt-1">Se preenchido, as porções por embalagem serão calculadas automaticamente</p>
            </div>
            <div>
                <label class="${labelClass}">Porções por Embalagem</label>
                <input type="number" id="input-servings-per-package" value="${escapeHtml(state.product.servingsPerPackage)}" class="${inputClass}" placeholder="Ex: 5" min="1" step="1" ${state.product.packageWeight ? 'readonly' : ''}>
                <p class="text-[10px] text-terracota-textMuted mt-1">Obrigatório conforme RDC 429/2020 Art. 22${state.product.packageWeight ? ' — calculado automaticamente' : ''}</p>
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
            <details class="bg-black/20 border border-white/10 rounded-lg group/tips">
                <summary class="px-4 py-3 cursor-pointer text-[11px] font-bold text-terracota-cyan/80 uppercase tracking-wider flex items-center gap-2 hover:text-terracota-cyan transition-colors">
                    <i class="ph ph-lightbulb text-sm"></i> Dicas Regulatórias
                    <i class="ph ph-caret-down text-xs ml-auto transition-transform group-open/tips:rotate-180"></i>
                </summary>
                <div class="px-4 pb-4 space-y-2 text-[11px] text-terracota-textMuted leading-relaxed">
                    <p><i class="ph ph-scales text-terracota-cyan/60 mr-1"></i><strong class="text-terracota-textLight">Porção:</strong> A porção de referência é definida pelo grupo de alimento (Anexo V, IN 75/2020). A tolerância é de ±30% em relação ao valor de referência.</p>
                    <p><i class="ph ph-warning-diamond text-terracota-cyan/60 mr-1"></i><strong class="text-terracota-textLight">Alérgenos:</strong> A declaração de alérgenos é obrigatória conforme RDC 26/2015. Devem constar no rótulo mesmo em traços.</p>
                    <p><i class="ph ph-spoon text-terracota-cyan/60 mr-1"></i><strong class="text-terracota-textLight">Medida caseira:</strong> Deve descrever a porção em termos domésticos (ex: "1 fatia", "2 colheres de sopa"). Obrigatória conforme RDC 429/2020.</p>
                    <p><i class="ph ph-package text-terracota-cyan/60 mr-1"></i><strong class="text-terracota-textLight">Porções por embalagem:</strong> Obrigatório conforme RDC 429/2020 Art. 22. Se peso líquido for preenchido, o cálculo é automático.</p>
                    <p><i class="ph ph-fire text-terracota-cyan/60 mr-1"></i><strong class="text-terracota-textLight">Energia:</strong> Calculada automaticamente pelo motor: Carb×4 + Prot×4 + Gord×9 + Fibra×2 (Anexo XXII, IN 75/2020).</p>
                </div>
            </details>
        </div>
    `;

    // Event listeners
    document.getElementById('input-name').addEventListener('input', (e) => { state.product.name = e.target.value; _autosave(); });
    document.getElementById('input-portion').addEventListener('input', (e) => {
        state.product.portionSize = e.target.value;
        _recalcServingsFromPackageWeight();
        _refreshPortionFeedback();
        _refreshPackageFeedback();
        _autosave();
    });
    document.getElementById('input-desc').addEventListener('input', (e) => { state.product.portionDesc = e.target.value; _autosave(); });
    document.getElementById('input-servings-per-package').addEventListener('input', (e) => { state.product.servingsPerPackage = e.target.value; _autosave(); });
    document.getElementById('input-package-weight').addEventListener('input', (e) => {
        state.product.packageWeight = e.target.value;
        _recalcServingsFromPackageWeight();
        _refreshPackageFeedback();
        // Update servings field and readonly state without re-rendering (avoids focus loss)
        const servingsInput = document.getElementById('input-servings-per-package');
        if (servingsInput) {
            servingsInput.value = state.product.servingsPerPackage;
            servingsInput.readOnly = !!state.product.packageWeight;
        }
        const servingsHint = servingsInput?.parentElement?.querySelector('p');
        if (servingsHint) {
            servingsHint.textContent = state.product.packageWeight
                ? 'Obrigatório conforme RDC 429/2020 Art. 22 — calculado automaticamente'
                : 'Obrigatório conforme RDC 429/2020 Art. 22';
        }
    });
    document.getElementById('input-custom-allergens')?.addEventListener('input', (e) => { state.product.customAllergens = e.target.value; _autosave(); });

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
            // Auto-fill portion whenever a group is selected (overwrite current values)
            if (e.target.value && state.portionGroups) {
                const group = state.portionGroups.find(g => g.code === e.target.value);
                if (group) {
                    state.product.portionSize = group.portion_g;
                    state.product.portionDesc = group.household_measure;
                    document.getElementById('input-portion').value = group.portion_g;
                    document.getElementById('input-desc').value = group.household_measure;
                    _recalcServingsFromPackageWeight();
                    _refreshPortionFeedback();
                    _refreshPackageFeedback();
                }
            }
        });
    }

    // Food form toggle — reset groupCode and auto-filled portion when switching
    document.getElementById('input-food-form').addEventListener('change', (e) => {
        const prevForm = state.product.foodForm;
        state.product.foodForm = e.target.value;
        state.product.portionUnit = state.product.foodForm === 'liquid' ? 'ml' : 'g';
        if (state.product.groupCode) {
            const validGroups = getFilteredPortionGroups();
            if (!validGroups.find(g => g.code === state.product.groupCode)) {
                state.product.groupCode = '';
                state.product.portionSize = '';
                state.product.portionDesc = '';
            }
        }
        const newFiltered = getFilteredPortionGroups();
        const formLabel = state.product.foodForm === 'liquid' ? 'líquido' : 'sólido';
        showToast(`Categorias filtradas para produto ${formLabel} (${newFiltered.length} disponíveis)`, 'info', 3000);
        renderStep1(container);
    });

    // Group code change — also refresh portion feedback
    const groupCodeEl = document.getElementById('input-group-code');
    if (groupCodeEl) {
        const origHandler = groupCodeEl.onchange;
        groupCodeEl.addEventListener('change', () => {
            setTimeout(_refreshPortionFeedback, 50);
        });
    }

    // Initial feedback render
    _refreshPortionFeedback();
    _refreshPackageFeedback();
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

/** Auto-calculate servingsPerPackage from packageWeight and portionSize */
function _recalcServingsFromPackageWeight() {
    const pkg = parseFloat(state.product.packageWeight);
    const portion = parseFloat(state.product.portionSize);
    if (pkg > 0 && portion > 0) {
        state.product.servingsPerPackage = String(Math.floor(pkg / portion));
    }
}

// ---- TACO Autocomplete ------------------------------------------------------

let _tacoDebounceTimer = null;
let _activeTacoDropdown = null;
let _tacoHighlightIndex = -1;
let _tacoSearching = false;

async function tacoSearch(query) {
    if (!query || query.length < 2) return [];
    try {
        const res = await fetch(`/app/api/taco/search?q=${encodeURIComponent(query)}&limit=8`, { headers: withCsrfHeaders() });
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
    ing._manualKcal = false;
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

// Plausibility ranges per 100g (mirrors backend validators.py)
const _NUTRIENT_RANGES = {
    carbs: 100, proteins: 100, totalFat: 100, saturatedFat: 100,
    transFat: 100, fiber: 100, totalSugars: 100, addedSugars: 100,
    sodium: 100000, energyKcal: 900
};

function getIngredientWarnings(nutri, ing) {
    const warnings = [];
    const sat = parseFloat(nutri.saturatedFat);
    const trans = parseFloat(nutri.transFat);
    const totalFat = parseFloat(nutri.totalFat);
    const carbs = parseFloat(nutri.carbs);
    const proteins = parseFloat(nutri.proteins);
    const fiber = parseFloat(nutri.fiber);
    const addedSugars = parseFloat(nutri.addedSugars);
    const totalSugars = parseFloat(nutri.totalSugars);
    const sodium = parseFloat(nutri.sodium);
    const kcal = parseFloat(nutri.energyKcal);

    // --- Relationship checks ---

    if (!isNaN(sat) && !isNaN(trans) && !isNaN(totalFat) && totalFat > 0) {
        if (sat + trans > totalFat) {
            warnings.push({ fields: ['saturatedFat', 'transFat', 'totalFat'], msg: 'Sat + Trans excede Gorduras Totais' });
        }
    }
    if (!isNaN(addedSugars) && !isNaN(totalSugars) && addedSugars > totalSugars) {
        warnings.push({ fields: ['addedSugars', 'totalSugars'], msg: 'Açúcares Adic. excede Açúcares Totais' });
    }
    if (!isNaN(totalSugars) && !isNaN(carbs) && totalSugars > carbs && carbs > 0) {
        warnings.push({ fields: ['totalSugars', 'carbs'], msg: 'Açúcares Totais excede Carboidratos' });
    }

    // --- Macro sum plausibility (per 100g) ---

    const macroSum = (isNaN(carbs) ? 0 : carbs)
                   + (isNaN(proteins) ? 0 : proteins)
                   + (isNaN(totalFat) ? 0 : totalFat)
                   + (isNaN(fiber) ? 0 : fiber);
    if (macroSum > 105) {
        warnings.push({ fields: ['carbs', 'proteins', 'totalFat', 'fiber'], msg: `Soma dos macros (${macroSum.toFixed(1)}g) excede 100g/100g` });
    }

    // --- Individual range warnings ---

    for (const [field, max] of Object.entries(_NUTRIENT_RANGES)) {
        const v = parseFloat(nutri[field]);
        if (!isNaN(v) && v > max) {
            const unit = field === 'sodium' ? 'mg' : (field === 'energyKcal' ? 'kcal' : 'g');
            warnings.push({ fields: [field], msg: `${field === 'energyKcal' ? 'Kcal' : field} (${v}) acima do máximo esperado (${max}${unit})` });
        }
    }

    // --- Energy vs macro divergence ---

    if (ing && ing._manualKcal && !isNaN(kcal) && kcal > 0) {
        const estimated = estimateKcal(nutri);
        if (estimated !== null && estimated > 0) {
            const diff = Math.abs(kcal - estimated) / estimated;
            if (diff > 0.20) {
                warnings.push({ fields: ['energyKcal'], msg: `Kcal informado (${kcal}) diverge >20% do estimado (${estimated} kcal)` });
            }
        }
    }

    // --- Trans fat insignificance hint (Anexo IV) ---

    if (!isNaN(sat) && !isNaN(trans) && sat >= 0 && trans >= 0 && (sat + trans) > 0 && sat <= 0.2 && trans <= 0.2 && (sat + trans) <= 0.2) {
        warnings.push({ fields: [], msg: 'Sat + Trans ≤ 0,2g — serão declarados como 0 (Anexo IV)', type: 'info' });
    }

    return warnings;
}

// ---- Running Totals ---------------------------------------------------------

function computeRunningTotals() {
    let totalWeight = 0;
    const sums = { energyKcal: 0, carbs: 0, proteins: 0, totalFat: 0, saturatedFat: 0, transFat: 0, fiber: 0, sodium: 0, totalSugars: 0, addedSugars: 0 };
    for (const ing of state.ingredients) {
        const qty = parseFloat(ing.quantity) || 0;
        if (qty <= 0) continue;
        totalWeight += qty;
        const n = ing.nutritionalInfo || {};
        const f = qty / 100;
        const kcalVal = ing._manualKcal ? (parseFloat(n.energyKcal) || 0) : (estimateKcal(n) || parseFloat(n.energyKcal) || 0);
        sums.energyKcal += kcalVal * f;
        sums.carbs += (parseFloat(n.carbs) || 0) * f;
        sums.proteins += (parseFloat(n.proteins) || 0) * f;
        sums.totalFat += (parseFloat(n.totalFat) || 0) * f;
        sums.saturatedFat += (parseFloat(n.saturatedFat) || 0) * f;
        sums.transFat += (parseFloat(n.transFat) || 0) * f;
        sums.fiber += (parseFloat(n.fiber) || 0) * f;
        sums.sodium += (parseFloat(n.sodium) || 0) * f;
        sums.totalSugars += (parseFloat(n.totalSugars) || 0) * f;
        sums.addedSugars += (parseFloat(n.addedSugars) || 0) * f;
    }
    if (totalWeight <= 0) return null;
    const per100 = {};
    for (const k of Object.keys(sums)) {
        per100[k] = (sums[k] / totalWeight) * 100;
    }
    return { totalWeight, count: state.ingredients.length, per100 };
}

// Anexo IV significance thresholds (per portion)
const _SIGNIF_THRESHOLDS = {
    energyKcal: 4, carbs: 0.5, proteins: 0.5, totalFat: 0.5,
    saturatedFat: 0.2, transFat: 0.2, fiber: 0.5, sodium: 5,
    totalSugars: 0.5, addedSugars: 0.5
};

function _isInsignificant(nutrient, perPortionValue) {
    const threshold = _SIGNIF_THRESHOLDS[nutrient];
    return threshold !== undefined && perPortionValue <= threshold;
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

    // Compute per-portion values for significance check
    const portionSize = parseFloat(state.product.portionSize) || 0;
    const perPortion = {};
    const insig = {};
    if (portionSize > 0 && totals.totalWeight > 0) {
        for (const k of Object.keys(p)) {
            perPortion[k] = (p[k] * portionSize) / 100;
            insig[k] = _isInsignificant(k, perPortion[k]);
        }
    }

    const hasInsig = Object.values(insig).some(v => v);

    // Helper: style nutrient cell — strikethrough + dimmed if insignificant
    const nutCell = (label, value, key, decPlaces = 1, unitStr = 'g') => {
        const isZero = insig[key];
        const valClass = isZero ? 'text-white/40 line-through decoration-yellow-500/60' : 'text-white';
        const labelExtra = isZero ? ' title="Será declarado como 0 ou não significativo (Anexo IV)"' : '';
        const badge = isZero ? '<span class="text-[8px] text-yellow-500/80 font-normal ml-0.5">~0</span>' : '';
        return `<div${labelExtra}>
            <div class="text-[10px] text-terracota-textMuted uppercase">${label}</div>
            <div class="text-sm font-bold ${valClass}">${fmt(value, decPlaces)}${unitStr}${badge}</div>
        </div>`;
    };

    // Macro distribution %
    const totalMacroKcal = (p.carbs * 4) + (p.proteins * 4) + (p.totalFat * 9);
    const carbPct = totalMacroKcal > 0 ? Math.round((p.carbs * 4 / totalMacroKcal) * 100) : 0;
    const protPct = totalMacroKcal > 0 ? Math.round((p.proteins * 4 / totalMacroKcal) * 100) : 0;
    const fatPct = totalMacroKcal > 0 ? Math.round((p.totalFat * 9 / totalMacroKcal) * 100) : 0;

    const insigNote = hasInsig
        ? `<div class="text-[10px] text-yellow-500/70 mt-2 flex items-center gap-1"><i class="ph ph-info text-xs"></i>Nutrientes riscados serão declarados como 0 ou não significativo (Anexo IV)</div>`
        : '';
    const portionNote = portionSize > 0
        ? `<span class="text-[10px] text-terracota-textMuted ml-2">· porção: ${portionSize}${unit}</span>`
        : '';

    el.innerHTML = `
        <div class="bg-black/30 border border-white/[0.12] rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
                <span class="text-[10px] font-bold text-terracota-cyan uppercase tracking-wider"><i class="ph ph-chart-bar text-xs mr-1"></i>Resumo da Receita</span>
                <span class="text-xs text-terracota-textMuted">${totals.count} ingrediente${totals.count > 1 ? 's' : ''} · ${fmt(totals.totalWeight, 0)}${unit} total${portionNote}</span>
            </div>
            <div class="grid grid-cols-5 sm:grid-cols-10 gap-2 text-center mb-3">
                ${nutCell('Kcal', p.energyKcal, 'energyKcal', 0, '')}
                ${nutCell('Carb', p.carbs, 'carbs', 1, 'g')}
                ${nutCell('Prot', p.proteins, 'proteins', 1, 'g')}
                ${nutCell('Gord', p.totalFat, 'totalFat', 1, 'g')}
                ${nutCell('Sat', p.saturatedFat, 'saturatedFat', 1, 'g')}
                ${nutCell('Trans', p.transFat, 'transFat', 1, 'g')}
                ${nutCell('Fibra', p.fiber, 'fiber', 1, 'g')}
                ${nutCell('Sódio', p.sodium, 'sodium', 0, 'mg')}
                ${nutCell('Aç Tot', p.totalSugars, 'totalSugars', 1, 'g')}
                ${nutCell('Aç Adic', p.addedSugars, 'addedSugars', 1, 'g')}
            </div>
            <div class="flex items-center gap-2 text-[10px]">
                <span class="text-terracota-textMuted">Macro:</span>
                <div class="flex-1 h-2.5 rounded-full overflow-hidden bg-white/5 flex">
                    <div style="width: ${carbPct}%" class="bg-blue-400 transition-all" title="Carb ${carbPct}%"></div>
                    <div style="width: ${protPct}%" class="bg-emerald-400 transition-all" title="Prot ${protPct}%"></div>
                    <div style="width: ${fatPct}%" class="bg-orange-400 transition-all" title="Gord ${fatPct}%"></div>
                </div>
                <span class="text-blue-400">${carbPct}%C</span>
                <span class="text-emerald-400">${protPct}%P</span>
                <span class="text-orange-400">${fatPct}%G</span>
            </div>
            <div class="text-[10px] text-terracota-textMuted mt-2 text-right">valores por 100${unit} da receita</div>
            ${insigNote}
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
                <i class="ph ph-magnifying-glass text-2xl"></i>
            </div>
            <p class="text-terracota-textLight text-sm mb-1">Comece adicionando ingredientes</p>
            <p class="text-terracota-textMuted text-xs mb-5">Busque na Tabela TACO ou insira manualmente</p>
            <div class="flex justify-center gap-3">
                <button onclick="addIngredientWithFocus()" class="px-5 py-2.5 bg-terracota-cyan/20 border border-terracota-cyan/40 text-terracota-cyan text-xs font-bold uppercase tracking-wider rounded-lg hover:bg-terracota-cyan/30 transition-all">
                    <span class="inline-flex items-center gap-1.5"><i class="ph ph-magnifying-glass text-base"></i> Buscar na TACO</span>
                </button>
                <button onclick="addIngredient()" class="px-5 py-2.5 bg-white/10 border border-white/20 text-white text-xs font-bold uppercase tracking-wider rounded-lg hover:bg-white/20 transition-all">
                    <span class="inline-flex items-center gap-1.5"><i class="ph ph-plus text-base"></i> Adicionar Manual</span>
                </button>
            </div>
        </div>` : '';

    const bulkToolbarHtml = hasIngredients ? `
            <div class="flex items-center gap-3 text-xs bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2">
                <span class="text-terracota-textMuted">${state.ingredients.length} ingrediente${state.ingredients.length > 1 ? 's' : ''}</span>
                <span class="text-white/10">|</span>
                <button onclick="fillZeroNutrients()" class="text-terracota-textMuted hover:text-white transition-colors flex items-center gap-1" title="Preencher campos vazios com 0"><i class="ph ph-cursor-text text-sm"></i> Preencher zeros</button>
                <button onclick="confirmClearAllIngredients()" class="text-red-400/70 hover:text-red-400 transition-colors flex items-center gap-1" title="Remover todos os ingredientes"><i class="ph ph-trash text-sm"></i> Limpar tudo</button>
                ${state.ingredients.length > 5 ? `<span class="text-white/10">|</span>
                <div class="relative flex-1 max-w-[200px]">
                    <i class="ph ph-magnifying-glass text-sm absolute left-2 top-1/2 -translate-y-1/2 text-terracota-textMuted pointer-events-none"></i>
                    <input type="text" id="ing-search" class="w-full text-xs bg-black/30 border border-white/10 rounded pl-7 pr-2 py-1 text-white placeholder:text-terracota-textMuted/50 focus:ring-1 focus:ring-terracota-cyan focus:border-terracota-cyan" placeholder="Filtrar ingredientes..." oninput="filterIngredients(this.value)">
                </div>` : ''}
            </div>` : '';

    container.innerHTML = `
        <div class="space-y-5">
            <div class="flex justify-between items-center">
                <h3 class="text-2xl font-bold text-white font-heading">Ingredientes</h3>
                ${hasIngredients ? `<div class="flex items-center gap-2">
                    <button onclick="toggleAllIngredients(false)" class="text-[10px] text-terracota-textMuted hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors" title="Colapsar todos"><i class="ph ph-arrows-in text-sm"></i></button>
                    <button onclick="toggleAllIngredients(true)" class="text-[10px] text-terracota-textMuted hover:text-white px-2 py-1 rounded hover:bg-white/10 transition-colors" title="Expandir todos"><i class="ph ph-arrows-out text-sm"></i></button>
                    <button onclick="addIngredient()" class="text-xs font-bold uppercase tracking-wider px-4 py-2 bg-white/10 text-terracota-cyan rounded-full hover:bg-terracota-cyan hover:text-terracota-deepDark transition-colors inline-flex items-center gap-1.5"><i class="ph ph-plus text-sm"></i> Adicionar</button>
                </div>` : ''}
            </div>
            ${bulkToolbarHtml}
            <div id="drop-zone" class="border-2 border-dashed border-white/20 rounded-xl p-6 text-center transition-all bg-white/5 hover:bg-white/10 hover:border-terracota-cyan group relative">
                <input type="file" id="file-upload" class="hidden" accept=".xlsx" onchange="handleExcelUpload(this.files[0])">
                <div class="pointer-events-none flex items-center justify-center gap-4">
                    <i class="ph ph-file-xls text-3xl text-terracota-textLight group-hover:text-terracota-cyan transition-colors flex-shrink-0"></i>
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
    setupIngredientDragAndDrop();
}

function createIngredientRow(ing, index) {
    const inputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1.5";
    const smInputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1";
    const labelClass = "block text-[10px] text-slate-400 mb-0.5 uppercase tracking-wider";
    const nutri = ing.nutritionalInfo || {};
    const unit = state.product.portionUnit || 'g';
    const warnings = getIngredientWarnings(nutri, ing);
    const warnFields = new Set(warnings.flatMap(w => w.fields));
    const hasTaco = !!ing._tacoId;
    const estimated = estimateKcal(nutri);
    const isManualKcal = ing._manualKcal === true;
    const kcalDisplay = isManualKcal ? nutri.energyKcal : (estimated ?? nutri.energyKcal ?? '');
    const kcalIsAuto = !isManualKcal && estimated !== null;
    const isExpanded = ing._expanded !== false; // default expanded for new rows

    const warnClass = (field) => warnFields.has(field) ? 'border-yellow-500/60 bg-yellow-500/5' : '';

    // Summary line for collapsed state
    const kcalSummary = kcalDisplay !== '' ? `${kcalDisplay} kcal` : '—';

    const el = document.createElement('div');
    el.className = 'ing-row bg-white/[0.08] border border-white/[0.15] rounded-xl p-4 relative group hover:bg-white/[0.12] transition-colors';
    el.setAttribute('data-ing-index', index);
    el.setAttribute('draggable', 'true');

    el.innerHTML = `
        <div class="flex gap-3 items-start mb-1">
            <div class="drag-handle flex-shrink-0 mt-2 text-white/30 hover:text-terracota-cyan cursor-grab" title="Arrastar para reordenar">
                <i class="ph ph-dots-six-vertical text-lg"></i>
            </div>
            <div class="flex-1 relative">
                <label class="${labelClass}">Nome do Ingrediente ${hasTaco ? '<span class="text-[10px] px-1.5 py-0.5 bg-emerald-500/20 text-emerald-300 rounded ml-1">TACO</span>' : ''}</label>
                <input type="text" class="${inputClass} ingredient-name-input" value="${escapeHtml(ing.name)}" data-index="${index}" placeholder="Digite para buscar na TACO..." autocomplete="off">
            </div>
            <div class="w-24 flex-shrink-0">
                <label class="${labelClass}">Qtd (${unit})</label>
                <input type="number" class="${inputClass}" value="${escapeHtml(ing.quantity)}" oninput="updateIngredient(${index}, 'quantity', this.value); renderRunningTotals();" placeholder="100" min="0" step="0.1">
            </div>
            <div class="flex-shrink-0 flex items-center gap-2 mt-5">
                <span class="text-xs text-terracota-textMuted whitespace-nowrap">${kcalSummary}</span>
                <button class="ing-collapse-toggle p-1 rounded hover:bg-white/10 transition-colors" title="Expandir/Colapsar nutrientes" onclick="toggleIngredientExpand(${index})">
                    <i class="ph ph-caret-down text-sm ing-chevron ${isExpanded ? 'rotated' : ''}"></i>
                </button>
            </div>
        </div>
        <div class="ing-nutri-panel ${isExpanded ? 'expanded' : ''}">
            <div class="ing-nutri-inner">
                <div class="bg-black/30 p-3 rounded-lg border border-white/[0.08] mt-2">
                    <div class="text-[10px] font-bold text-terracota-cyan uppercase tracking-wider mb-2">Nutricional (por 100${unit})</div>
                    <div class="grid grid-cols-3 sm:grid-cols-5 gap-x-2 gap-y-1.5">
                        <div class="relative">
                            <label class="${labelClass}">Kcal ${kcalIsAuto ? '<span class="text-[10px] text-terracota-cyan/80">auto</span>' : ''}</label>
                            <input type="number" class="${smInputClass} ${kcalIsAuto ? 'text-terracota-cyan' : ''}" value="${kcalDisplay}" oninput="updateIngredientNutri(${index}, 'energyKcal', this.value)" title="Auto-calculado: Carb×4 + Prot×4 + Gord×9 + Fibra×2. Edite para sobrescrever." min="0" step="0.1">
                        </div>
                        <div>
                            <label class="${labelClass}">Carb (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('carbs')}" value="${nutri.carbs ?? ''}" oninput="updateIngredientNutri(${index}, 'carbs', this.value)" title="Carboidratos totais por 100${unit}. Inclui açúcares e amidos." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">Prot (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('proteins')}" value="${nutri.proteins ?? ''}" oninput="updateIngredientNutri(${index}, 'proteins', this.value)" title="Proteínas por 100${unit} do ingrediente." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">Gord Tot (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('totalFat')}" value="${nutri.totalFat ?? ''}" oninput="updateIngredientNutri(${index}, 'totalFat', this.value)" title="Gorduras totais por 100${unit}. Deve ser ≥ saturada + trans." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">Fibra (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('fiber')}" value="${nutri.fiber ?? ''}" oninput="updateIngredientNutri(${index}, 'fiber', this.value)" title="Fibra alimentar por 100${unit}. Contribui 2 kcal/g." min="0" step="0.01">
                        </div>
                    </div>
                    <div class="grid grid-cols-3 sm:grid-cols-5 gap-x-2 gap-y-1.5 mt-2 pt-2 border-t border-white/[0.08]">
                        <div>
                            <label class="${labelClass} text-slate-400">↳ Sat (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('saturatedFat')}" value="${nutri.saturatedFat ?? ''}" oninput="updateIngredientNutri(${index}, 'saturatedFat', this.value)" title="Gordura saturada por 100${unit}. Deve ser ≤ gordura total." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass} text-slate-400">↳ Trans (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('transFat')}" value="${nutri.transFat ?? ''}" oninput="updateIngredientNutri(${index}, 'transFat', this.value)" title="Gordura trans por 100${unit}. Declarado 0 se sat+trans ≤ 0,2g (Anexo IV)." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass} text-slate-400">↳ Aç Tot (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('totalSugars')}" value="${nutri.totalSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'totalSugars', this.value)" title="Açúcares totais por 100${unit}. Deve ser ≤ carboidratos." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass} text-slate-400">↳ Aç Adic (g)</label>
                            <input type="number" class="${smInputClass} ${warnClass('addedSugars')}" value="${nutri.addedSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'addedSugars', this.value)" title="Açúcares adicionados por 100${unit}. Deve ser ≤ açúcares totais." min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">Sódio (mg)</label>
                            <input type="number" class="${smInputClass} ${warnClass('sodium')}" value="${nutri.sodium ?? ''}" oninput="updateIngredientNutri(${index}, 'sodium', this.value)" title="Sódio em miligramas (mg) por 100${unit}." min="0" step="0.01">
                        </div>
                    </div>
                    <div class="ing-warnings">${warnings.length > 0 ? warnings.map(w => {
                        const isInfo = w.type === 'info';
                        const colorClass = isInfo ? 'text-terracota-cyan/80' : 'text-yellow-400';
                        const icon = isInfo ? 'ph-info' : 'ph-warning';
                        return `<p class="text-[11px] ${colorClass} flex items-center gap-1 mt-1"><i class="ph ${icon} text-xs flex-shrink-0"></i>${escapeHtml(w.msg)}</p>`;
                    }).join('') : ''}</div>
                </div>
            </div>
        </div>
        <div class="absolute -top-2 -right-2 flex gap-1 opacity-70 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
            <button onclick="copyIngredient(${index})" class="bg-terracota-cyan/80 text-terracota-deepDark rounded-full p-1.5 shadow-lg hover:bg-terracota-cyan" title="Duplicar ingrediente">
                <i class="ph ph-copy text-sm"></i>
            </button>
            <button onclick="removeIngredient(${index})" class="bg-red-500/80 text-white rounded-full p-1.5 shadow-lg hover:bg-red-600" title="Remover ingrediente">
                <i class="ph ph-x text-sm"></i>
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
    pushUndo();
    state.ingredients.push({
        id: Date.now(),
        name: '',
        quantity: '',
        _tacoId: null,
        _manualKcal: false,
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
    pushUndo();
    const copy = JSON.parse(JSON.stringify(original));
    copy.id = Date.now();
    copy.name = copy.name ? copy.name + ' (cópia)' : '';
    copy._tacoId = original._tacoId || null;
    copy._manualKcal = original._manualKcal || false;
    state.ingredients.splice(index + 1, 0, copy);
    renderStep2(document.getElementById('wizard-content'));
    showToast('Ingrediente duplicado.', 'info', 2000);
}

function removeIngredient(index) {
    pushUndo();
    state.ingredients.splice(index, 1);
    renderStep2(document.getElementById('wizard-content'));
}

function toggleIngredientExpand(index) {
    const ing = state.ingredients[index];
    if (!ing) return;
    ing._expanded = ing._expanded === false ? true : false;
    const row = document.querySelector(`[data-ing-index="${index}"]`);
    if (!row) return;
    const panel = row.querySelector('.ing-nutri-panel');
    const chevron = row.querySelector('.ing-chevron');
    if (panel) panel.classList.toggle('expanded');
    if (chevron) chevron.classList.toggle('rotated');
}

function toggleAllIngredients(expand) {
    state.ingredients.forEach((ing, idx) => {
        ing._expanded = expand;
    });
    document.querySelectorAll('.ing-nutri-panel').forEach(p => {
        p.classList.toggle('expanded', expand);
    });
    document.querySelectorAll('.ing-chevron').forEach(c => {
        c.classList.toggle('rotated', expand);
    });
}

function fillZeroNutrients() {
    pushUndo();
    const fields = ['energyKcal','carbs','proteins','totalFat','saturatedFat','transFat','fiber','sodium','totalSugars','addedSugars'];
    let filled = 0;
    state.ingredients.forEach(ing => {
        const n = ing.nutritionalInfo;
        fields.forEach(f => {
            if (n[f] === '' || n[f] === null || n[f] === undefined) {
                n[f] = 0;
                filled++;
            }
        });
    });
    if (filled > 0) {
        renderStep2(document.getElementById('wizard-content'));
        showToast(`${filled} campo${filled > 1 ? 's' : ''} preenchido${filled > 1 ? 's' : ''} com 0`, 'success');
    } else {
        showToast('Todos os campos já estão preenchidos', 'info');
    }
}

function confirmClearAllIngredients() {
    if (state.ingredients.length === 0) return;
    const count = state.ingredients.length;
    if (confirm(`Remover todos os ${count} ingredientes? Esta ação pode ser desfeita com Ctrl+Z.`)) {
        pushUndo();
        state.ingredients = [];
        renderStep2(document.getElementById('wizard-content'));
        showToast(`${count} ingrediente${count > 1 ? 's' : ''} removido${count > 1 ? 's' : ''}`, 'info');
    }
}

function filterIngredients(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.ing-row').forEach(row => {
        const idx = parseInt(row.getAttribute('data-ing-index'));
        const name = (state.ingredients[idx]?.name || '').toLowerCase();
        row.style.display = (!q || name.includes(q)) ? '' : 'none';
    });
}

function updateIngredient(index, field, value) {
    state.ingredients[index][field] = value;
    _autosave();
}

const _MACRO_FIELDS = new Set(['carbs', 'proteins', 'totalFat', 'fiber']);

function updateIngredientNutri(index, field, value) {
    const v = parseFloat(value);
    state.ingredients[index].nutritionalInfo[field] = isNaN(v) ? '' : v;

    if (field === 'energyKcal') {
        state.ingredients[index]._manualKcal = true;
    } else if (_MACRO_FIELDS.has(field)) {
        state.ingredients[index]._manualKcal = false;
    }

    _refreshIngredientFeedback(index);
    _autosave();
}

function _refreshIngredientFeedback(index) {
    const row = document.querySelector(`[data-ing-index="${index}"]`);
    if (!row) return;
    const ing = state.ingredients[index];
    const nutri = ing.nutritionalInfo;

    // Auto kcal — recalculate from macros unless user explicitly typed kcal
    const estimated = estimateKcal(nutri);
    const isManual = ing._manualKcal === true;
    const kcalInput = row.querySelector('input[oninput*="energyKcal"]');
    if (kcalInput && !isManual && estimated !== null) {
        kcalInput.value = estimated;
        nutri.energyKcal = estimated;
        kcalInput.classList.add('text-terracota-cyan');
    } else if (kcalInput && !isManual && estimated === null) {
        kcalInput.classList.add('text-terracota-cyan');
    } else if (kcalInput && isManual) {
        kcalInput.classList.remove('text-terracota-cyan');
    }

    // Update collapsed summary kcal
    const summarySpan = row.querySelector('.text-terracota-textMuted.whitespace-nowrap');
    if (summarySpan) {
        const displayVal = isManual ? nutri.energyKcal : (estimated ?? nutri.energyKcal);
        summarySpan.textContent = (displayVal !== '' && displayVal !== null && displayVal !== undefined) ? `${displayVal} kcal` : '—';
    }

    // Inline warnings
    const warnings = getIngredientWarnings(nutri, ing);
    const warnContainer = row.querySelector('.ing-warnings');
    const warnFields = new Set(warnings.flatMap(w => w.fields));
    const allHighlightFields = ['saturatedFat', 'transFat', 'totalFat', 'addedSugars', 'totalSugars', 'carbs', 'proteins', 'fiber', 'sodium', 'energyKcal'];
    for (const f of allHighlightFields) {
        const input = row.querySelector(`input[oninput*="'${f}'"]`);
        if (!input) continue;
        input.classList.toggle('border-yellow-500/60', warnFields.has(f));
        input.classList.toggle('bg-yellow-500/5', warnFields.has(f));
    }

    if (warnContainer) {
        if (warnings.length > 0) {
            warnContainer.innerHTML = warnings.map(w => {
                const isInfo = w.type === 'info';
                const colorClass = isInfo ? 'text-terracota-cyan/80' : 'text-yellow-400';
                const icon = isInfo ? 'ph-info' : 'ph-warning';
                return `<p class="text-[11px] ${colorClass} flex items-center gap-1 mt-1"><i class="ph ${icon} text-xs flex-shrink-0"></i>${escapeHtml(w.msg)}</p>`;
            }).join('');
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
        // Collect non-blocking recommendations
        const hints = [];
        if (!state.product.portionDesc?.trim()) {
            hints.push('medida caseira não informada');
        }
        if ((!state.product.allergenKeys || state.product.allergenKeys.length === 0) && !state.product.allergens?.trim() && !state.product.customAllergens?.trim()) {
            hints.push('declaração de alérgenos vazia (RDC 26/2015)');
        }
        if (!state.product.groupCode) {
            hints.push('grupo de alimento não selecionado');
        }
        if (!state.product.servingsPerPackage) {
            hints.push('porções por embalagem não informada (RDC 429/2020)');
        }
        if (hints.length > 0) {
            showToast(`Recomendações: ${hints.join('; ')}.`, 'info', 5000);
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
    btn.innerHTML = '<i class="ph ph-circle-notch animate-spin text-lg mr-2"></i> Calculando...';
    btn.disabled = true;

    // Show skeleton loading in content area
    const content = document.getElementById('wizard-content');
    const prevContent = content.innerHTML;
    content.innerHTML = `
        <div class="space-y-4 py-8 max-w-xl mx-auto">
            <div class="skeleton h-8 w-48 mx-auto"></div>
            <div class="skeleton h-4 w-32 mx-auto mt-2"></div>
            <div class="skeleton h-64 w-full mt-6"></div>
            <div class="flex justify-center gap-4 mt-6">
                <div class="skeleton h-12 w-36"></div>
                <div class="skeleton h-12 w-36"></div>
            </div>
        </div>
    `;

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
        const res = await fetch('/app/api/calculate', {
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
        // Attach backend metadata to calculatedData for Step 3 rendering
        if (data.calculationWarnings) {
            state.calculatedData.calculationWarnings = data.calculationWarnings;
        }
        if (data.significanceInfo) {
            state.calculatedData.significanceInfo = data.significanceInfo;
        }
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

function _buildComplianceChecklist() {
    const product = state.product;
    const checks = [];

    checks.push({ ok: !!product.name?.trim(), label: 'Nome do produto informado' });
    checks.push({ ok: !!product.portionDesc?.trim(), label: 'Medida caseira informada' });

    const hasAllergens = (product.allergenKeys?.length > 0) || !!product.allergens?.trim() || !!product.customAllergens?.trim();
    checks.push({ ok: hasAllergens, label: 'Declaração de alérgenos' });

    checks.push({ ok: !!product.groupCode, label: 'Grupo de alimento selecionado' });

    // Portion within reference range
    let portionOk = false;
    if (product.groupCode && state.portionGroups) {
        const group = state.portionGroups.find(g => g.code === product.groupCode);
        if (group) {
            const ref = parseFloat(group.portion_g);
            const portion = parseFloat(product.portionSize) || 0;
            portionOk = portion >= ref * 0.7 && portion <= ref * 1.3;
        }
    }
    checks.push({ ok: portionOk, label: 'Porção dentro da referência (Anexo V)' });

    // Ingredient warnings
    let hasIngWarnings = false;
    for (const ing of state.ingredients) {
        const w = getIngredientWarnings(ing.nutritionalInfo || {}, ing);
        if (w.some(x => x.type !== 'info')) { hasIngWarnings = true; break; }
    }
    checks.push({ ok: !hasIngWarnings, label: 'Nenhum aviso de consistência nos ingredientes' });

    // Kcal coherence
    let kcalOk = true;
    for (const ing of state.ingredients) {
        if (ing._manualKcal) {
            const est = estimateKcal(ing.nutritionalInfo || {});
            const manual = parseFloat(ing.nutritionalInfo?.energyKcal) || 0;
            if (est && manual > 0 && Math.abs(manual - est) / est > 0.2) { kcalOk = false; break; }
        }
    }
    checks.push({ ok: kcalOk, label: 'Kcal coerente com macronutrientes' });

    const passCount = checks.filter(c => c.ok).length;
    const allPass = passCount === checks.length;
    const headerColor = allPass ? 'text-emerald-400' : 'text-yellow-400';

    return `
        <div class="mb-6 bg-black/30 border border-white/[0.12] rounded-xl p-4">
            <div class="flex items-center justify-between mb-3">
                <span class="text-[10px] font-bold ${headerColor} uppercase tracking-wider flex items-center gap-1.5">
                    <i class="ph ${allPass ? 'ph-shield-check' : 'ph-shield-warning'} text-sm"></i>
                    Checklist de Conformidade
                </span>
                <span class="text-[10px] text-terracota-textMuted">${passCount}/${checks.length}</span>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                ${checks.map(c => {
                    const icon = c.ok ? 'ph-check-circle' : 'ph-x-circle';
                    const color = c.ok ? 'text-emerald-400' : 'text-red-400/70';
                    return `<div class="flex items-center gap-2 text-[11px] ${color}"><i class="ph ${icon} text-sm flex-shrink-0"></i>${c.label}</div>`;
                }).join('')}
            </div>
        </div>
    `;
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

    const complianceHtml = _buildComplianceChecklist();

    // Calculation warnings from backend
    const calcWarnings = allData.calculationWarnings || [];
    const calcWarnHtml = calcWarnings.length > 0
        ? `<div class="mb-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3">
              <p class="text-[10px] font-bold text-yellow-400 uppercase tracking-wider mb-2 flex items-center gap-1"><i class="ph ph-warning text-sm"></i>Avisos do Motor de Cálculo</p>
              ${calcWarnings.map(w => `<p class="text-[11px] text-yellow-300/80 flex items-center gap-1 mt-1"><i class="ph ph-caret-right text-xs"></i>${escapeHtml(w)}</p>`).join('')}
           </div>`
        : '';

    container.innerHTML = `
        <div class="text-center mb-4">
            <p class="text-sm text-terracota-textMuted">
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300">
                    <i class="ph ph-eye text-base"></i>
                    Prévia — revise antes de gerar
                </span>
            </p>
        </div>
        ${complianceHtml}
        ${calcWarnHtml}
        ${warningHtml}
        ${buildFrontalStampsHtml(allData, product)}
        <div class="flex justify-center gap-2 mb-4 no-print">
            <button onclick="copyTableToClipboard()" class="px-3 py-1.5 text-xs bg-white/10 border border-white/20 text-terracota-textMuted rounded-lg hover:bg-white/20 hover:text-white transition-colors inline-flex items-center gap-1.5" title="Copiar tabela como texto">
                <i class="ph ph-clipboard-text text-sm"></i> Copiar
            </button>
        </div>
        ${buildNutritionTableHtml(allData, product)}
        <div class="flex justify-center gap-4 mt-8 no-print flex-wrap">
            ${canGenerate ? `
            <button id="btn-generate" onclick="finalizeTable()" class="px-10 py-3.5 bg-gradient-to-r from-terracota-purple to-purple-600 text-white font-bold rounded-lg hover:scale-105 shadow-[0_0_25px_rgba(123,44,191,0.4)] transition-all flex items-center gap-2">
                <i class="ph-bold ph-check text-xl"></i>
                Gerar Tabela
            </button>` : ''}
            <button onclick="goToStep(2)" class="px-8 py-3.5 bg-white/10 border border-white/20 text-white font-bold rounded-lg hover:bg-white/20 transition-all flex items-center gap-2">
                <i class="ph ph-pencil-simple text-xl"></i>
                Editar Ingredientes
            </button>
            <button onclick="goToStep(1)" class="px-8 py-3.5 bg-white/10 border border-white/20 text-terracota-textMuted font-bold rounded-lg hover:bg-white/20 hover:text-white transition-all flex items-center gap-2">
                <i class="ph ph-gear text-xl"></i>
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
                <i class="ph-bold ph-check-circle text-xl text-emerald-400"></i>
                <span class="text-emerald-300 text-sm font-semibold">Tabela gerada e salva com sucesso!</span>
            </div>
        </div>
        ${quotaBadgeHtml()}
        ${buildFrontalStampsHtml(allData, product)}
        <div class="flex justify-center gap-2 mb-4 no-print flex-wrap">
            <button onclick="copyTableToClipboard()" class="px-3 py-1.5 text-xs bg-white/10 border border-white/20 text-terracota-textMuted rounded-lg hover:bg-white/20 hover:text-white transition-colors inline-flex items-center gap-1.5" title="Copiar tabela como texto">
                <i class="ph ph-clipboard-text text-sm"></i> Copiar
            </button>
            <button onclick="exportTableAsPng()" class="px-3 py-1.5 text-xs bg-white/10 border border-white/20 text-terracota-textMuted rounded-lg hover:bg-white/20 hover:text-white transition-colors inline-flex items-center gap-1.5" title="Baixar como PNG">
                <i class="ph ph-image text-sm"></i> PNG
            </button>
            <button onclick="openTableComparison()" class="px-3 py-1.5 text-xs bg-white/10 border border-white/20 text-terracota-textMuted rounded-lg hover:bg-white/20 hover:text-white transition-colors inline-flex items-center gap-1.5" title="Comparar com tabela anterior">
                <i class="ph ph-arrows-left-right text-sm"></i> Comparar
            </button>
        </div>
        ${buildNutritionTableHtml(allData, product)}
        <div id="comparison-container"></div>
        <div class="flex justify-center gap-4 mt-8 no-print flex-wrap">
            <button onclick="printTable()" class="px-8 py-3.5 bg-terracota-cyan text-terracota-deepDark font-bold rounded-lg hover:bg-white shadow-[0_0_20px_rgba(0,196,204,0.3)] transition-all flex items-center gap-2">
                <i class="ph-bold ph-printer text-xl"></i>
                Imprimir / PDF
            </button>
            ${canCreateMore ? `
            <button onclick="startNewTable()" class="px-8 py-3.5 bg-terracota-purple text-white font-bold rounded-lg hover:bg-purple-600 shadow-sm transition-all flex items-center gap-2">
                <i class="ph-bold ph-plus text-xl"></i>
                Nova Tabela
            </button>` : `
            <a href="/account/upgrade" class="px-8 py-3.5 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white font-bold rounded-lg hover:scale-105 shadow-[0_0_25px_rgba(123,44,191,0.3)] transition-all flex items-center gap-2 no-underline">
                <i class="ph-bold ph-trend-up text-xl"></i>
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
        <i class="ph ph-circle-notch animate-spin text-lg"></i>
        Gerando...
    `;

    const result = await saveCurrentTable();

    if (result.ok) {
        state.isFinalized = true;
        clearDraft();
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
            <i class="ph-bold ph-arrow-clockwise text-lg"></i>
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
        servingsPerPackage: '',
        packageWeight: '',
    };
    state.ingredients = [];
    state.calculatedData = null;
    state.isFinalized = false;
    state.savedTableId = null;
    state.saveTableError = '';
    state.currentIdempotencyKey = null;
    goToStep(1);
}

// ---- ANVISA Frontal Warning Stamps (RDC 429/2020) ---------------------------
function computeFrontalStamps(per100, foodForm) {
    const stamps = [];
    const isSolid = foodForm !== 'liquid';
    const raw = (key) => parseFloat(per100[key]?.raw) || 0;

    // Thresholds per 100g (solid) or 100ml (liquid)
    if (raw('addedSugars') >= (isSolid ? 15 : 7.5)) {
        stamps.push({ key: 'sugar', label: 'ALTO EM AÇÚCARES ADICIONADOS', icon: 'ph-cube-transparent' });
    }
    if (raw('saturatedFat') >= (isSolid ? 6 : 3)) {
        stamps.push({ key: 'satfat', label: 'ALTO EM GORDURAS SATURADAS', icon: 'ph-drop-half-bottom' });
    }
    if (raw('sodium') >= (isSolid ? 600 : 300)) {
        stamps.push({ key: 'sodium', label: 'ALTO EM SÓDIO', icon: 'ph-salt' });
    }
    return stamps;
}

// ---- Shared Nutrition Table HTML Builder ------------------------------------

function buildFrontalStampsHtml(allData, product) {
    const per100 = allData.per100g || allData.per100_base || {};
    const foodForm = product.foodForm || 'solid';
    const stamps = computeFrontalStamps(per100, foodForm);
    if (stamps.length === 0) return '';
    return `
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1rem;">
            ${stamps.map(s => `
                <div style="display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:8px;background:#fef2f2;border:1px solid #fca5a5;color:#dc2626;font-size:11px;font-weight:700;letter-spacing:0.05em;">
                    <i class="ph ${s.icon}" style="font-size:14px;"></i>
                    ${s.label}
                </div>
            `).join('')}
        </div>`;
}

function buildNutritionTableHtml(allData, product) {
    const per100 = allData.per100g || allData.per100_base || {};
    const portion = allData.perPortion || allData;
    const energyKjPortion = Math.round((portion.energy?.raw ?? 0) * 4.184);
    const energyKjPer100 = Math.round((per100.energy?.raw ?? 0) * 4.184);
    const transVd = portion.transFat?.vd === '' ? '**' : (portion.transFat?.vd ?? '**');
    const totalSugarsVd = portion.totalSugars?.vd === '' ? '**' : (portion.totalSugars?.vd ?? '**');

    const portionSize = product.portionSize || product.portion_size || '';
    const portionDesc = product.portionDesc || product.portion_desc || '';
    const glutenText = product.gluten || product.gluten_status || '';
    const allergensText = product.allergens || '';
    const portionUnit = product.portionUnit || product.portion_unit || 'g';
    const baseLabel = portionUnit === 'ml' ? '100 ml' : '100 g';
    const servingsPerPackage = product.servingsPerPackage || product.servings_per_package || '';

    const row = (label, per100val, portionVal, vdVal, indent = false) => {
        const vd = vdVal === '' ? '**' : (vdVal ?? '**');
        return `
            <tr style="border-bottom: 1px solid #d1d5db;">
                <td style="padding: 0.375rem 0${indent ? ' 0.375rem 1rem' : ''}; color: ${indent ? '#4b5563' : '#000'}; background: #fff;">${label}</td>
                <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${per100val}</td>
                <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portionVal}</td>
                <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff; min-width: 60px;">${vd}</td>
            </tr>`;
    };

    const servingsLine = servingsPerPackage
        ? `<p>Porções por embalagem: <strong>${escapeHtml(String(servingsPerPackage))}</strong></p>`
        : '';

    return `
        <div id="nutritional-table-print-area" style="max-width: 36rem; margin: 0 auto; padding: 2rem; background: #ffffff; color: #000000; border-radius: 0.75rem; border: 1px solid #e5e7eb;">
            <h3 style="font-size: 1.25rem; font-weight: 700; color: #000; border-bottom: 2px solid #000; padding-bottom: 0.5rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.05em;">Informação Nutricional</h3>
            <div style="margin-bottom: 1rem; font-size: 0.875rem; color: #000; font-weight: 500;">
                <p>Porção de: <strong>${escapeHtml(portionSize)} ${portionUnit}</strong> (${escapeHtml(portionDesc || '-')})</p>
                ${servingsLine}
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
                    ${row('Valor Energético', `${per100.energy?.display ?? 0} kcal = ${energyKjPer100} kJ`, `${portion.energy?.display ?? 0} kcal = ${energyKjPortion} kJ`, portion.energy?.vd ?? 0)}
                    ${row('Carboidratos', `${per100.carbs?.display ?? 0} g`, `${portion.carbs?.display ?? 0} g`, portion.carbs?.vd ?? 0)}
                    ${row('Açúcares Totais', `${per100.totalSugars?.display ?? 0} g`, `${portion.totalSugars?.display ?? 0} g`, totalSugarsVd, true)}
                    ${row('Açúcares Adicionados', `${per100.addedSugars?.display ?? 0} g`, `${portion.addedSugars?.display ?? 0} g`, portion.addedSugars?.vd ?? 0, true)}
                    ${row('Proteínas', `${per100.proteins?.display ?? 0} g`, `${portion.proteins?.display ?? 0} g`, portion.proteins?.vd ?? 0)}
                    ${row('Gorduras Totais', `${per100.totalFat?.display ?? 0} g`, `${portion.totalFat?.display ?? 0} g`, portion.totalFat?.vd ?? 0)}
                    ${row('Gorduras Saturadas', `${per100.saturatedFat?.display ?? 0} g`, `${portion.saturatedFat?.display ?? 0} g`, portion.saturatedFat?.vd ?? 0, true)}
                    ${row('Gorduras Trans', `${per100.transFat?.display ?? 0} g`, `${portion.transFat?.display ?? 0} g`, transVd, true)}
                    ${row('Fibra Alimentar', `${per100.fiber?.display ?? 0} g`, `${portion.fiber?.display ?? 0} g`, portion.fiber?.vd ?? 0)}
                    ${row('Sódio', `${per100.sodium?.display ?? 0} mg`, `${portion.sodium?.display ?? 0} mg`, portion.sodium?.vd ?? 0)}
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

        const res = await fetch('/app/api/import-excel', {
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

// ---- Undo/Redo System -------------------------------------------------------

const _undoStack = [];
const _redoStack = [];
const MAX_UNDO = 50;
let _undoDebounce = null;

function _snapshotState() {
    return JSON.stringify({ product: state.product, ingredients: state.ingredients });
}

function pushUndo() {
    clearTimeout(_undoDebounce);
    _undoDebounce = setTimeout(() => {
        const snap = _snapshotState();
        if (_undoStack.length > 0 && _undoStack[_undoStack.length - 1] === snap) return;
        _undoStack.push(snap);
        if (_undoStack.length > MAX_UNDO) _undoStack.shift();
        _redoStack.length = 0;
    }, 500);
}

function undo() {
    if (_undoStack.length === 0) { showToast('Nada para desfazer.', 'info', 1500); return; }
    _redoStack.push(_snapshotState());
    const prev = JSON.parse(_undoStack.pop());
    state.product = prev.product;
    state.ingredients = prev.ingredients;
    if (state.currentStep === 1) renderStep1(document.getElementById('wizard-content'));
    else if (state.currentStep === 2) renderStep2(document.getElementById('wizard-content'));
    showToast('Desfeito.', 'info', 1500);
}

function redo() {
    if (_redoStack.length === 0) { showToast('Nada para refazer.', 'info', 1500); return; }
    _undoStack.push(_snapshotState());
    const next = JSON.parse(_redoStack.pop());
    state.product = next.product;
    state.ingredients = next.ingredients;
    if (state.currentStep === 1) renderStep1(document.getElementById('wizard-content'));
    else if (state.currentStep === 2) renderStep2(document.getElementById('wizard-content'));
    showToast('Refeito.', 'info', 1500);
}

// ---- Autosave Drafts --------------------------------------------------------

const AUTOSAVE_KEY = 'terracota_draft';
let _autosaveTimer = null;

function _autosave() {
    clearTimeout(_autosaveTimer);
    _autosaveTimer = setTimeout(() => {
        if (state.currentStep < 1 || state.isFinalized) return;
        const draft = {
            product: state.product,
            ingredients: state.ingredients,
            currentStep: state.currentStep,
            savedAt: Date.now()
        };
        try {
            localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(draft));
            const indicator = document.getElementById('autosave-indicator');
            if (indicator) {
                indicator.textContent = 'Rascunho salvo';
                indicator.classList.remove('opacity-0');
                setTimeout(() => indicator.classList.add('opacity-0'), 2000);
            }
        } catch (e) { /* localStorage full — ignore */ }
    }, 10000);
}

function _checkDraftOnLoad() {
    try {
        const raw = localStorage.getItem(AUTOSAVE_KEY);
        if (!raw) return false;
        const draft = JSON.parse(raw);
        // Only restore if draft is less than 24h old
        if (Date.now() - draft.savedAt > 86400000) {
            localStorage.removeItem(AUTOSAVE_KEY);
            return false;
        }
        if (!draft.product?.name && (!draft.ingredients || draft.ingredients.length === 0)) {
            localStorage.removeItem(AUTOSAVE_KEY);
            return false;
        }
        // Show restore prompt
        const content = document.getElementById('wizard-content');
        content.innerHTML = `
            <div class="text-center py-12">
                <div class="mb-6 inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-terracota-cyan/10 border border-terracota-cyan/20 text-terracota-cyan">
                    <i class="ph ph-clock-counter-clockwise text-3xl"></i>
                </div>
                <h3 class="text-xl font-bold text-white mb-2 font-heading">Rascunho encontrado</h3>
                <p class="text-terracota-textMuted text-sm mb-1">Produto: <span class="text-white">${escapeHtml(draft.product?.name || 'Sem nome')}</span></p>
                <p class="text-terracota-textMuted text-sm mb-6">${draft.ingredients?.length || 0} ingredientes · Salvo ${_timeAgo(draft.savedAt)}</p>
                <div class="flex justify-center gap-4">
                    <button id="btn-restore-draft" class="px-8 py-3 bg-terracota-cyan text-terracota-deepDark font-bold rounded-lg hover:bg-white transition-all inline-flex items-center gap-2">
                        <i class="ph-bold ph-arrow-counter-clockwise text-lg"></i> Restaurar Rascunho
                    </button>
                    <button id="btn-discard-draft" class="px-8 py-3 bg-white/10 border border-white/20 text-white font-bold rounded-lg hover:bg-white/20 transition-all">
                        Descartar
                    </button>
                </div>
            </div>
        `;
        document.getElementById('btn-restore-draft').addEventListener('click', () => {
            state.product = draft.product;
            state.ingredients = draft.ingredients || [];
            goToStep(draft.currentStep || 1);
            showToast('Rascunho restaurado!', 'success');
        });
        document.getElementById('btn-discard-draft').addEventListener('click', () => {
            localStorage.removeItem(AUTOSAVE_KEY);
            renderWelcome();
        });
        return true;
    } catch (e) { return false; }
}

function _timeAgo(ts) {
    const mins = Math.floor((Date.now() - ts) / 60000);
    if (mins < 1) return 'agora';
    if (mins < 60) return `há ${mins} min`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `há ${hrs}h`;
    return `há ${Math.floor(hrs / 24)}d`;
}

function clearDraft() {
    try { localStorage.removeItem(AUTOSAVE_KEY); } catch (e) { /* ignore */ }
}

// ---- Keyboard Shortcuts -----------------------------------------------------

document.addEventListener('keydown', (e) => {
    // Only active when wizard is loaded
    if (state.currentStep < 0) return;

    const isMod = e.ctrlKey || e.metaKey;

    // Ctrl/Cmd+Enter: advance / calculate
    if (isMod && e.key === 'Enter') {
        e.preventDefault();
        const btnNext = document.getElementById('btn-next');
        if (btnNext && btnNext.style.display !== 'none' && !btnNext.disabled) {
            btnNext.click();
        }
        return;
    }

    // Ctrl/Cmd+Z: Undo
    if (isMod && !e.shiftKey && e.key === 'z') {
        e.preventDefault();
        undo();
        return;
    }

    // Ctrl/Cmd+Shift+Z: Redo
    if (isMod && e.shiftKey && e.key === 'z') {
        e.preventDefault();
        redo();
        return;
    }

    // Ctrl/Cmd+N: Add ingredient (step 2)
    if (isMod && e.key === 'n' && state.currentStep === 2) {
        e.preventDefault();
        addIngredientWithFocus();
        return;
    }

    // Ctrl/Cmd+P: Print (step 3 finalized)
    if (isMod && e.key === 'p' && state.currentStep === 3 && state.isFinalized) {
        e.preventDefault();
        printTable();
        return;
    }

    // Escape: close TACO dropdown
    if (e.key === 'Escape') {
        closeTacoDropdown();
    }
});

// ---- Drag & Drop Ingredient Reorder -----------------------------------------

function setupIngredientDragAndDrop() {
    const list = document.getElementById('ingredients-list');
    if (!list) return;
    let dragIndex = null;

    list.addEventListener('dragstart', (e) => {
        const row = e.target.closest('.ing-row');
        if (!row) return;
        // Only allow drag from handle
        if (!e.target.closest('.drag-handle')) { e.preventDefault(); return; }
        dragIndex = parseInt(row.getAttribute('data-ing-index'));
        row.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });

    list.addEventListener('dragend', (e) => {
        const row = e.target.closest('.ing-row');
        if (row) row.classList.remove('dragging');
        dragIndex = null;
    });

    list.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    });

    list.addEventListener('drop', (e) => {
        e.preventDefault();
        if (dragIndex === null) return;
        const target = e.target.closest('.ing-row');
        if (!target) return;
        const dropIndex = parseInt(target.getAttribute('data-ing-index'));
        if (dropIndex === dragIndex) return;
        // Reorder
        const [moved] = state.ingredients.splice(dragIndex, 1);
        state.ingredients.splice(dropIndex, 0, moved);
        pushUndo();
        renderStep2(document.getElementById('wizard-content'));
    });
}

// ---- Copy Table to Clipboard ------------------------------------------------

function copyTableToClipboard() {
    const el = document.getElementById('nutritional-table-print-area');
    if (!el) return;
    // Extract text content from the table area
    const rows = el.querySelectorAll('tbody tr');
    const lines = ['INFORMAÇÃO NUTRICIONAL', ''];
    const headers = el.querySelectorAll('thead th');
    if (headers.length > 0) {
        lines.push(Array.from(headers).map(h => h.textContent.trim()).join('\t'));
    }
    rows.forEach(r => {
        const cells = r.querySelectorAll('td');
        lines.push(Array.from(cells).map(c => c.textContent.trim()).join('\t'));
    });
    // Add footer notes
    const footerP = el.querySelector('p');
    if (footerP) lines.push('', footerP.textContent.trim());

    navigator.clipboard.writeText(lines.join('\n')).then(() => {
        showToast('Tabela copiada para a área de transferência!', 'success');
    }).catch(() => {
        showToast('Não foi possível copiar. Tente novamente.', 'error');
    });
}

// ---- Export Table as PNG (html2canvas lazy-loaded) ---------------------------

let _html2canvasLoaded = false;

function _loadHtml2Canvas() {
    return new Promise((resolve, reject) => {
        if (_html2canvasLoaded && window.html2canvas) {
            resolve(window.html2canvas);
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
        script.integrity = 'sha384-LpXfKmGiKbEVpenJKPBMIbbzjEAH0LHffMXc3Ij9AU0d7rPkTiM8XW/vNYfEqSa';
        script.crossOrigin = 'anonymous';
        script.onload = () => {
            _html2canvasLoaded = true;
            resolve(window.html2canvas);
        };
        script.onerror = () => reject(new Error('Failed to load html2canvas'));
        document.head.appendChild(script);
    });
}

async function exportTableAsPng() {
    const el = document.getElementById('nutritional-table-print-area');
    if (!el) return;

    showToast('Gerando imagem...', 'info', 2000);
    try {
        const html2canvas = await _loadHtml2Canvas();
        const canvas = await html2canvas(el, {
            scale: 2,
            backgroundColor: '#ffffff',
            useCORS: true,
        });
        const link = document.createElement('a');
        const name = (state.product.name || 'tabela_nutricional').replace(/[^a-zA-Z0-9_-]/g, '_');
        link.download = `${name}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast('PNG baixado com sucesso!', 'success');
    } catch (err) {
        console.error('PNG export failed:', err);
        showToast('Erro ao exportar PNG. Tente novamente.', 'error');
    }
}

// ---- Table Comparison -------------------------------------------------------

async function openTableComparison() {
    const container = document.getElementById('comparison-container');
    if (!container) return;

    // If already open, toggle off
    if (container.innerHTML.trim()) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `
        <div class="mt-6 p-4 bg-white/[0.04] border border-white/[0.1] rounded-xl">
            <div class="text-center py-4">
                <div class="w-6 h-6 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                <p class="text-xs text-terracota-textMuted">Carregando tabelas anteriores...</p>
            </div>
        </div>
    `;

    try {
        const res = await fetch('/app/api/tables', {
            headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
        });
        if (!res.ok) throw new Error('fetch failed');
        const data = await res.json();
        const tables = data.tables || [];

        // Filter out current table
        const others = tables.filter(t => t.id !== state.savedTableId).slice(0, 10);

        if (others.length === 0) {
            container.innerHTML = `
                <div class="mt-6 p-4 bg-white/[0.04] border border-white/[0.1] rounded-xl text-center">
                    <i class="ph ph-info text-xl text-terracota-textMuted mb-2"></i>
                    <p class="text-sm text-terracota-textMuted">Nenhuma tabela anterior encontrada para comparação.</p>
                </div>
            `;
            return;
        }

        const options = others.map(t => `<option value="${t.id}">${escapeHtml(t.product_name || t.name || `Tabela #${t.id}`)}</option>`).join('');
        container.innerHTML = `
            <div class="mt-6 p-4 bg-white/[0.04] border border-white/[0.1] rounded-xl">
                <div class="flex items-center justify-between mb-3">
                    <span class="text-xs font-bold text-terracota-cyan uppercase tracking-wider"><i class="ph ph-arrows-left-right mr-1"></i>Comparar com</span>
                    <button onclick="document.getElementById('comparison-container').innerHTML=''" class="text-terracota-textMuted hover:text-white text-xs"><i class="ph ph-x"></i></button>
                </div>
                <select id="compare-table-select" class="w-full text-sm bg-black/30 border border-white/10 rounded-lg text-white px-3 py-2 mb-3" onchange="loadComparisonTable(this.value)">
                    <option value="">Selecione uma tabela...</option>
                    ${options}
                </select>
                <div id="comparison-result"></div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `
            <div class="mt-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-center">
                <p class="text-sm text-red-300">Erro ao carregar tabelas. Tente novamente.</p>
            </div>
        `;
    }
}

async function loadComparisonTable(tableId) {
    if (!tableId) {
        document.getElementById('comparison-result').innerHTML = '';
        return;
    }

    const resultEl = document.getElementById('comparison-result');
    resultEl.innerHTML = '<div class="text-center py-3"><div class="w-5 h-5 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin mx-auto"></div></div>';

    try {
        const res = await fetch(`/app/api/tables/${encodeURIComponent(tableId)}`, {
            headers: withCsrfHeaders({ 'Content-Type': 'application/json' }),
        });
        if (!res.ok) throw new Error('fetch failed');
        const data = await res.json();

        const otherData = data.calculated_data || data.calculatedData || {};
        const otherPortion = otherData.perPortion || {};
        const currentPortion = (state.calculatedData || {}).perPortion || {};

        const nutrients = [
            { key: 'energy', label: 'Energia', unit: 'kcal' },
            { key: 'carbs', label: 'Carboidratos', unit: 'g' },
            { key: 'proteins', label: 'Proteínas', unit: 'g' },
            { key: 'totalFat', label: 'Gorduras Totais', unit: 'g' },
            { key: 'saturatedFat', label: 'Gord. Saturadas', unit: 'g' },
            { key: 'transFat', label: 'Gord. Trans', unit: 'g' },
            { key: 'fiber', label: 'Fibra', unit: 'g' },
            { key: 'sodium', label: 'Sódio', unit: 'mg' },
            { key: 'totalSugars', label: 'Açúcares Tot.', unit: 'g' },
            { key: 'addedSugars', label: 'Açúcares Adic.', unit: 'g' },
        ];

        const rowsHtml = nutrients.map(n => {
            const curr = parseFloat(currentPortion[n.key]?.raw) || 0;
            const other = parseFloat(otherPortion[n.key]?.raw) || 0;
            const diff = curr - other;
            const diffPct = other > 0 ? ((diff / other) * 100).toFixed(0) : (curr > 0 ? '+∞' : '0');
            const arrow = diff > 0.01 ? '↑' : diff < -0.01 ? '↓' : '=';
            const clr = diff > 0.01 ? 'text-red-400' : diff < -0.01 ? 'text-emerald-400' : 'text-terracota-textMuted';
            return `<tr class="border-b border-white/[0.06]">
                <td class="py-1 text-xs text-terracota-textLight">${n.label}</td>
                <td class="py-1 text-xs text-right font-mono text-white">${currentPortion[n.key]?.display ?? '0'} ${n.unit}</td>
                <td class="py-1 text-xs text-right font-mono text-terracota-textMuted">${otherPortion[n.key]?.display ?? '0'} ${n.unit}</td>
                <td class="py-1 text-xs text-right font-mono ${clr}">${arrow} ${typeof diffPct === 'string' ? diffPct : (diff > 0 ? '+' : '') + diffPct}%</td>
            </tr>`;
        }).join('');

        resultEl.innerHTML = `
            <table class="w-full text-xs">
                <thead>
                    <tr class="border-b border-white/[0.1]">
                        <th class="py-1 text-left text-[10px] text-terracota-textMuted uppercase">Nutriente</th>
                        <th class="py-1 text-right text-[10px] text-terracota-cyan uppercase">Atual</th>
                        <th class="py-1 text-right text-[10px] text-terracota-textMuted uppercase">Anterior</th>
                        <th class="py-1 text-right text-[10px] text-terracota-textMuted uppercase">Δ</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        `;
    } catch (err) {
        resultEl.innerHTML = '<p class="text-xs text-red-300 text-center">Erro ao carregar tabela.</p>';
    }
}
