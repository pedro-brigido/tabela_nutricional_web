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
        gluten: 'Não contém glúten'
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
    toastTimeout: null
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
    await fetchQuota();

    if (state.quotaInfo && !state.quotaInfo.canCreate) {
        await fetchLatestTable();
        renderQuotaExhausted();
    } else {
        renderWelcome();
    }
    setupNavigation();
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

    btnBack.style.display = state.currentStep > 0 && state.currentStep < 3 ? 'block' : 'none';
    btnNext.style.display = state.currentStep > 0 && state.currentStep < 3 ? 'block' : 'none';

    if (state.currentStep > 0 && state.currentStep <= 3) {
        progress.innerHTML = renderProgressBar(state.currentStep);
        progress.style.display = 'block';
    } else {
        progress.style.display = 'none';
    }

    switch (state.currentStep) {
        case 1:
            renderStep1(content);
            btnNext.innerText = 'Próximo: Ingredientes';
            break;
        case 2:
            renderStep2(content);
            btnNext.innerText = 'Calcular Tabela';
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
        const bgCircle = active ? 'bg-terracota-cyan text-terracota-deepDark shadow-[0_0_15px_rgba(0,196,204,0.4)]' : 'bg-terracota-deepDark border border-white/20 text-terracota-textLight';
        const ring = current ? 'ring-4 ring-terracota-cyan/20' : '';
        const textClass = active ? 'text-terracota-cyan' : 'text-terracota-textLight/50';
        return `
            <div class="relative z-10 flex flex-col items-center">
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

    container.innerHTML = `
        <div class="space-y-8 max-w-lg mx-auto">
            <h3 class="text-2xl font-bold text-white font-heading text-center mb-8">Informações do Produto</h3>
            <div>
                <label class="${labelClass}">Nome do Produto</label>
                <input type="text" id="input-name" value="${escapeHtml(state.product.name)}" class="${inputClass}" placeholder="Ex: Bolo de Chocolate">
            </div>
            <div class="grid grid-cols-2 gap-6">
                <div>
                    <label class="${labelClass}">Porção (g ou ml)</label>
                    <input type="number" id="input-portion" value="${escapeHtml(state.product.portionSize)}" class="${inputClass}" placeholder="Ex: 60">
                </div>
                <div>
                    <label class="${labelClass}">Medida Caseira</label>
                    <input type="text" id="input-desc" value="${escapeHtml(state.product.portionDesc)}" class="${inputClass}" placeholder="Ex: 1 fatia">
                </div>
            </div>
            <div>
                <label class="${labelClass}">Declaração de Alergênicos</label>
                <textarea id="input-allergens" rows="3" class="${inputClass}" placeholder="Ex: ALÉRGICOS: CONTÉM OVO E TRIGO.">${escapeHtml(state.product.allergens)}</textarea>
            </div>
            <div>
                <label class="${labelClass}">Glúten</label>
                <select id="input-gluten" class="${inputClass} appearance-none cursor-pointer">
                    <option value="Não contém glúten" class="bg-terracota-deepDark" ${state.product.gluten === 'Não contém glúten' ? 'selected' : ''}>Não contém glúten</option>
                    <option value="Contém glúten" class="bg-terracota-deepDark" ${state.product.gluten === 'Contém glúten' ? 'selected' : ''}>Contém glúten</option>
                </select>
            </div>
        </div>
    `;

    document.getElementById('input-name').addEventListener('input', (e) => state.product.name = e.target.value);
    document.getElementById('input-portion').addEventListener('input', (e) => state.product.portionSize = e.target.value);
    document.getElementById('input-desc').addEventListener('input', (e) => state.product.portionDesc = e.target.value);
    document.getElementById('input-allergens').addEventListener('input', (e) => state.product.allergens = e.target.value);
    document.getElementById('input-gluten').addEventListener('change', (e) => state.product.gluten = e.target.value);
}

// ---- Step 2: Ingredients ----------------------------------------------------

function renderStep2(container) {
    container.innerHTML = `
        <div class="space-y-6">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-2xl font-bold text-white font-heading">Ingredientes</h3>
                <button onclick="addIngredient()" class="text-xs font-bold uppercase tracking-wider px-4 py-2 bg-white/10 text-terracota-cyan rounded-full hover:bg-terracota-cyan hover:text-terracota-deepDark transition-colors">
                    + Adicionar Novo
                </button>
            </div>
            <div id="drop-zone" class="border-2 border-dashed border-white/20 rounded-xl p-8 text-center transition-all bg-white/5 hover:bg-white/10 hover:border-terracota-cyan group relative">
                <input type="file" id="file-upload" class="hidden" accept=".xlsx" onchange="handleExcelUpload(this.files[0])">
                <div class="pointer-events-none">
                    <div class="mx-auto w-12 h-12 mb-4 text-terracota-textLight group-hover:text-terracota-cyan transition-colors">
                        <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    </div>
                    <p class="text-terracota-textLight text-sm mb-2">Arraste e solte seu arquivo Excel (.xlsx) aqui</p>
                    <p class="text-xs text-terracota-textLight/50 mb-4">ou</p>
                    <button onclick="document.getElementById('file-upload').click()" class="px-4 py-2 bg-white/10 text-white text-xs font-bold uppercase tracking-wider rounded-lg hover:bg-white/20 transition-all pointer-events-auto">
                        Selecionar Arquivo
                    </button>
                </div>
                <div id="upload-loading" class="absolute inset-0 bg-terracota-deepDark/90 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center hidden">
                    <div class="w-8 h-8 border-2 border-terracota-cyan border-t-transparent rounded-full animate-spin mb-3"></div>
                    <p class="text-xs text-terracota-cyan font-bold uppercase tracking-wider">Processando...</p>
                </div>
            </div>
            <div id="ingredients-list" class="space-y-4">
                ${state.ingredients.length === 0 ? '<div class="text-center py-4"><p class="text-terracota-textLight text-xs">Ou adicione manualmente abaixo</p></div>' : ''}
            </div>
        </div>
    `;

    if (state.ingredients.length > 0) {
        const list = document.getElementById('ingredients-list');
        list.innerHTML = '';
        state.ingredients.forEach((ing, index) => {
            list.appendChild(createIngredientRow(ing, index));
        });
    }
    setupDragAndDrop();
}

function createIngredientRow(ing, index) {
    const inputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1";
    const labelClass = "block text-[10px] text-terracota-textLight/70 mb-1 uppercase";
    const nutri = ing.nutritionalInfo || {};
    const el = document.createElement('div');
    el.className = 'bg-white/5 border border-white/10 rounded-xl p-5 relative group hover:bg-white/10 transition-colors';
    el.innerHTML = `
        <div class="grid grid-cols-12 gap-4 items-start">
            <div class="col-span-4">
                <label class="${labelClass}">Nome</label>
                <input type="text" class="${inputClass}" value="${escapeHtml(ing.name)}" oninput="updateIngredient(${index}, 'name', this.value)" placeholder="Farinha">
            </div>
            <div class="col-span-2">
                <label class="${labelClass}">Qtd (g)</label>
                <input type="number" class="${inputClass}" value="${escapeHtml(ing.quantity)}" oninput="updateIngredient(${index}, 'quantity', this.value)" placeholder="100">
            </div>
            <div class="col-span-6 grid grid-cols-4 gap-2 bg-black/20 p-3 rounded-lg border border-white/5">
                <div class="col-span-4 text-[10px] font-bold text-terracota-cyan uppercase tracking-wider mb-1">Nutricional (por 100g)</div>
                <div>
                    <label class="block text-[8px] text-slate-400">Kcal</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.energyKcal ?? ''}" oninput="updateIngredientNutri(${index}, 'energyKcal', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Carb</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.carbs ?? ''}" oninput="updateIngredientNutri(${index}, 'carbs', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Prot</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.proteins ?? ''}" oninput="updateIngredientNutri(${index}, 'proteins', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Gord</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.totalFat ?? ''}" oninput="updateIngredientNutri(${index}, 'totalFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Sat</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.saturatedFat ?? ''}" oninput="updateIngredientNutri(${index}, 'saturatedFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Trans</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.transFat ?? ''}" oninput="updateIngredientNutri(${index}, 'transFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Fibra</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.fiber ?? ''}" oninput="updateIngredientNutri(${index}, 'fiber', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Sódio</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${nutri.sodium ?? ''}" oninput="updateIngredientNutri(${index}, 'sodium', this.value)">
                </div>
            </div>
        </div>
        <button onclick="removeIngredient(${index})" class="absolute -top-2 -right-2 bg-red-500/80 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity shadow-lg hover:bg-red-600">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
    `;
    return el;
}

function addIngredient() {
    state.ingredients.push({
        id: Date.now(),
        name: '',
        quantity: '',
        nutritionalInfo: { energyKcal: '', carbs: '', proteins: '', totalFat: '', saturatedFat: '', transFat: '', fiber: '', sodium: '' }
    });
    renderStep2(document.getElementById('wizard-content'));
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
}

// ---- Validation -------------------------------------------------------------

function validateStep(step) {
    if (step === 1) {
        if (!state.product.name) { showToast('Informe o nome do produto.', 'warning'); return false; }
        if (!state.product.portionSize) { showToast('Informe o tamanho da porção.', 'warning'); return false; }
        return true;
    }
    if (step === 2) {
        if (state.ingredients.length === 0) { showToast('Adicione pelo menos um ingrediente.', 'warning'); return false; }
        return true;
    }
    return true;
}

// ---- Calculate (Preview only — no save) -------------------------------------

async function calculateResult() {
    const btn = document.getElementById('btn-next');
    const origText = btn.innerText;
    btn.innerText = 'Calculando...';
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
                sodium: parseFloat(ing.nutritionalInfo?.sodium) || 0
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
        btn.innerText = origText;
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
                Editar
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
    state.product = { name: '', portionSize: '', portionDesc: '', allergens: '', gluten: 'Não contém glúten' };
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
    const portion = allData.perPortion || allData;
    const energyKj = Math.round((portion.energy?.raw ?? 0) * 4.184);
    const transVd = portion.transFat?.vd === '' ? '**' : (portion.transFat?.vd ?? '**');

    const portionSize = product.portionSize || product.portion_size || '';
    const portionDesc = product.portionDesc || product.portion_desc || '';
    const glutenText = product.gluten || product.gluten_status || '';
    const allergensText = product.allergens || '';

    return `
        <div id="nutritional-table-print-area" style="max-width: 36rem; margin: 0 auto; padding: 2rem; background: #ffffff; color: #000000; border-radius: 0.75rem; border: 1px solid #e5e7eb;">
            <h3 style="font-size: 1.25rem; font-weight: 700; color: #000; border-bottom: 2px solid #000; padding-bottom: 0.5rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.05em;">Informação Nutricional</h3>
            <div style="margin-bottom: 1rem; font-size: 0.875rem; color: #000; font-weight: 500;">
                <p>Porção de: <strong>${escapeHtml(portionSize)} g</strong> (${escapeHtml(portionDesc || '-')})</p>
            </div>
            <table style="width: 100%; font-size: 0.875rem; margin-bottom: 1.5rem; border-collapse: collapse; color: #000; background: #fff;">
                <thead>
                    <tr style="border-bottom: 2px solid #000;">
                        <th style="padding: 0.25rem 0; text-align: left; font-weight: 700; color: #000; background: #fff;">Quantidade por porção</th>
                        <th style="padding: 0.25rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;"></th>
                        <th style="padding: 0.25rem 0; text-align: right; font-weight: 700; color: #000; background: #fff; min-width: 60px;">% VD (*)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Valor Energético</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.energy?.display ?? 0} kcal = ${energyKj} kJ</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.energy?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Carboidratos</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.carbs?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.carbs?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Proteínas</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.proteins?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.proteins?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Gorduras Totais</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.totalFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.totalFat?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Gorduras Saturadas</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.saturatedFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.saturatedFat?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0 0.375rem 1rem; color: #4b5563; background: #fff;">Gorduras Trans</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.transFat?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${transVd}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Fibra Alimentar</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.fiber?.display ?? 0} g</td>
                        <td style="padding: 0.375rem 0; text-align: right; font-weight: 700; color: #000; background: #fff;">${portion.fiber?.vd ?? 0}</td>
                    </tr>
                    <tr style="border-bottom: 1px solid #d1d5db;">
                        <td style="padding: 0.375rem 0; color: #000; background: #fff;">Sódio</td>
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
        renderStep2(document.getElementById('wizard-content'));
    } catch (e) {
        console.error(e);
        showToast('Erro ao ler o arquivo Excel.', 'error');
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}
