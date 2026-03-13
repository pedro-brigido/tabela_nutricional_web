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
    portionGroups: null,    // cached from /api/portion-references
    maxStepReached: 0,      // highest step visited (enables fluid back-navigation)
    summaryDockCollapsed: false,
    summaryDockManual: false
};

const INGREDIENT_NUTRIENT_FIELDS = ['energyKcal', 'carbs', 'proteins', 'totalFat', 'saturatedFat', 'transFat', 'fiber', 'sodium', 'totalSugars', 'addedSugars'];

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

function calculatorStartIconSvg(name, className = 'calculator-start-icon') {
    const icons = {
        product: `
            <path d="M9 5.25h6"></path>
            <path d="M9.25 4h5.5a1 1 0 0 1 1 1v.75h1A2.25 2.25 0 0 1 19 8v10A2.25 2.25 0 0 1 16.75 20.25h-9.5A2.25 2.25 0 0 1 5 18V8a2.25 2.25 0 0 1 2.25-2.25h1V5a1 1 0 0 1 1-1Z"></path>
            <path d="M9 10h6"></path>
            <path d="M9 13.5h6"></path>
            <path d="M9 17h4"></path>
        `,
        ingredients: `
            <path d="M5.5 12h13"></path>
            <path d="M7 12c.2 3 2.6 5.25 5.6 5.25h.8c3 0 5.4-2.25 5.6-5.25"></path>
            <path d="M9.2 9.25c.2-1.1.9-2 1.95-2.75"></path>
            <path d="M12.05 8.5c.25-1.5 1.2-2.8 2.55-3.5"></path>
            <path d="M14.85 9.2c.15-.75.55-1.35 1.15-1.9"></path>
        `,
        table: `
            <rect x="4.5" y="5.5" width="15" height="13" rx="2.5"></rect>
            <path d="M4.5 9.5h15"></path>
            <path d="M9.5 9.5v9"></path>
            <path d="M14.5 9.5v9"></path>
        `,
        shield: `
            <path d="M12 4.5 18 7v4.5c0 4.1-2.4 7.05-6 8.5-3.6-1.45-6-4.4-6-8.5V7l6-2.5Z"></path>
            <path d="m9.45 12.15 1.75 1.75 3.55-3.55"></path>
        `,
        tableShield: `
            <rect x="4.5" y="5.5" width="11" height="13" rx="2.5"></rect>
            <path d="M4.5 9.5h11"></path>
            <path d="M9 9.5v9"></path>
            <path d="M15.5 12.8c0-.85.48-1.42 1.25-1.73L18 10.5l1.25.57c.77.31 1.25.88 1.25 1.73v1.08c0 1.65-.95 2.77-2.5 3.54-1.55-.77-2.5-1.89-2.5-3.54Z"></path>
            <path d="m17.35 14.1.65.65 1.35-1.35"></path>
        `,
        calculator: `
            <rect x="5.5" y="4.5" width="13" height="15" rx="2.5"></rect>
            <path d="M8.5 8.25h7"></path>
            <circle cx="9" cy="12" r=".45" fill="currentColor" stroke="none"></circle>
            <circle cx="12" cy="12" r=".45" fill="currentColor" stroke="none"></circle>
            <circle cx="15" cy="12" r=".45" fill="currentColor" stroke="none"></circle>
            <circle cx="9" cy="15" r=".45" fill="currentColor" stroke="none"></circle>
            <circle cx="12" cy="15" r=".45" fill="currentColor" stroke="none"></circle>
            <circle cx="15" cy="15" r=".45" fill="currentColor" stroke="none"></circle>
        `,
        calculatorShield: `
            <rect x="4.25" y="4.5" width="10.5" height="15" rx="2.5"></rect>
            <path d="M7.4 8.3h4.2"></path>
            <circle cx="8" cy="12.1" r=".42" fill="currentColor" stroke="none"></circle>
            <circle cx="10" cy="12.1" r=".42" fill="currentColor" stroke="none"></circle>
            <circle cx="12" cy="12.1" r=".42" fill="currentColor" stroke="none"></circle>
            <circle cx="8" cy="14.9" r=".42" fill="currentColor" stroke="none"></circle>
            <circle cx="10" cy="14.9" r=".42" fill="currentColor" stroke="none"></circle>
            <circle cx="12" cy="14.9" r=".42" fill="currentColor" stroke="none"></circle>
            <path d="M15.6 13.1c0-.88.49-1.49 1.28-1.82l1.22-.58 1.22.58c.79.33 1.29.94 1.29 1.82v1.08c0 1.66-.95 2.8-2.51 3.58-1.56-.78-2.5-1.92-2.5-3.58Z"></path>
            <path d="m17.45 14.35.65.65 1.35-1.35"></path>
        `,
        clock: `
            <circle cx="12" cy="12" r="7.5"></circle>
            <path d="M12 8.5v4l2.5 1.5"></path>
        `
    };

    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="${className}" aria-hidden="true">${icons[name] || icons.product}</svg>`;
}

function calculatorStartFeaturePill(iconName, label, extraClass = '') {
    return `<span class="calculator-home-proof ${extraClass}">
        ${calculatorStartIconSvg(iconName, 'calculator-home-proof-icon')}
        <span>${escapeHtml(label)}</span>
    </span>`;
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
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/5 border border-white/[0.08] text-[11px] text-terracota-textMuted">
        <span class="w-1.5 h-1.5 rounded-full ${q.canCreate ? 'bg-emerald-400' : 'bg-red-400'}"></span>
        ${q.tablesCreated}/${limitText}
    </span>`;
}

function quotaBadgeFullHtml(extraClass = '') {
    const q = state.quotaInfo;
    if (!q) return '';
    const limitText = q.tablesLimit === null ? '∞' : q.tablesLimit;
    const classes = extraClass ? ` ${extraClass}` : '';
    return `<div class="text-center mt-3 text-xs text-terracota-textMuted${classes}">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10">
            <span class="w-2 h-2 rounded-full ${q.canCreate ? 'bg-emerald-400' : 'bg-red-400'}"></span>
            ${q.tablesCreated}/${limitText} tabelas este mês · <span class="text-terracota-cyan">${escapeHtml(q.planName)}</span>
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
        _updateHeaderQuotaBadge();
        return state.quotaInfo;
    } catch (e) { console.error('fetchQuota error', e); return null; }
}

function _updateHeaderQuotaBadge() {
    const el = document.getElementById('header-quota-badge');
    if (el) el.innerHTML = quotaBadgeHtml();
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
        state.maxStepReached = 0;
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

    // Track highest step reached for fluid back-navigation
    state.maxStepReached = Math.max(state.maxStepReached, step);

    // Determine direction for slide animation
    const goingForward = step > prevStep;
    const outClass = goingForward ? 'wizard-slide-out-left' : 'wizard-slide-out-right';
    const inClass  = goingForward ? 'wizard-slide-in-right' : 'wizard-slide-in-left';

    // Remove any lingering animation classes
    content.classList.remove('wizard-fade-in', 'wizard-fade-out', 'wizard-slide-out-left', 'wizard-slide-out-right', 'wizard-slide-in-left', 'wizard-slide-in-right');
    content.classList.add(outClass);

    const onFadeOut = () => {
        content.removeEventListener('animationend', onFadeOut);
        state.currentStep = step;
        updateUI();
        content.classList.remove(outClass);
        content.classList.add(inClass);
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

    // Back button: visible on any step > 1 (unless finalized)
    const showBack = state.currentStep > 1 && !state.isFinalized;
    btnBack.style.display = showBack ? 'flex' : 'none';
    btnBack.disabled = !showBack;

    // Next button: visible on steps 1 and 2 only
    btnNext.style.display = state.currentStep > 0 && state.currentStep < 3 ? 'flex' : 'none';
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
            btnNext.innerHTML = '<span>Próximo: Ingredientes</span> <i class="ph ph-arrow-right ml-2"></i>';
            btnBack.innerHTML = '<i class="ph ph-arrow-left mr-2"></i> <span>Voltar</span>';
            break;
        case 2:
            renderStep2(content);
            btnNext.innerHTML = '<i class="ph ph-calculator mr-2"></i> <span>Calcular Tabela</span>';
            btnBack.innerHTML = '<i class="ph ph-arrow-left mr-2"></i> <span>Voltar: Produto</span>';
            break;
        case 3:
            renderStep3(content);
            btnBack.innerHTML = '<i class="ph ph-arrow-left mr-2"></i> <span>Voltar: Ingredientes</span>';
            break;
        default:
            renderWelcome();
    }
}

function renderProgressBar(step) {
    const steps = [
        { label: 'Produto', sub: 'Nome, porção e conformidade', icon: 'ph-package' },
        { label: 'Ingredientes', sub: 'Receita, macros e revisão', icon: 'ph-bowl-food' },
        { label: 'Tabela', sub: 'Prévia e geração final', icon: 'ph-calculator' }
    ];
    const ingredientCount = state.ingredients.length;

    const segments = steps.map((s, idx) => {
        const sNum = idx + 1;
        const completed = sNum < step;
        const active = sNum === step;
        const canClick = (sNum !== step) && (sNum <= state.maxStepReached || (sNum === 3 && state.calculatedData));
        const reachable = !completed && !active && sNum <= state.maxStepReached;
        const clickAttr = canClick
            ? `onclick="goToStep(${sNum})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();goToStep(${sNum});}" role="button" tabindex="0"`
            : 'aria-disabled="true"';
        let cardStateClass = 'wizard-step-card-future';
        let statusLabel = 'Aguardando';
        if (completed) {
            cardStateClass = 'wizard-step-card-completed';
            statusLabel = 'Concluído';
        } else if (active) {
            cardStateClass = 'wizard-step-card-active';
            statusLabel = 'Em edição';
        } else if (reachable) {
            cardStateClass = 'wizard-step-card-reachable';
            statusLabel = 'Disponível';
        }
        const badge = sNum === 2 && ingredientCount > 0
            ? `<span class="wizard-step-badge">${ingredientCount}</span>`
            : '';
        return `
            <div class="wizard-step-card ${cardStateClass} ${canClick ? 'is-clickable' : ''}" ${clickAttr} aria-current="${active ? 'step' : 'false'}">
                <div class="wizard-step-medallion">
                    <span class="wizard-step-number">0${sNum}</span>
                    <span class="wizard-step-icon">
                        <i class="ph ${s.icon}"></i>
                    </span>
                    ${completed ? '<span class="wizard-step-check"><i class="ph ph-check"></i></span>' : ''}
                </div>
                <div class="wizard-step-copy">
                    <div class="wizard-step-copy-row">
                        <span class="wizard-step-title">${s.label}</span>
                        ${badge}
                    </div>
                    <p class="wizard-step-subtitle">${s.sub}</p>
                    <span class="wizard-step-status">${statusLabel}</span>
                </div>
                ${active ? '<span class="wizard-step-active-line"></span>' : ''}
            </div>
        `;
    });

    const connectorHtml = (idx) => {
        const filled = idx + 1 < step;
        return `<div class="wizard-step-connector ${filled ? 'is-filled' : ''}" aria-hidden="true"></div>`;
    };

    const interleaved = segments.map((seg, i) =>
        i < segments.length - 1 ? seg + connectorHtml(i) : seg
    ).join('');

    return `<nav aria-label="Progresso da calculadora" class="wizard-step-grid" role="navigation">
        ${interleaved}
    </nav>
    <div class="flex justify-end items-center mt-3">
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
        <div class="calculator-home-shell">
            <section class="calculator-home-hero text-center" aria-labelledby="calculator-home-title">
                <div class="calculator-home-kicker">
                    <span class="calculator-home-kicker-dot"></span>
                    Plataforma de cálculo e conformidade
                </div>
                <div class="calculator-home-hero-icon-shell" aria-hidden="true">
                    <div class="calculator-home-hero-icon-core">
                        ${calculatorStartIconSvg('calculatorShield', 'calculator-home-hero-icon')}
                    </div>
                    <div class="calculator-home-hero-icon-badge">
                        ${calculatorStartIconSvg('tableShield', 'calculator-home-hero-badge-icon')}
                    </div>
                </div>
                <h2 id="calculator-home-title" class="text-4xl sm:text-[2.75rem] font-bold text-white mb-5 font-heading tracking-tight">Calculadora Nutricional</h2>
                <p class="text-lg sm:text-xl text-terracota-textLight mb-7 max-w-2xl mx-auto font-light leading-relaxed">
                    Gere tabelas nutricionais com uma jornada guiada para <span class="text-white font-medium">dados do produto</span>, <span class="text-white font-medium">ingredientes</span> e saída final em conformidade com a <span class="text-terracota-cyan font-medium">RDC 429/2020</span> e a <span class="text-terracota-cyan font-medium">IN 75/2020</span>.
                </p>
                <div class="calculator-home-proof-row">
                    ${calculatorStartFeaturePill('calculator', 'Cálculo guiado')}
                    ${calculatorStartFeaturePill('table', 'Tabela nutricional')}
                    ${calculatorStartFeaturePill('shield', 'Conformidade ANVISA', 'is-highlight')}
                </div>
                ${quotaBadgeFullHtml('calculator-home-quota')}
                <button onclick="goToStep(1)" class="calculator-home-cta mt-6 px-10 py-4 bg-terracota-cyan text-terracota-deepDark text-lg font-bold rounded-xl hover:bg-white hover:scale-[1.02] shadow-[0_0_30px_rgba(0,196,204,0.24)] transition-all inline-flex items-center gap-3">
                    ${calculatorStartIconSvg('product', 'calculator-home-cta-icon')}
                    <span>Iniciar Novo Produto</span>
                </button>
            </section>
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
    const inputClass = "w-full px-3 py-2.5 bg-black/25 border border-white/[0.08] rounded-xl text-white placeholder-white/20 focus:ring-1 focus:ring-terracota-cyan focus:border-terracota-cyan/40 outline-none transition-all text-sm";
    const labelClass = "block text-[10px] font-medium text-terracota-textMuted mb-1.5 uppercase tracking-wider";
    const isLiquid = state.product.foodForm === 'liquid';
    const portionUnitLabel = isLiquid ? 'ml' : 'g';

    const prodComplete = !!(state.product.name && state.product.foodForm);
    const portionComplete = !!(state.product.portionSize && state.product.portionDesc && state.product.servingsPerPackage);
    const regComplete = !!(
        (state.product.allergenKeys?.length > 0 || state.product.allergens?.trim() || state.product.customAllergens?.trim()) &&
        state.product.glutenStatus
    );
    const firstIncomplete = !prodComplete ? 'product' : !portionComplete ? 'portion' : !regComplete ? 'regulatory' : 'portion';
    const sectionStatus = (done, pendingLabel = 'Pendente') => done
        ? '<span class="calculator-status-pill is-complete"><i class="ph ph-check-circle"></i>Completo</span>'
        : `<span class="calculator-status-pill">${pendingLabel}</span>`;

    let allergenTagsHtml = '';
    if (state.allergenRegistry && state.allergenRegistry.allergens) {
        const tags = state.allergenRegistry.allergens.map(a => {
            const active = state.product.allergenKeys.includes(a.key);
            return `<button type="button" data-allergen-key="${a.key}" class="allergen-tag px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                active
                    ? 'bg-terracota-cyan/20 border-terracota-cyan/40 text-terracota-cyan'
                    : 'bg-white/[0.03] border-white/[0.08] text-white/40 hover:border-white/20 hover:text-white/60'
            }">${escapeHtml(a.label)}</button>`;
        }).join('');
        allergenTagsHtml = `<div class="flex flex-wrap gap-1.5">${tags}</div>`;
    } else {
        allergenTagsHtml = `<textarea id="input-allergens-fallback" rows="2" class="${inputClass}" placeholder="Ex: CONTÉM OVO E TRIGO">${escapeHtml(state.product.allergens)}</textarea>`;
    }

    // ---- Gluten options ----
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
            ? `<span class="text-[9px] text-terracota-cyan/70 ml-1">(${filteredCount}/${totalGroupCount})</span>`
            : '';
        portionGroupHtml = `
            <div>
                <label class="${labelClass}">Grupo de Alimento (Anexo V) ${filterBadge}</label>
                <select id="input-group-code" class="${inputClass} appearance-none cursor-pointer">
                    <option value="" class="bg-terracota-deepDark">— Selecione (opcional) —</option>
                    ${options}
                </select>
            </div>`;
    }

    const portionOpen = firstIncomplete === 'portion' || !!(state.product.portionSize || state.product.groupCode || state.product.packageWeight);
    const regOpen = firstIncomplete === 'regulatory' || !!(state.product.allergenKeys?.length > 0 || state.product.customAllergens?.trim() || state.product.allergens?.trim());

    container.innerHTML = `
        <div class="space-y-4 max-w-3xl mx-auto">
            <div class="calculator-hero-card">
                <div class="section-icon-lg">
                    <i class="ph ph-calculator text-xl"></i>
                </div>
                <div class="min-w-0">
                    <p class="calculator-eyebrow">Calculadora nutricional</p>
                    <h3 class="text-xl sm:text-2xl font-bold text-white font-heading">Informações do produto</h3>
                    <p class="text-sm text-white/55 mt-1">Organize os dados obrigatórios com clareza antes de calcular a tabela. O foco aqui é definir porção, rendimento e conformidade regulatória sem esconder campos importantes.</p>
                </div>
            </div>

            <div class="calculator-surface-card">
                <div class="calculator-section-header">
                    <div class="section-icon">
                        <i class="ph ph-package text-sm"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-semibold text-white">Produto</p>
                        <p class="text-xs text-white/45">Nome comercial, forma do alimento e grupo de referência.</p>
                    </div>
                    <div class="ml-auto">
                        ${sectionStatus(prodComplete, 'Essencial')}
                    </div>
                </div>
                <div class="px-4 pb-4 pt-1 space-y-4">
                    <div>
                        <label class="${labelClass}">Nome do Produto</label>
                        <input type="text" id="input-name" value="${escapeHtml(state.product.name)}" class="${inputClass}" placeholder="Ex: Bolo de Chocolate">
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="${labelClass}">Tipo</label>
                            <select id="input-food-form" class="${inputClass} appearance-none cursor-pointer">
                                <option value="solid" class="bg-terracota-deepDark" ${state.product.foodForm === 'solid' ? 'selected' : ''}>Sólido</option>
                                <option value="liquid" class="bg-terracota-deepDark" ${state.product.foodForm === 'liquid' ? 'selected' : ''}>Líquido</option>
                            </select>
                        </div>
                        <div>
                            ${portionGroupHtml ? portionGroupHtml : `<label class="${labelClass}">Grupo</label><p class="text-xs text-white/20 py-2.5">Carregando...</p>`}
                        </div>
                    </div>
                </div>
            </div>

            <details id="section-portion" class="group/sec calculator-surface-card calculator-surface-card-details" ${portionOpen ? 'open' : ''}>
                <summary class="calculator-section-summary">
                    <div class="section-icon">
                        <i class="ph ph-scales text-sm"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-semibold text-white">Porção & Embalagem</p>
                        <p class="text-xs text-white/45">Defina a porção de referência, medida caseira e rendimento da embalagem.</p>
                    </div>
                    <div class="calculator-section-summary-side">
                        ${sectionStatus(portionComplete, 'Configurar')}
                        <i class="ph ph-caret-down calculator-summary-caret"></i>
                    </div>
                </summary>
                <div class="px-4 pb-4 space-y-4">
                    <div class="calculator-section-callout">
                        <i class="ph ph-ruler text-sm"></i>
                        <span>A porção selecionada orienta o cálculo por porção e a checagem de consistência com o grupo do Anexo V.</span>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div>
                            <label class="${labelClass}">Peso da Embalagem (${portionUnitLabel})</label>
                            <input type="number" id="input-package-weight" value="${escapeHtml(state.product.packageWeight || '')}" class="${inputClass}" placeholder="Ex: 500" min="0.1" step="0.1">
                        </div>
                        <div>
                            <label class="${labelClass}">Porções/Embalagem</label>
                            <input type="number" id="input-servings-per-package" value="${escapeHtml(state.product.servingsPerPackage)}" class="${inputClass}" placeholder="Ex: 5" min="1" step="1" ${state.product.packageWeight ? 'readonly' : ''}>
                            ${state.product.packageWeight ? '<p class="text-[9px] text-terracota-textMuted mt-0.5">auto-calculado</p>' : ''}
                        </div>
                    </div>
                </div>
            </details>

            <details id="section-regulatory" class="group/sec calculator-surface-card calculator-surface-card-details" ${regOpen ? 'open' : ''}>
                <summary class="calculator-section-summary">
                    <div class="section-icon">
                        <i class="ph ph-shield-check text-sm"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-semibold text-white">Declarações Regulatórias</p>
                        <p class="text-xs text-white/45">Alergênicos, glúten e avisos obrigatórios para a rotulagem final.</p>
                    </div>
                    <div class="calculator-section-summary-side">
                        ${sectionStatus(regComplete, 'Revisar')}
                        <i class="ph ph-caret-down calculator-summary-caret"></i>
                    </div>
                </summary>
                <div class="px-4 pb-4 space-y-4">
                    <div class="calculator-section-callout">
                        <i class="ph ph-warning-diamond text-sm"></i>
                        <span>Preencha as declarações obrigatórias agora para evitar retrabalho quando a prévia estiver pronta.</span>
                    </div>
                    <div>
                        <label class="${labelClass}">Alérgenos (RDC 26/2015)</label>
                        ${allergenTagsHtml}
                        <div class="mt-2">
                            <input type="text" id="input-custom-allergens" value="${escapeHtml(state.product.customAllergens)}" class="${inputClass}" placeholder="Outros alérgenos: ex. kiwi, gergelim">
                        </div>
                    </div>
                    <div>
                        <label class="${labelClass}">Glúten</label>
                        <select id="input-gluten-status" class="${inputClass} appearance-none cursor-pointer">
                            ${glutenOptionsHtml}
                        </select>
                    </div>
                </div>
            </details>

            <details class="group/tips tips-card calculator-surface-card bg-white/[0.02]">
                <summary class="cursor-pointer px-4 py-3 flex items-center gap-2.5 select-none">
                    <div class="section-icon section-icon-amber">
                        <i class="ph ph-warning-diamond text-sm"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-semibold text-white/75 group-hover/tips:text-white transition-colors">Checklist rápido de conformidade</p>
                        <p class="text-xs text-white/35">Use este bloco para revisar os principais pontos antes do cálculo.</p>
                    </div>
                    <i class="ph ph-caret-down text-xs text-white/30 ml-auto transition-transform duration-300 group-open/tips:rotate-180 group-hover/tips:text-terracota-cyan"></i>
                </summary>
                <div class="px-4 pb-4 pt-1 space-y-2 text-[11px] text-terracota-textMuted leading-relaxed border-t border-white/[0.04]">
                    <div class="flex items-start gap-2 py-1.5">
                        <i class="ph ph-scales text-terracota-cyan text-sm mt-0.5 flex-shrink-0"></i>
                        <p><strong class="text-white/80">Porção:</strong> Referência pelo grupo de alimento (Anexo V, IN 75). Tolerância de ±30%.</p>
                    </div>
                    <div class="flex items-start gap-2 py-1.5">
                        <i class="ph ph-warning-diamond text-amber-400 text-sm mt-0.5 flex-shrink-0"></i>
                        <p><strong class="text-white/80">Alérgenos:</strong> Obrigatório conforme RDC 26/2015, mesmo em traços.</p>
                    </div>
                    <div class="flex items-start gap-2 py-1.5">
                        <i class="ph ph-spoon text-terracota-cyan text-sm mt-0.5 flex-shrink-0"></i>
                        <p><strong class="text-white/80">Medida caseira:</strong> Ex: "1 fatia", "2 colheres de sopa". Obrigatória (RDC 429).</p>
                    </div>
                    <div class="flex items-start gap-2 py-1.5">
                        <i class="ph ph-package text-terracota-cyan text-sm mt-0.5 flex-shrink-0"></i>
                        <p><strong class="text-white/80">Porções/embalagem:</strong> Obrigatório (Art. 22). Auto-calculado se peso preenchido.</p>
                    </div>
                </div>
            </details>
        </div>
    `;

    // ---- Event listeners ----
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
        const servingsInput = document.getElementById('input-servings-per-package');
        if (servingsInput) {
            servingsInput.value = state.product.servingsPerPackage;
            servingsInput.readOnly = !!state.product.packageWeight;
        }
    });
    document.getElementById('input-custom-allergens')?.addEventListener('input', (e) => { state.product.customAllergens = e.target.value; _syncAllergenText(); _autosave(); });

    // Allergen tag-pills — toggle on click
    document.querySelectorAll('.allergen-tag').forEach(tag => {
        tag.addEventListener('click', () => {
            const key = tag.getAttribute('data-allergen-key');
            const idx = state.product.allergenKeys.indexOf(key);
            if (idx >= 0) {
                state.product.allergenKeys.splice(idx, 1);
                tag.classList.remove('bg-terracota-cyan/20', 'border-terracota-cyan/40', 'text-terracota-cyan');
                tag.classList.add('bg-white/[0.03]', 'border-white/[0.08]', 'text-white/40');
            } else {
                state.product.allergenKeys.push(key);
                tag.classList.add('bg-terracota-cyan/20', 'border-terracota-cyan/40', 'text-terracota-cyan');
                tag.classList.remove('bg-white/[0.03]', 'border-white/[0.08]', 'text-white/40');
            }
            _syncAllergenText();
            _autosave();
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

    // Group code — auto-fill portion + auto-open portion section
    const groupCodeSelect = document.getElementById('input-group-code');
    if (groupCodeSelect) {
        groupCodeSelect.addEventListener('change', (e) => {
            state.product.groupCode = e.target.value;
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
                    // Auto-open portion section with highlight flash
                    const sec = document.getElementById('section-portion');
                    if (sec && !sec.open) {
                        sec.open = true;
                        sec.classList.add('ring-1', 'ring-emerald-400/40');
                        setTimeout(() => sec.classList.remove('ring-1', 'ring-emerald-400/40'), 1500);
                    }
                }
            }
        });
    }

    document.getElementById('input-food-form').addEventListener('change', (e) => {
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
    _activeInlineNutriIndex = -1;
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
    if (_activeInlineNutriIndex >= state.ingredients.length) {
        _activeInlineNutriIndex = -1;
    }
    if (!hasIngredients) {
        state.summaryDockCollapsed = false;
        state.summaryDockManual = false;
    } else if (!state.summaryDockManual) {
        state.summaryDockCollapsed = false;
    }

    const emptyStateHtml = !hasIngredients ? `
        <div class="calculator-empty-state">
            <div class="calculator-empty-icon">
                <i class="ph ph-bowl-food text-3xl"></i>
            </div>
            <p class="text-white text-base font-medium mb-1.5">Monte a fórmula ingrediente por ingrediente</p>
            <p class="text-terracota-textMuted text-sm mb-6 max-w-sm mx-auto">Pesquise na Tabela TACO, ajuste a quantidade usada na receita e abra os detalhes nutricionais quando precisar revisar macros e alertas.</p>
            <button onclick="addIngredientWithFocus()" class="px-6 py-2.5 bg-terracota-cyan/15 border border-terracota-cyan/30 text-terracota-cyan text-sm font-semibold rounded-xl hover:bg-terracota-cyan/25 transition-all inline-flex items-center gap-2">
                <i class="ph ph-magnifying-glass text-base"></i> Buscar na TACO
            </button>
            <p class="mt-3"><button onclick="addIngredient()" class="text-xs text-terracota-textMuted hover:text-white transition-colors">ou criar uma linha manualmente</button></p>
        </div>` : '';

    const toolbarHtml = hasIngredients ? `
            <div class="formula-toolbar">
                <div class="formula-toolbar-actions">
                <button onclick="addIngredientWithFocus()" class="px-3 py-1.5 bg-terracota-cyan/10 border border-terracota-cyan/25 text-terracota-cyan rounded-xl hover:bg-terracota-cyan/20 transition-colors font-medium inline-flex items-center gap-1.5">
                    <i class="ph ph-plus text-sm"></i> Adicionar
                </button>
                <button onclick="_openImportModal()" class="px-3 py-1.5 bg-white/[0.04] border border-white/[0.08] text-terracota-textMuted rounded-xl hover:bg-white/[0.08] hover:text-white transition-colors inline-flex items-center gap-1.5">
                    <i class="ph ph-file-xls text-sm"></i> Importar
                </button>
                </div>
                <div class="formula-toolbar-secondary">
                <button onclick="fillZeroNutrients()" class="text-terracota-textMuted hover:text-white transition-colors px-2.5 py-1.5 rounded-lg hover:bg-white/[0.06]" title="Preencher campos vazios com 0"><i class="ph ph-cursor-text text-sm"></i></button>
                <button onclick="confirmClearAllIngredients()" class="text-red-400/50 hover:text-red-400 transition-colors px-2.5 py-1.5 rounded-lg hover:bg-red-500/10" title="Remover todos"><i class="ph ph-trash text-sm"></i></button>
                ${state.ingredients.length > 5 ? `
                <div class="relative">
                    <i class="ph ph-magnifying-glass text-sm absolute left-2 top-1/2 -translate-y-1/2 text-terracota-textMuted pointer-events-none"></i>
                    <input type="text" id="ing-search" class="w-40 text-xs bg-black/25 border border-white/[0.08] rounded-xl pl-7 pr-2 py-1.5 text-white placeholder:text-white/20 focus:ring-1 focus:ring-terracota-cyan focus:border-terracota-cyan" placeholder="Filtrar ingrediente..." oninput="filterIngredients(this.value)">
                </div>` : ''}
                </div>
            </div>` : '';

    container.innerHTML = `
        <div class="space-y-4 pb-8">
            <div class="calculator-hero-card">
                <div class="section-icon-lg">
                    <i class="ph ph-bowl-food text-xl"></i>
                </div>
                <div class="min-w-0">
                    <p class="calculator-eyebrow">Composição da receita</p>
                    <h3 class="text-xl sm:text-2xl font-bold text-white font-heading">Ingredientes</h3>
                    <p class="text-sm text-white/55 mt-1">Cada ingrediente agora mostra um resumo claro da contribuição energética e uma área óbvia para abrir macros e detalhes nutricionais.</p>
                </div>
            </div>
            ${toolbarHtml}
            <div id="ingredients-list" class="space-y-3">
                ${emptyStateHtml}
            </div>
            <div id="summary-dock"></div>
        </div>
        <!-- Import modal (hidden) -->
        <div id="import-modal" class="fixed inset-0 z-50 hidden">
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onclick="_closeImportModal()"></div>
            <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-md p-6">
                <div class="bg-terracota-surface border border-white/10 rounded-2xl p-6 shadow-2xl relative">
                    <button onclick="_closeImportModal()" class="absolute top-3 right-3 text-terracota-textMuted hover:text-white transition-colors"><i class="ph ph-x text-lg"></i></button>
                    <h4 class="text-base font-heading font-semibold text-white mb-4"><i class="ph ph-file-xls text-terracota-cyan mr-2"></i>Importar Excel</h4>
                    <div id="drop-zone" class="border-2 border-dashed border-white/15 rounded-xl p-8 text-center transition-all hover:border-terracota-cyan/50 hover:bg-terracota-cyan/[0.03] group relative">
                        <input type="file" id="file-upload" class="hidden" accept=".xlsx" onchange="handleExcelUpload(this.files[0]); _closeImportModal();">
                        <i class="ph ph-upload-simple text-3xl text-terracota-textMuted group-hover:text-terracota-cyan transition-colors mb-3 block"></i>
                        <p class="text-sm text-terracota-textLight mb-1">Arraste um arquivo .xlsx aqui</p>
                        <p class="text-xs text-terracota-textMuted">ou <button onclick="document.getElementById('file-upload').click()" class="text-terracota-cyan hover:underline">selecione do computador</button></p>
                        <div id="upload-loading" class="absolute inset-0 bg-terracota-surface/95 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center hidden">
                            <div class="w-8 h-8 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin mb-3"></div>
                            <p class="text-xs text-terracota-cyan font-medium">Processando...</p>
                        </div>
                    </div>
                    <p class="text-[10px] text-terracota-textMuted mt-3">Formato: .xlsx · Máx 5MB · Até 500 linhas · Colunas mapeadas automaticamente</p>
                </div>
            </div>
        </div>
    `;

    if (hasIngredients) {
        const list = document.getElementById('ingredients-list');
        list.innerHTML = '';
        state.ingredients.forEach((ing, idx) => {
            list.appendChild(createIngredientRow(ing, idx));
        });
        if (_activeInlineNutriIndex !== -1) {
            _renderInlineNutriContent(_activeInlineNutriIndex);
        }
        _renderFullRunningTotals();
    }
    setupDragAndDrop();
    setupIngredientDragAndDrop();
}

// ---- Inline Nutrient Panel --------------------------------------------------

let _activeInlineNutriIndex = -1;

function _toggleInlineNutri(index) {
    const panel = document.querySelector(`[data-nutri-panel="${index}"]`);
    if (!panel) return;
    const trigger = document.querySelector(`[data-nutri-trigger="${index}"]`);
    const wrapper = panel.closest('.ing-row-wrapper');
    const isExpanding = !panel.classList.contains('expanded');
    if (isExpanding && _activeInlineNutriIndex !== -1 && _activeInlineNutriIndex !== index) {
        const prevPanel = document.querySelector(`[data-nutri-panel="${_activeInlineNutriIndex}"]`);
        const prevTrigger = document.querySelector(`[data-nutri-trigger="${_activeInlineNutriIndex}"]`);
        const prevWrapper = prevPanel?.closest('.ing-row-wrapper');
        if (prevPanel) prevPanel.classList.remove('expanded');
        if (prevTrigger) {
            prevTrigger.classList.remove('active');
            prevTrigger.setAttribute('aria-expanded', 'false');
        }
        if (prevWrapper) prevWrapper.classList.remove('is-expanded');
    }

    if (isExpanding) {
        _activeInlineNutriIndex = index;
        _renderInlineNutriContent(index);
        panel.classList.add('expanded');
        if (wrapper) wrapper.classList.add('is-expanded');
        if (trigger) {
            trigger.classList.add('active');
            trigger.setAttribute('aria-expanded', 'true');
        }
        requestAnimationFrame(() => {
            if (wrapper) wrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    } else {
        _activeInlineNutriIndex = -1;
        panel.classList.remove('expanded');
        if (wrapper) wrapper.classList.remove('is-expanded');
        if (trigger) {
            trigger.classList.remove('active');
            trigger.setAttribute('aria-expanded', 'false');
        }
    }
}

function _renderInlineNutriContent(index) {
    const ing = state.ingredients[index];
    if (!ing) return;
    const nutri = ing.nutritionalInfo || {};
    const unit = state.product.portionUnit || 'g';
    const warnings = getIngredientWarnings(nutri, ing);
    const warnFields = new Set(warnings.flatMap(w => w.fields));
    const hasTaco = !!ing._tacoId;
    const estimated = estimateKcal(nutri);
    const isManualKcal = ing._manualKcal === true;
    const kcalDisplay = isManualKcal ? nutri.energyKcal : (estimated ?? nutri.energyKcal ?? '');
    const kcalIsAuto = !isManualKcal && estimated !== null;

    const inputClass = "w-full text-sm bg-black/30 border border-white/[0.08] rounded-xl text-white focus:ring-1 focus:ring-terracota-cyan px-3 py-2";
    const labelClass = "block text-[10px] text-slate-400 mb-1 uppercase tracking-wider";
    const warnClass = (field) => warnFields.has(field) ? 'border-yellow-500/60 bg-yellow-500/5' : '';

    const panel = document.querySelector(`[data-nutri-panel="${index}"]`);
    if (!panel) return;
    const inner = panel.querySelector('.ing-nutri-inner > div');
    if (!inner) return;

    inner.innerHTML = `
        <div class="ingredient-detail-card">
            <div class="px-4 py-3 flex items-center justify-between border-b border-white/[0.04]">
                <div class="flex items-center gap-2.5">
                    <div class="section-icon" style="width:1.75rem;height:1.75rem;">
                        <i class="ph ph-chart-pie-slice" style="font-size:0.8rem;"></i>
                    </div>
                    <div>
                        <p class="text-[11px] font-semibold text-white uppercase tracking-wider">Nutrientes por 100${unit}</p>
                        <p class="text-[11px] text-white/40">Revise macros, subtipos e avisos de consistência para este ingrediente.</p>
                    </div>
                </div>
                ${hasTaco ? '<span class="macro-pill macro-pill-source">TACO</span>' : ''}
            </div>
            <div class="p-4 space-y-4">
                <div class="calculator-section-callout">
                    <i class="ph ph-chart-pie-slice text-sm"></i>
                    <span>${kcalIsAuto ? 'A energia está sendo estimada automaticamente a partir dos macros preenchidos.' : 'A energia está manual. Ajuste os macros abaixo e revise os avisos de consistência.'}</span>
                </div>
                <div class="grid grid-cols-3 gap-3">
                    <div>
                        <label class="${labelClass}">Energia (kcal) ${kcalIsAuto ? '<span class="text-terracota-cyan/80">auto</span>' : ''}</label>
                        <input type="number" class="${inputClass} ${kcalIsAuto ? 'text-terracota-cyan' : ''}" value="${kcalDisplay}" oninput="updateIngredientNutri(${index}, 'energyKcal', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.1" title="Auto: Carb×4 + Prot×4 + Gord×9 + Fibra×2">
                    </div>
                    <div>
                        <label class="${labelClass}">Carboidratos (g)</label>
                        <input type="number" class="${inputClass} ${warnClass('carbs')}" value="${nutri.carbs ?? ''}" oninput="updateIngredientNutri(${index}, 'carbs', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                    </div>
                    <div>
                        <label class="${labelClass}">Proteínas (g)</label>
                        <input type="number" class="${inputClass} ${warnClass('proteins')}" value="${nutri.proteins ?? ''}" oninput="updateIngredientNutri(${index}, 'proteins', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                    </div>
                </div>
                <div class="grid grid-cols-3 gap-3">
                    <div>
                        <label class="${labelClass}">Gorduras Totais (g)</label>
                        <input type="number" class="${inputClass} ${warnClass('totalFat')}" value="${nutri.totalFat ?? ''}" oninput="updateIngredientNutri(${index}, 'totalFat', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                    </div>
                    <div>
                        <label class="${labelClass}">Fibra Alimentar (g)</label>
                        <input type="number" class="${inputClass} ${warnClass('fiber')}" value="${nutri.fiber ?? ''}" oninput="updateIngredientNutri(${index}, 'fiber', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                    </div>
                    <div>
                        <label class="${labelClass}">Sódio (mg)</label>
                        <input type="number" class="${inputClass} ${warnClass('sodium')}" value="${nutri.sodium ?? ''}" oninput="updateIngredientNutri(${index}, 'sodium', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                    </div>
                </div>
                <div class="border-t border-white/[0.04] pt-3">
                    <p class="text-[10px] text-terracota-textMuted uppercase tracking-wider mb-2">Subtipos</p>
                    <div class="grid grid-cols-4 gap-3">
                        <div>
                            <label class="${labelClass}">↳ Saturada (g)</label>
                            <input type="number" class="${inputClass} ${warnClass('saturatedFat')}" value="${nutri.saturatedFat ?? ''}" oninput="updateIngredientNutri(${index}, 'saturatedFat', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">↳ Trans (g)</label>
                            <input type="number" class="${inputClass} ${warnClass('transFat')}" value="${nutri.transFat ?? ''}" oninput="updateIngredientNutri(${index}, 'transFat', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">↳ Açúc. Totais (g)</label>
                            <input type="number" class="${inputClass} ${warnClass('totalSugars')}" value="${nutri.totalSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'totalSugars', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                        </div>
                        <div>
                            <label class="${labelClass}">↳ Açúc. Adicion. (g)</label>
                            <input type="number" class="${inputClass} ${warnClass('addedSugars')}" value="${nutri.addedSugars ?? ''}" oninput="updateIngredientNutri(${index}, 'addedSugars', this.value); _refreshInlineNutriWarnings(${index});" min="0" step="0.01">
                        </div>
                    </div>
                </div>
                <div id="inline-nutri-warnings-${index}">${warnings.length > 0 ? warnings.map(w => {
                    const isInfo = w.type === 'info';
                    const colorClass = isInfo ? 'text-terracota-cyan/80' : 'text-yellow-400';
                    const icon = isInfo ? 'ph-info' : 'ph-warning';
                    return `<p class="text-[11px] ${colorClass} flex items-center gap-1 mt-1"><i class="ph ${icon} text-xs flex-shrink-0"></i>${escapeHtml(w.msg)}</p>`;
                }).join('') : ''}</div>
            </div>
        </div>
    `;
}

function _refreshInlineNutriWarnings(index) {
    const ing = state.ingredients[index];
    if (!ing) return;
    const nutri = ing.nutritionalInfo;
    const warnings = getIngredientWarnings(nutri, ing);
    const warnContainer = document.getElementById(`inline-nutri-warnings-${index}`);
    if (warnContainer) {
        warnContainer.innerHTML = warnings.length > 0 ? warnings.map(w => {
            const isInfo = w.type === 'info';
            const colorClass = isInfo ? 'text-terracota-cyan/80' : 'text-yellow-400';
            const icon = isInfo ? 'ph-info' : 'ph-warning';
            return `<p class="text-[11px] ${colorClass} flex items-center gap-1 mt-1"><i class="ph ${icon} text-xs flex-shrink-0"></i>${escapeHtml(w.msg)}</p>`;
        }).join('') : '';
    }
    // Auto kcal recalc
    const estimated = estimateKcal(nutri);
    const isManual = ing._manualKcal === true;
    if (!isManual && estimated !== null) {
        nutri.energyKcal = estimated;
        const panel = document.querySelector(`[data-nutri-panel="${index}"]`);
        if (panel) {
            const kcalInput = panel.querySelector('input[oninput*="energyKcal"]');
            if (kcalInput) {
                kcalInput.value = estimated;
                kcalInput.classList.add('text-terracota-cyan');
            }
        }
    }
    _refreshCompactTotals();
    _refreshIngredientRowSummary(index);
}

function createIngredientRow(ing, index) {
    const inputClass = "w-full text-sm bg-black/25 border-white/[0.08] rounded-xl text-white focus:ring-1 focus:ring-terracota-cyan border px-3 py-2";
    const nutri = ing.nutritionalInfo || {};
    const unit = state.product.portionUnit || 'g';
    const warnings = getIngredientWarnings(nutri, ing);
    const hasTaco = !!ing._tacoId;
    const estimated = estimateKcal(nutri);
    const isManualKcal = ing._manualKcal === true;
    const kcalDisplay = isManualKcal ? nutri.energyKcal : (estimated ?? nutri.energyKcal ?? '');
    const kcalSummary = kcalDisplay !== '' ? `${kcalDisplay}` : '—';
    const hardWarnings = warnings.filter(w => w.type !== 'info');
    const filledCount = INGREDIENT_NUTRIENT_FIELDS.filter(f => nutri[f] !== '' && nutri[f] !== null && nutri[f] !== undefined).length;
    const isExpanded = _activeInlineNutriIndex === index;
    const completionClass = filledCount === INGREDIENT_NUTRIENT_FIELDS.length ? 'macro-pill macro-pill-success' : 'macro-pill';
    const completionLabel = filledCount === INGREDIENT_NUTRIENT_FIELDS.length
        ? '<i class="ph ph-check-circle"></i>Completo'
        : `${filledCount}/10 campos`;
    const warningBadge = hardWarnings.length > 0
        ? `<span class="macro-pill macro-pill-warning" data-ing-warning="${index}"><i class="ph ph-warning-diamond"></i>${hardWarnings.length} aviso${hardWarnings.length > 1 ? 's' : ''}</span>`
        : `<span class="macro-pill hidden" data-ing-warning="${index}"></span>`;

    const el = document.createElement('div');
    el.className = `ing-row-wrapper ingredient-card-shell ${isExpanded ? 'is-expanded' : ''}`;
    el.setAttribute('data-ing-index', index);
    el.setAttribute('draggable', 'true');

    el.innerHTML = `
        <div class="ing-row" data-ing-index="${index}">
            <div class="ingredient-card-top">
                <div class="ingredient-card-main">
                    <div class="drag-handle text-white/20 hover:text-terracota-cyan" title="Arrastar para reordenar">
                        <i class="ph ph-dots-six-vertical text-base"></i>
                    </div>
                    <div class="ingredient-field ingredient-name-field">
                        <label class="ingredient-field-label">Ingrediente</label>
                        <div class="relative">
                            <input type="text" class="${inputClass} ingredient-name-input" value="${escapeHtml(ing.name)}" data-index="${index}" placeholder="Buscar ingrediente na TACO..." autocomplete="off">
                        </div>
                    </div>
                    <div class="ingredient-field ingredient-quantity-field">
                        <label class="ingredient-field-label">Quantidade (${unit})</label>
                        <input type="number" class="${inputClass} text-center" value="${escapeHtml(ing.quantity)}" oninput="updateIngredient(${index}, 'quantity', this.value); _refreshCompactTotals();" placeholder="${unit}" min="0" step="0.1" title="Quantidade em ${unit}">
                    </div>
                </div>
                <div class="ingredient-card-side">
                    <div class="ingredient-energy-chip">
                        <span class="ingredient-energy-label">Energia/100${unit}</span>
                        <span class="ingredient-energy-value ingredient-kcal-summary">${kcalSummary}<span class="text-[10px] text-white/25 ml-1">kcal</span></span>
                    </div>
                    <div class="ingredient-actions">
                        <button onclick="copyIngredient(${index})" class="ingredient-action" title="Duplicar">
                            <i class="ph ph-copy text-sm"></i>
                        </button>
                        <button onclick="removeIngredient(${index})" class="ingredient-action is-danger" title="Remover">
                            <i class="ph ph-trash text-sm"></i>
                        </button>
                    </div>
                </div>
            </div>
            <button type="button" onclick="_toggleInlineNutri(${index})" class="macro-disclosure ${isExpanded ? 'active' : ''}" data-nutri-trigger="${index}" aria-expanded="${isExpanded ? 'true' : 'false'}" aria-controls="ingredient-nutri-${index}" title="Ver/editar nutrientes">
                <div class="macro-disclosure-copy">
                    <span class="macro-disclosure-icon">
                        <i class="ph ph-chart-pie-slice text-sm"></i>
                    </span>
                    <div class="min-w-0">
                        <span class="macro-disclosure-title">Ver macros e detalhes nutricionais</span>
                        <span class="macro-disclosure-sub">Carboidratos, proteínas, gorduras, açúcares, fibras e sódio por 100${unit}</span>
                    </div>
                </div>
                <div class="macro-disclosure-meta">
                    <span class="${completionClass}" data-ing-completion="${index}">${completionLabel}</span>
                    ${warningBadge}
                    ${hasTaco ? '<span class="macro-pill macro-pill-source">TACO</span>' : ''}
                    <i class="ph ph-caret-down nutri-chevron"></i>
                </div>
            </button>
        </div>
        <div id="ingredient-nutri-${index}" class="ing-nutri-expand ${isExpanded ? 'expanded' : ''}" data-nutri-panel="${index}">
            <div class="ing-nutri-inner">
                <div class="px-3 pb-3 pt-1"></div>
            </div>
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

// ---- Step 2 Helper Functions ------------------------------------------------

function _openImportModal() {
    const modal = document.getElementById('import-modal');
    if (modal) modal.classList.remove('hidden');
}

function _closeImportModal() {
    const modal = document.getElementById('import-modal');
    if (modal) modal.classList.add('hidden');
}

function _toggleRunningTotals() {
    if (state.ingredients.length === 0) return;
    state.summaryDockCollapsed = !state.summaryDockCollapsed;
    state.summaryDockManual = true;
    _renderFullRunningTotals();
}

function _refreshCompactTotals() {
    _renderFullRunningTotals();
}

function _renderFullRunningTotals() {
    const el = document.getElementById('summary-dock');
    if (!el) return;
    const totals = computeRunningTotals();
    if (!totals) { el.innerHTML = ''; return; }
    const unit = state.product.portionUnit || 'g';
    const p = totals.per100;
    const fmt = (v, d = 1) => v.toFixed(d);

    const portionSize = parseFloat(state.product.portionSize) || 0;
    const insig = {};
    if (portionSize > 0 && totals.totalWeight > 0) {
        for (const k of Object.keys(p)) {
            insig[k] = _isInsignificant(k, (p[k] * portionSize) / 100);
        }
    }
    const hasInsig = Object.values(insig).some(v => v);
    const isCollapsed = state.summaryDockCollapsed;

    const nutCell = (label, value, key, decPlaces = 1, unitStr = 'g') => {
        const isZero = insig[key];
        const valClass = isZero ? 'text-white/40 line-through decoration-yellow-500/60' : 'text-white';
        const badge = isZero ? '<span class="text-[8px] text-yellow-500/80 font-normal ml-0.5">~0</span>' : '';
        return `<div class="summary-grid-cell">
            <div class="text-[10px] text-terracota-textMuted uppercase mb-0.5">${label}</div>
            <div class="text-sm font-bold ${valClass}">${fmt(value, decPlaces)}${unitStr}${badge}</div>
        </div>`;
    };

    const totalMacroKcal = (p.carbs * 4) + (p.proteins * 4) + (p.totalFat * 9);
    const carbPct = totalMacroKcal > 0 ? Math.round((p.carbs * 4 / totalMacroKcal) * 100) : 0;
    const protPct = totalMacroKcal > 0 ? Math.round((p.proteins * 4 / totalMacroKcal) * 100) : 0;
    const fatPct = totalMacroKcal > 0 ? Math.round((p.totalFat * 9 / totalMacroKcal) * 100) : 0;
    const portionMetric = portionSize > 0 ? `${fmt(portionSize, portionSize % 1 === 0 ? 0 : 1)}${unit}` : 'Não definida';

    const insigNote = hasInsig
        ? `<div class="text-[10px] text-yellow-500/70 mt-3 flex items-center gap-1"><i class="ph ph-info text-xs"></i>Nutrientes riscados serão declarados como 0 ou não significativo (Anexo IV).</div>`
        : '';

    if (isCollapsed) {
        el.innerHTML = `
            <div class="summary-dock-shell is-collapsed">
                <button type="button" class="summary-dock-toggle" onclick="_toggleRunningTotals()" aria-expanded="false">
                    <div class="summary-dock-toggle-copy">
                        <span class="summary-dock-toggle-icon"><i class="ph ph-chart-bar-horizontal"></i></span>
                        <span class="summary-dock-toggle-title">Resumo da fórmula</span>
                    </div>
                    <div class="summary-dock-toggle-metrics">
                        <span>${totals.count} ingrediente${totals.count > 1 ? 's' : ''}</span>
                        <span>${fmt(totals.totalWeight, 0)}${unit}</span>
                        <span>${fmt(p.energyKcal, 0)} kcal</span>
                    </div>
                    <span class="summary-dock-toggle-action">Expandir</span>
                </button>
            </div>
        `;
        return;
    }

    el.innerHTML = `
        <div class="summary-dock-shell">
            <div class="summary-dock-card">
                <div class="summary-dock-head">
                    <div class="flex items-center gap-3 min-w-0">
                        <div class="section-icon">
                            <i class="ph ph-chart-bar-horizontal text-sm"></i>
                        </div>
                        <div class="min-w-0">
                            <p class="text-sm font-semibold text-white">Resumo da fórmula</p>
                            <p class="text-xs text-white/45">Valores vivos da receita atual por 100${unit}. Atualizado em tempo real enquanto você edita os ingredientes.</p>
                        </div>
                    </div>
                    <button type="button" class="summary-dock-minimize" onclick="_toggleRunningTotals()" aria-expanded="true">
                        <i class="ph ph-caret-down text-sm"></i> Minimizar
                    </button>
                </div>
                <div class="summary-dock-metrics">
                    <div class="summary-dock-metric">
                        <span class="summary-dock-metric-label">Ingredientes</span>
                        <strong>${totals.count}</strong>
                    </div>
                    <div class="summary-dock-metric">
                        <span class="summary-dock-metric-label">Peso total</span>
                        <strong>${fmt(totals.totalWeight, 0)}${unit}</strong>
                    </div>
                    <div class="summary-dock-metric">
                        <span class="summary-dock-metric-label">Energia/100${unit}</span>
                        <strong>${fmt(p.energyKcal, 0)} kcal</strong>
                    </div>
                    <div class="summary-dock-metric">
                        <span class="summary-dock-metric-label">Porção atual</span>
                        <strong>${portionMetric}</strong>
                    </div>
                </div>
                <div class="summary-dock-distribution">
                    <div class="flex items-center justify-between gap-3 mb-2">
                        <span class="text-[11px] font-semibold text-white/70 uppercase tracking-wider">Distribuição de macros</span>
                        <span class="text-[11px] text-white/40">Base energética da fórmula</span>
                    </div>
                    <div class="flex items-center gap-2 text-[10px]">
                        <div class="flex-1 h-3 rounded-full overflow-hidden bg-white/5 flex">
                            <div style="width: ${carbPct}%" class="bg-blue-400 transition-all rounded-l-full" title="Carboidratos ${carbPct}%"></div>
                            <div style="width: ${protPct}%" class="bg-emerald-400 transition-all" title="Proteínas ${protPct}%"></div>
                            <div style="width: ${fatPct}%" class="bg-orange-400 transition-all rounded-r-full" title="Gorduras ${fatPct}%"></div>
                        </div>
                        <span class="text-blue-400">${carbPct}% C</span>
                        <span class="text-emerald-400">${protPct}% P</span>
                        <span class="text-orange-400">${fatPct}% G</span>
                    </div>
                </div>
                <div class="summary-dock-grid">
                ${nutCell('Kcal', p.energyKcal, 'energyKcal', 0, '')}
                ${nutCell('Carb', p.carbs, 'carbs')}
                ${nutCell('Prot', p.proteins, 'proteins')}
                ${nutCell('Gord', p.totalFat, 'totalFat')}
                ${nutCell('Sat', p.saturatedFat, 'saturatedFat')}
                ${nutCell('Trans', p.transFat, 'transFat')}
                ${nutCell('Fibra', p.fiber, 'fiber')}
                ${nutCell('Sódio', p.sodium, 'sodium', 0, 'mg')}
                ${nutCell('Aç Tot', p.totalSugars, 'totalSugars')}
                ${nutCell('Aç Adic', p.addedSugars, 'addedSugars')}
                </div>
                <div class="summary-dock-foot">
                    <span>Valores por 100${unit} da receita atual.</span>
                    <span>${state.product.portionDesc ? `Porção: ${escapeHtml(state.product.portionDesc)}` : 'Preencha a porção para revisar a leitura final.'}</span>
                </div>
                ${insigNote}
            </div>
        </div>
    `;
}

function _openNutriPanel(index) {
    // Legacy compat: redirect to inline panel
    _toggleInlineNutri(index);
}

function _closeNutriPanel() {
    // Legacy compat: close any open inline panel
    if (_activeInlineNutriIndex !== -1) {
        _toggleInlineNutri(_activeInlineNutriIndex);
    }
}

function _refreshNutriPanelWarnings(index) {
    // Legacy compat: redirect to inline refresh
    _refreshInlineNutriWarnings(index);
}

function _refreshIngredientRowSummary(index) {
    const ing = state.ingredients[index];
    if (!ing) return;
    const row = document.querySelector(`.ing-row-wrapper[data-ing-index="${index}"]`);
    if (!row) return;
    const nutri = ing.nutritionalInfo;
    const estimated = estimateKcal(nutri);
    const isManual = ing._manualKcal === true;
    const kcalDisplay = isManual ? nutri.energyKcal : (estimated ?? nutri.energyKcal ?? '');
    const kcalSummary = kcalDisplay !== '' && kcalDisplay !== null && kcalDisplay !== undefined ? `${kcalDisplay}` : '—';
    const kcalSpan = row.querySelector('.ingredient-kcal-summary');
    if (kcalSpan) {
        kcalSpan.innerHTML = `${kcalSummary}<span class="text-[10px] text-white/25 ml-1">kcal</span>`;
    }
    const filledCount = INGREDIENT_NUTRIENT_FIELDS.filter(f => nutri[f] !== '' && nutri[f] !== null && nutri[f] !== undefined).length;
    const warnings = getIngredientWarnings(nutri, ing);
    const hardWarnings = warnings.filter(w => w.type !== 'info');

    const completionEl = row.querySelector(`[data-ing-completion="${index}"]`);
    if (completionEl) {
        completionEl.className = filledCount === INGREDIENT_NUTRIENT_FIELDS.length ? 'macro-pill macro-pill-success' : 'macro-pill';
        completionEl.innerHTML = filledCount === INGREDIENT_NUTRIENT_FIELDS.length
            ? '<i class="ph ph-check-circle"></i>Completo'
            : `${filledCount}/10 campos`;
    }

    const warningEl = row.querySelector(`[data-ing-warning="${index}"]`);
    if (warningEl) {
        if (hardWarnings.length > 0) {
            warningEl.className = 'macro-pill macro-pill-warning';
            warningEl.innerHTML = `<i class="ph ph-warning-diamond"></i>${hardWarnings.length} aviso${hardWarnings.length > 1 ? 's' : ''}`;
        } else {
            warningEl.className = 'macro-pill hidden';
            warningEl.innerHTML = '';
        }
    }
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
    _activeInlineNutriIndex = state.ingredients.length - 1;
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
    if (_activeInlineNutriIndex > index) {
        _activeInlineNutriIndex += 1;
    }
    renderStep2(document.getElementById('wizard-content'));
    showToast('Ingrediente duplicado.', 'info', 2000);
}

function removeIngredient(index) {
    pushUndo();
    if (_activeInlineNutriIndex === index) {
        _activeInlineNutriIndex = -1;
    } else if (_activeInlineNutriIndex > index) {
        _activeInlineNutriIndex -= 1;
    }
    state.ingredients.splice(index, 1);
    renderStep2(document.getElementById('wizard-content'));
}

function toggleIngredientExpand(index) {
    // Nutrient editing now uses side panel
    _openNutriPanel(index);
}

function toggleAllIngredients(expand) {
    // No-op — inline expand/collapse replaced by side panel
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
        _activeInlineNutriIndex = -1;
        state.summaryDockCollapsed = false;
        state.summaryDockManual = false;
        renderStep2(document.getElementById('wizard-content'));
        showToast(`${count} ingrediente${count > 1 ? 's' : ''} removido${count > 1 ? 's' : ''}`, 'info');
    }
}

function filterIngredients(query) {
    const q = query.toLowerCase().trim();
    document.querySelectorAll('.ing-row-wrapper').forEach(row => {
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
    const ing = state.ingredients[index];
    if (!ing) return;
    const nutri = ing.nutritionalInfo;

    // Auto kcal — recalculate from macros unless user explicitly typed kcal
    const estimated = estimateKcal(nutri);
    const isManual = ing._manualKcal === true;
    if (!isManual && estimated !== null) {
        nutri.energyKcal = estimated;
    }

    // Update the row's inline summary
    _refreshIngredientRowSummary(index);

    if (_activeInlineNutriIndex === index) {
        _refreshNutriPanelWarnings(index);
    }

    _refreshCompactTotals();
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

    let hasIngWarnings = false;
    for (const ing of state.ingredients) {
        const w = getIngredientWarnings(ing.nutritionalInfo || {}, ing);
        if (w.some(x => x.type !== 'info')) { hasIngWarnings = true; break; }
    }
    checks.push({ ok: !hasIngWarnings, label: 'Nenhum aviso de consistência nos ingredientes' });

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
    const icon = allPass ? 'ph-shield-check' : 'ph-shield-warning';
    const summaryText = allPass ? `${passCount}/${checks.length} verificações OK` : `${checks.length - passCount} pendência${checks.length - passCount > 1 ? 's' : ''}`;

    return `
        <details class="mb-4 bg-white/[0.02] border border-white/[0.06] rounded-xl overflow-hidden group/comp hover:border-white/[0.1] transition-all duration-300">
            <summary class="px-4 py-2.5 cursor-pointer flex items-center select-none hover:bg-white/[0.02] transition-colors">
                <div class="w-6 h-6 rounded-md ${allPass ? 'bg-emerald-500/10' : 'bg-yellow-500/10'} flex items-center justify-center mr-2 flex-shrink-0">
                    <i class="ph ${icon} text-sm ${headerColor}"></i>
                </div>
                <span class="text-[11px] font-semibold ${headerColor}">${summaryText}</span>
                <i class="ph ph-caret-down text-xs text-white/30 ml-auto transition-transform duration-300 group-open/comp:rotate-180 group-hover/comp:text-terracota-cyan"></i>
            </summary>
            <div class="px-4 pb-3 grid grid-cols-1 sm:grid-cols-2 gap-1">
                ${checks.map(c => {
                    const ci = c.ok ? 'ph-check-circle' : 'ph-x-circle';
                    const cc = c.ok ? 'text-emerald-400' : 'text-red-400/70';
                    return `<div class="flex items-center gap-1.5 text-[11px] ${cc}"><i class="ph ${ci} text-xs flex-shrink-0"></i>${c.label}</div>`;
                }).join('')}
            </div>
        </details>
    `;
}

function renderStep3Preview(container) {
    const allData = state.calculatedData;
    const product = state.product;
    const canGenerate = !state.quotaInfo || state.quotaInfo.canCreate !== false;

    const warningHtml = !canGenerate
        ? `<div class="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl text-center">
                <p class="text-yellow-300 text-sm font-medium">Limite de tabelas atingido.</p>
                <p class="text-yellow-300/70 text-xs mt-1">Visualize a prévia, mas para salvar faça upgrade.</p>
                <a href="/account/upgrade" class="inline-block mt-2 px-5 py-2 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white text-xs font-bold rounded-lg hover:scale-105 transition-all">Fazer Upgrade</a>
           </div>`
        : '';

    const complianceHtml = _buildComplianceChecklist();

    const calcWarnings = allData.calculationWarnings || [];
    const calcWarnHtml = calcWarnings.length > 0
        ? `<details class="mb-3 bg-yellow-500/10 border border-yellow-500/20 rounded-xl overflow-hidden group/warn hover:border-yellow-500/30 transition-all duration-300">
              <summary class="px-3 py-2 cursor-pointer text-[10px] font-bold text-yellow-400 uppercase tracking-wider flex items-center gap-2 select-none hover:bg-yellow-500/5 transition-colors">
                <div class="w-5 h-5 rounded-md bg-yellow-500/15 flex items-center justify-center flex-shrink-0"><i class="ph ph-warning text-xs text-yellow-400"></i></div>
                Avisos do cálculo (${calcWarnings.length})
                <i class="ph ph-caret-down text-xs text-yellow-400/50 ml-auto transition-transform duration-300 group-open/warn:rotate-180"></i>
              </summary>
              <div class="px-3 pb-2">${calcWarnings.map(w => `<p class="text-[11px] text-yellow-300/80 flex items-center gap-1 mt-1"><i class="ph ph-caret-right text-xs"></i>${escapeHtml(w)}</p>`).join('')}</div>
           </details>`
        : '';

    container.innerHTML = `
        <div class="space-y-3">
            <div class="text-center">
                <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-300 text-xs">
                    <i class="ph ph-eye text-sm"></i> Prévia — revise antes de gerar
                </span>
            </div>
            ${complianceHtml}
            ${calcWarnHtml}
            ${warningHtml}
            ${buildFrontalStampsHtml(allData, product)}
            <div class="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-4 sm:p-6 shadow-xl">
                ${buildNutritionTableHtml(allData, product)}
            </div>
            <div class="flex justify-center gap-3 pt-2 no-print">
                ${canGenerate ? `
                <button id="btn-generate" onclick="finalizeTable()" class="px-8 py-3 bg-gradient-to-r from-terracota-purple to-purple-600 text-white font-bold rounded-xl hover:scale-[1.03] shadow-lg shadow-purple-500/20 transition-all flex items-center gap-2 text-sm">
                    <i class="ph-bold ph-check text-lg"></i> Gerar Tabela
                </button>` : ''}
            </div>
            <div class="flex justify-center gap-2 no-print">
                <button onclick="copyTableToClipboard()" class="px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/50 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.15] transition-all flex items-center gap-1.5 text-xs" title="Copiar texto">
                    <i class="ph ph-clipboard-text text-sm"></i> Copiar
                </button>
                <button onclick="goToStep(2)" class="px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/50 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.15] transition-all flex items-center gap-1.5 text-xs" title="Editar ingredientes">
                    <i class="ph ph-pencil-simple text-sm"></i> Ingredientes
                </button>
                <button onclick="goToStep(1)" class="px-3 py-2 rounded-xl bg-white/[0.03] border border-white/[0.08] text-white/50 hover:text-white hover:bg-white/[0.08] hover:border-white/[0.15] transition-all flex items-center gap-1.5 text-xs" title="Editar produto">
                    <i class="ph ph-gear text-sm"></i> Produto
                </button>
            </div>
        </div>
    `;
}

function renderStep3Finalized(container) {
    const allData = state.calculatedData;
    const product = state.product;
    const q = state.quotaInfo;
    const canCreateMore = q && q.canCreate;

    container.innerHTML = `
        <div class="space-y-3">
            <div class="text-center">
                <div class="inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded-full celebration-glow">
                    <i class="ph-bold ph-check-circle text-lg text-emerald-400"></i>
                    <span class="text-emerald-300 text-sm font-semibold">Tabela gerada com sucesso!</span>
                </div>
            </div>
            ${quotaBadgeFullHtml()}
            ${buildFrontalStampsHtml(allData, product)}
            <div class="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-4 sm:p-6 shadow-xl">
                ${buildNutritionTableHtml(allData, product)}
            </div>
            <div id="comparison-container"></div>
            <div class="flex justify-center gap-3 pt-2 no-print">
                <button onclick="printTable()" class="px-6 py-2.5 bg-terracota-cyan text-terracota-deepDark font-bold rounded-xl hover:bg-white shadow-lg shadow-cyan-500/20 transition-all flex items-center gap-2 text-sm">
                    <i class="ph-bold ph-printer text-lg"></i> Imprimir / PDF
                </button>
                ${canCreateMore ? `
                <button onclick="startNewTable()" class="px-6 py-2.5 bg-terracota-purple/80 text-white font-semibold rounded-xl hover:bg-terracota-purple transition-all flex items-center gap-2 text-sm">
                    <i class="ph ph-plus text-lg"></i> Nova Tabela
                </button>` : `
                <a href="/account/upgrade" class="px-6 py-2.5 bg-gradient-to-r from-terracota-purple to-terracota-cyan text-white font-semibold rounded-xl hover:scale-[1.03] transition-all flex items-center gap-2 text-sm no-underline">
                    <i class="ph ph-trend-up text-lg"></i> Upgrade
                </a>`}
            </div>
            <div class="flex justify-center gap-2 no-print">
                <button onclick="copyTableToClipboard()" class="p-2 rounded-lg text-terracota-textMuted hover:text-white hover:bg-white/[0.06] transition-colors" title="Copiar texto">
                    <i class="ph ph-clipboard-text text-base"></i>
                </button>
                <button onclick="exportTableAsPng()" class="p-2 rounded-lg text-terracota-textMuted hover:text-white hover:bg-white/[0.06] transition-colors" title="Baixar PNG">
                    <i class="ph ph-image text-base"></i>
                </button>
                <button onclick="openTableComparison()" class="p-2 rounded-lg text-terracota-textMuted hover:text-white hover:bg-white/[0.06] transition-colors" title="Comparar">
                    <i class="ph ph-arrows-left-right text-base"></i>
                </button>
                <a href="/account/" class="p-2 rounded-lg text-terracota-textMuted hover:text-white hover:bg-white/[0.06] transition-colors no-underline" title="Minha Conta">
                    <i class="ph ph-user-circle text-base"></i>
                </a>
            </div>
        </div>
    `;
    // Celebration glow animation
    _triggerCelebration();
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

// ---- Celebration animation --------------------------------------------------

function _triggerCelebration() {
    const badge = document.querySelector('.celebration-glow');
    if (!badge) return;
    badge.classList.add('celebrating');
    setTimeout(() => badge.classList.remove('celebrating'), 2500);
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
    state.maxStepReached = 0;
    state.summaryDockCollapsed = false;
    state.summaryDockManual = false;
    _activeInlineNutriIndex = -1;
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
        _activeInlineNutriIndex = -1;
        state.summaryDockCollapsed = false;
        state.summaryDockManual = false;
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
            state.maxStepReached = draft.currentStep || 1;
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
        const row = e.target.closest('.ing-row-wrapper');
        if (!row) return;
        // Only allow drag from handle
        if (!e.target.closest('.drag-handle')) { e.preventDefault(); return; }
        dragIndex = parseInt(row.getAttribute('data-ing-index'));
        row.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });

    list.addEventListener('dragend', (e) => {
        const row = e.target.closest('.ing-row-wrapper');
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
        const target = e.target.closest('.ing-row-wrapper');
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
