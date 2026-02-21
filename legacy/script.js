/**
 * Main Application Logic
 * Orchestrates the wizard flow and UI updates.
 */

// State Management
const state = {
    currentStep: 0, // 0 = Welcome, 1 = Product, 2 = Ingredients, 3 = Result
    product: {
        name: '',
        portionSize: '',
        portionDesc: '',
        allergens: '',
        gluten: 'Não contém glúten'
    },
    ingredients: [], // Array of { id, name, quantity, nutritionalInfo: {} }
    calculatedData: null
};

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

function initApp() {
    renderWelcome();
    setupNavigation();
}

function setupNavigation() {
    document.getElementById('btn-back').addEventListener('click', () => {
        if (state.currentStep > 1) {
            goToStep(state.currentStep - 1);
        }
    });

    document.getElementById('btn-next').addEventListener('click', () => {
        if (validateStep(state.currentStep)) {
            if (state.currentStep === 2) {
                // Calculate before moving to result
                calculateResult();
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

    // Reset buttons
    btnBack.style.display = state.currentStep > 0 ? 'block' : 'none';
    btnNext.style.display = state.currentStep > 0 && state.currentStep < 3 ? 'block' : 'none';

    // Update Progress Bar
    if (state.currentStep > 0) {
        progress.innerHTML = renderProgressBar(state.currentStep);
        progress.style.display = 'block';
    } else {
        progress.style.display = 'none';
    }

    // Render Content
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
    return `
        <div class="flex items-center justify-between relative">
            <div class="absolute w-full top-1/2 transform -translate-y-1/2 h-0.5 bg-white/10 -z-0"></div>
            ${steps.map((label, idx) => {
        const s = idx + 1;
        const active = s <= step;
        const current = s === step;
        // Styles
        const bgCircle = active ? 'bg-terracota-cyan text-terracota-deepDark shadow-[0_0_15px_rgba(0,196,204,0.4)]' : 'bg-terracota-deepDark border border-white/20 text-terracota-textLight';
        const ring = current ? 'ring-4 ring-terracota-cyan/20' : '';
        const textClass = active ? 'text-terracota-cyan' : 'text-terracota-textLight/50';

        return `
                    <div class="relative z-10 flex flex-col items-center">
                        <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm transition-all duration-300 ${bgCircle} ${ring}">
                            ${s}
                        </div>
                        <span class="mt-3 text-xs font-medium uppercase tracking-wider ${textClass}">${label}</span>
                    </div>
                `;
    }).join('')}
        </div>
    `;
}

// --- Steps Rendering ---

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
            <button onclick="goToStep(1)" class="px-10 py-4 bg-terracota-cyan text-terracota-deepDark text-lg font-bold rounded-xl hover:bg-white hover:scale-105 shadow-[0_0_30px_rgba(0,196,204,0.3)] transition-all">
                Iniciar Novo Produto
            </button>
        </div>
    `;
}

function renderStep1(container) {
    const inputClass = "w-full px-4 py-3 bg-black/20 border border-white/10 rounded-lg text-white placeholder-white/30 focus:ring-2 focus:ring-terracota-cyan focus:border-transparent outline-none transition-all";
    const labelClass = "block text-sm font-medium text-terracota-textLight mb-2 uppercase tracking-wide text-[10px]";

    container.innerHTML = `
        <div class="space-y-8 max-w-lg mx-auto">
            <h3 class="text-2xl font-bold text-white font-heading text-center mb-8">Informações do Produto</h3>
            
            <div>
                <label class="${labelClass}">Nome do Produto</label>
                <input type="text" id="input-name" value="${state.product.name}" 
                    class="${inputClass}"
                    placeholder="Ex: Bolo de Chocolate">
            </div>

            <div class="grid grid-cols-2 gap-6">
                <div>
                    <label class="${labelClass}">Porção (g ou ml)</label>
                    <input type="number" id="input-portion" value="${state.product.portionSize}" 
                        class="${inputClass}"
                        placeholder="Ex: 60">
                </div>
                 <div>
                    <label class="${labelClass}">Medida Caseira</label>
                    <input type="text" id="input-desc" value="${state.product.portionDesc}" 
                        class="${inputClass}"
                        placeholder="Ex: 1 fatia">
                </div>
            </div>

            <div>
                <label class="${labelClass}">Declaração de Alergênicos</label>
                <textarea id="input-allergens" rows="3" class="${inputClass}"
                    placeholder="Ex: ALÉRGICOS: CONTÉM OVO E TRIGO.">${state.product.allergens}</textarea>
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

    // Bind events
    document.getElementById('input-name').addEventListener('input', (e) => state.product.name = e.target.value);
    document.getElementById('input-portion').addEventListener('input', (e) => state.product.portionSize = e.target.value);
    document.getElementById('input-desc').addEventListener('input', (e) => state.product.portionDesc = e.target.value);
    document.getElementById('input-allergens').addEventListener('input', (e) => state.product.allergens = e.target.value);
    document.getElementById('input-gluten').addEventListener('change', (e) => state.product.gluten = e.target.value);
}

function renderStep2(container) {
    container.innerHTML = `
        <div class="space-y-6">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-2xl font-bold text-white font-heading">Ingredientes</h3>
                <button onclick="addIngredient()" class="text-xs font-bold uppercase tracking-wider px-4 py-2 bg-white/10 text-terracota-cyan rounded-full hover:bg-terracota-cyan hover:text-terracota-deepDark transition-colors">
                    + Adicionar Novo
                </button>
            </div>

            <!-- Drag and Drop Area -->
            <div id="drop-zone" class="border-2 border-dashed border-white/20 rounded-xl p-8 text-center transition-all bg-white/5 hover:bg-white/10 hover:border-terracota-cyan group relative">
                <input type="file" id="file-upload" class="hidden" accept=".xlsx, .xls" onchange="handleExcelUpload(this.files[0])">
                
                <div class="pointer-events-none">
                    <div class="mx-auto w-12 h-12 mb-4 text-terracota-textLight group-hover:text-terracota-cyan transition-colors">
                        <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                    </div>
                    <p class="text-terracota-textLight text-sm mb-2">Arraste e solte seu arquivo Excel aqui</p>
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
                ${state.ingredients.length === 0 ? `
                    <div class="text-center py-4">
                        <p class="text-terracota-textLight text-xs">Ou adicione manualmente abaixo</p>
                    </div>
                ` : ''}
                <!-- Ingredients rendered here -->
            </div>
        </div>
    `;

    // Render existing ingredients
    if (state.ingredients.length > 0) {
        const list = document.getElementById('ingredients-list');
        list.innerHTML = '';
        state.ingredients.forEach((ing, index) => {
            list.appendChild(createIngredientRow(ing, index));
        });
    }

    // Setup Drag and Drop events
    setupDragAndDrop();
}

function createIngredientRow(ing, index) {
    const inputClass = "w-full text-sm bg-black/20 border-white/10 rounded text-white focus:ring-1 focus:ring-terracota-cyan border px-2 py-1";
    const labelClass = "block text-[10px] text-terracota-textLight/70 mb-1 uppercase";
    const el = document.createElement('div');
    el.className = 'bg-white/5 border border-white/10 rounded-xl p-5 relative group hover:bg-white/10 transition-colors';
    el.innerHTML = `
        <div class="grid grid-cols-12 gap-4 items-start">
            <div class="col-span-4">
                <label class="${labelClass}">Nome</label>
                <input type="text" class="${inputClass}" value="${ing.name}" oninput="updateIngredient(${index}, 'name', this.value)" placeholder="Farinha">
            </div>
            <div class="col-span-2">
                <label class="${labelClass}">Qtd (g)</label>
                <input type="number" class="${inputClass}" value="${ing.quantity}" oninput="updateIngredient(${index}, 'quantity', this.value)" placeholder="100">
            </div>
            
            <div class="col-span-6 grid grid-cols-4 gap-2 bg-black/20 p-3 rounded-lg border border-white/5">
                <div class="col-span-4 text-[10px] font-bold text-terracota-cyan uppercase tracking-wider mb-1">Nutricional (por 100g)</div>
                
                <div>
                    <label class="block text-[8px] text-slate-400">Kcal</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.energyKcal || ''}" oninput="updateIngredientNutri(${index}, 'energyKcal', this.value)">
                </div>
                 <div>
                    <label class="block text-[8px] text-slate-400">Carb</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.carbs || ''}" oninput="updateIngredientNutri(${index}, 'carbs', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Prot</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.proteins || ''}" oninput="updateIngredientNutri(${index}, 'proteins', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Gord</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.totalFat || ''}" oninput="updateIngredientNutri(${index}, 'totalFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Sat</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.saturatedFat || ''}" oninput="updateIngredientNutri(${index}, 'saturatedFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Trans</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.transFat || ''}" oninput="updateIngredientNutri(${index}, 'transFat', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Fibra</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.fiber || ''}" oninput="updateIngredientNutri(${index}, 'fiber', this.value)">
                </div>
                <div>
                    <label class="block text-[8px] text-slate-400">Sódio</label>
                    <input type="number" class="${inputClass} text-xs py-0.5" value="${ing.nutritionalInfo.sodium || ''}" oninput="updateIngredientNutri(${index}, 'sodium', this.value)">
                </div>
            </div>
        </div>
        <button onclick="removeIngredient(${index})" class="absolute -top-2 -right-2 bg-red-500/80 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity shadow-lg hover:bg-red-600">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
        </button>
    `;
    return el;
}

// Logic Helpers

function addIngredient() {
    state.ingredients.push({
        id: Date.now(),
        name: '',
        quantity: '',
        nutritionalInfo: {
            energyKcal: '', carbs: '', proteins: '', totalFat: '', saturatedFat: '', transFat: '', fiber: '', sodium: ''
        }
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
    state.ingredients[index].nutritionalInfo[field] = parseFloat(value) || 0;
}

function validateStep(step) {
    if (step === 1) {
        if (!state.product.name) return alert('Por favor, informe o nome do produto.');
        if (!state.product.portionSize) return alert('Por favor, informe o tamanho da porção.');
        return true;
    }
    if (step === 2) {
        if (state.ingredients.length === 0) return alert('Adicione pelo menos um ingrediente.');
        // Could add more validation here
        return true;
    }
    return true;
}

function calculateResult() {
    try {
        const ingredients = state.ingredients;
        const portionSize = parseFloat(state.product.portionSize);

        state.calculatedData = AnvisaCalculator.calculate(ingredients, portionSize);
    } catch (e) {
        console.error("Calculation Error", e);
        alert('Erro ao calcular. Verifique os valores inseridos.');
    }
}

function renderStep3(container) {
    if (!state.calculatedData) {
        container.innerHTML = '<div class="text-red-400 text-center">Erro ao carregar dados calculados.</div>';
        return;
    }

    const allData = state.calculatedData;
    const portion = allData.perPortion;
    const product = state.product;

    container.innerHTML = `
        <!-- Print Area: Uses white background for regulation compliance -->
        <div id="nutritional-table-print-area" class="max-w-xl mx-auto p-8 bg-white text-black shadow-2xl rounded-xl border border-white/10 overflow-hidden transform transition-all hover:scale-[1.01]">
            <h3 class="text-xl font-bold text-black border-b-2 border-black pb-2 mb-4 uppercase tracking-wider font-heading">Informação Nutricional</h3>

            <div class="mb-4 text-sm text-black font-medium">
                <p>Porção de: <span class="font-bold">${product.portionSize} g</span> (${product.portionDesc})</p>
            </div>

            <table class="w-full text-sm mb-6 border-collapse">
                <thead>
                    <tr class="border-b-2 border-black">
                        <th class="py-1 text-left font-bold text-black">Quantidade por porção</th>
                        <th class="py-1 text-right font-bold text-black min-w-[60px]">% VD (*)</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-300">
                    <tr>
                        <td class="py-1.5 text-black">Valor Energético</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.energy.display} kcal = ${Math.round(portion.energy.raw * 4.184)} kJ</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.energy.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 text-black">Carboidratos</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.carbs.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.carbs.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 text-black">Proteínas</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.proteins.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.proteins.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 text-black">Gorduras Totais</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.totalFat.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.totalFat.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 pl-4 text-gray-600">Gorduras Saturadas</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.saturatedFat.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.saturatedFat.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 pl-4 text-gray-600">Gorduras Trans</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.transFat.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">**</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 text-black">Fibra Alimentar</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.fiber.display} g</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.fiber.vd}</td>
                    </tr>
                    <tr>
                        <td class="py-1.5 text-black">Sódio</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.sodium.display} mg</td>
                        <td class="py-1.5 text-right font-bold text-black">${portion.sodium.vd}</td>
                    </tr>
                </tbody>
            </table>

            <p class="text-[10px] leading-tight text-gray-600 mb-6">
                (*) % Valores Diários de referência com base em uma dieta de 2.000 kcal ou 8.400 kJ. Seus valores diários podem ser maiores ou menores dependendo de suas necessidades energéticas. (**) VD não estabelecido.
            </p>

            <div class="border-t border-gray-300 pt-4">
                <p class="text-sm font-bold text-black mb-1 uppercase">${product.gluten.toUpperCase()}</p>
                ${product.allergens ? `<p class="text-sm font-bold text-black uppercase">${product.allergens}</p>` : ''}
            </div>
        </div>

        <div class="flex justify-center space-x-4 mt-8 no-print">
            <button onclick="window.print()" class="px-8 py-3 bg-terracota-cyan text-terracota-deepDark font-bold rounded-lg hover:bg-white shadow-[0_0_20px_rgba(0,196,204,0.3)] transition-all flex items-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path></svg>
                Imprimir Tabela
            </button>
            <button onclick="goToStep(1)" class="px-8 py-3 bg-white/10 border border-white/20 text-white font-bold rounded-lg hover:bg-white/20 shadow-sm transition-all">
                Editar
            </button>
        </div>
    `;

}

// --- Excel Import Logic ---

function setupDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        dropZone.classList.add('border-terracota-cyan', 'bg-white/10');
    }

    function unhighlight(e) {
        dropZone.classList.remove('border-terracota-cyan', 'bg-white/10');
    }

    dropZone.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleExcelUpload(files[0]);
    }
}

async function handleExcelUpload(file) {
    if (!file) return;

    const loading = document.getElementById('upload-loading');
    if (loading) loading.classList.remove('hidden');

    try {
        const data = await file.arrayBuffer();
        const workbook = XLSX.read(data);
        const firstSheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[firstSheetName];
        const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 }); // Array of arrays

        processExcelData(jsonData);
    } catch (error) {
        console.error("Error parsing Excel:", error);
        alert("Erro ao ler o arquivo Excel. Verifique se o formato está correto.");
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

function processExcelData(rows) {
    if (!rows || rows.length < 2) {
        alert("Arquivo vazio ou sem cabeçalho identificável.");
        return;
    }

    const headers = rows[0].map(h => String(h).toLowerCase().trim());

    // Column Mapping Helper
    const findCol = (terms) => headers.findIndex(h => terms.some(t => h.includes(t)));

    const mapIndex = {
        name: findCol(['nome', 'ingrediente', 'produto', 'descrição']),
        quantity: findCol(['qtd', 'quantidade', 'peso', 'quant']),
        // Nutri
        energy: findCol(['kcal', 'energia', 'calorias', 'valor energético', 'energ']),
        carbs: findCol(['carb', 'carboidrato']),
        proteins: findCol(['prot', 'proteína', 'proteina']),
        totalFat: headers.findIndex(h => (h.includes('gord') || h.includes('lip')) && !h.includes('sat') && !h.includes('trans')),
        saturatedFat: findCol(['sat', 'saturada']),
        transFat: findCol(['trans']),
        fiber: findCol(['fibra']),
        sodium: findCol(['sódio', 'sodio', 'na'])
    };

    if (mapIndex.name === -1) {
        alert("Não foi possível identificar a coluna de Nome do ingrediente. Verifique se o cabeçalho contém 'Nome' ou 'Ingrediente'.");
        return;
    }

    // Process rows
    let addedCount = 0;
    for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        // Skip if name is empty
        if (!row[mapIndex.name]) continue;

        const getValue = (idx) => {
            if (idx === -1) return 0;
            const val = row[idx];
            return typeof val === 'number' ? val : (parseFloat(String(val).replace(',', '.')) || 0);
        };

        const newIng = {
            id: Date.now() + i,
            name: row[mapIndex.name],
            quantity: getValue(mapIndex.quantity),
            nutritionalInfo: {
                energyKcal: getValue(mapIndex.energy),
                carbs: getValue(mapIndex.carbs),
                proteins: getValue(mapIndex.proteins),
                totalFat: getValue(mapIndex.totalFat),
                saturatedFat: getValue(mapIndex.saturatedFat),
                transFat: getValue(mapIndex.transFat),
                fiber: getValue(mapIndex.fiber),
                sodium: getValue(mapIndex.sodium)
            }
        };

        state.ingredients.push(newIng);
        addedCount++;
    }

    if (addedCount > 0) {
        renderStep2(document.getElementById('wizard-content'));
    } else {
        alert("Nenhum ingrediente válido encontrado.");
    }
}
