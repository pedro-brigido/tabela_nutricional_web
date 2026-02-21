/**
 * ANVISA Nutritional Calculator Core Logic
 * Regulation References:
 * - RDC 429/2020 (Nutritional Labeling)
 * - IN 75/2020 (Technical requirements)
 */

const AnvisaConstants = {
    // Reference Daily Values (VD) for adults (Annex II, IN 75/2020)
    VD: {
        energy: 2000, // kcal
        carbs: 300,   // g
        addedSugars: 50, // g
        totalSugars: null, // No VD
        totalFat: 55, // g (Changed from 55 to 55? Wait, standard is 55g in IN 75)
        saturatedFat: 20, // g
        transFat: null, // No VD
        fiber: 25,    // g
        sodium: 2000, // mg
        protein: 50   // g
    },
    // Atwater Factors
    FACTORS: {
        protein: 4,
        carbs: 4,
        fat: 9,
        fiber: 2,
        ethanol: 7,
        polyol: 2.4,
        erythritol: 0
    },
    // Rounding & Significance Thresholds (Annex IV, IN 75/2020)
    RULES: {
        energy: {
            unit: 'kcal',
            threshold: 4, // < 4 kcal = 0
            rounding: [
                { limit: 10, step: 1 },    // < 10: integers (1, 2, 3...) - simplified, actually standard says "whole number" usually
                { limit: null, step: 1 }   // >= 10: whole numbers
                // NOTE: ANVISA RDC 429 usually requires rounding to nearest 1 kcal.
            ]
        },
        macronutrients: {
            // Carbs, Protein, Fat, Fiber, Sugar
            unit: 'g',
            threshold: 0.5, // < 0.5g = 0
            rounding: [
                { limit: 10, decimal: 1 }, // < 10g: 1 decimal place (e.g., 1.5)
                { limit: null, decimal: 0 } // >= 10g: whole numbers (e.g., 12)
            ]
        },
        sodium: {
            unit: 'mg',
            threshold: 5, // < 5mg = 0
            rounding: [
                { limit: null, step: 1 } // whole numbers
            ]
        },
        transFat: {
            unit: 'g',
            threshold: 0.1, // Specific strict threshold for trans fat
            // Special rule: if <= 0.2g per portion AND per 100g, can be "0"
            // For MVP we use the base threshold from the table which is often simplified to 0.1 or 0.2 depending on context. 
            // IN 75 Annex IV: "Quantities insignificant": <= 0.2 g par portion => "0"
            // But we will stick to the generic rounding logic method for now.
            rounding: [
                { limit: 10, decimal: 1 },
                { limit: null, decimal: 0 }
            ]
        }
    }
};

class AnvisaCalculator {

    /**
     * Calculates nutritional table measurements for a specific portion.
     * @param {Array} ingredients - List of { nutritionalInfo: { ...per100g }, quantity: number (g) }
     * @param {number} portionSize - Size of the portion in grams
     * @returns {object} Calculated values for 100g and Per Portion, including %VD
     */
    static calculate(ingredients, portionSize) {
        // 1. Sum total raw values per 100g of final product (assuming sum of ingredients = final weight for MVP - ignoring cooking loss factor)
        // In this MVP, we assume "quantity" is the amount of ingredient in the FINAL product.
        // If the user inputs a recipe (sum > portion), we need to normalize.
        // Let's assume the user inputs the quantity used to make the TOTAL batch, and we calculate per 100g of expected final yield.

        let totalBatchWeight = 0;
        let totalNutrients = {
            energy: 0, // kcal
            carbs: 0,
            proteins: 0,
            totalFat: 0,
            saturatedFat: 0,
            transFat: 0,
            fiber: 0,
            sodium: 0
        };

        ingredients.forEach(ing => {
            const qty = parseFloat(ing.quantity) || 0;
            totalBatchWeight += qty;

            // Ingredient info is usually per 100g
            const factor = qty / 100;

            totalNutrients.carbs += (ing.nutritionalInfo.carbs || 0) * factor;
            totalNutrients.proteins += (ing.nutritionalInfo.proteins || 0) * factor;
            totalNutrients.totalFat += (ing.nutritionalInfo.totalFat || 0) * factor;
            totalNutrients.saturatedFat += (ing.nutritionalInfo.saturatedFat || 0) * factor;
            totalNutrients.transFat += (ing.nutritionalInfo.transFat || 0) * factor;
            totalNutrients.fiber += (ing.nutritionalInfo.fiber || 0) * factor;
            totalNutrients.sodium += (ing.nutritionalInfo.sodium || 0) * factor;

            // Energy: Check if provided, otherwise calculate
            if (ing.nutritionalInfo.energyKcal) {
                totalNutrients.energy += ing.nutritionalInfo.energyKcal * factor;
            } else {
                // Determine energy from macros for this ingredient
                const calculatedE =
                    ((ing.nutritionalInfo.carbs || 0) * 4) +
                    ((ing.nutritionalInfo.proteins || 0) * 4) +
                    ((ing.nutritionalInfo.totalFat || 0) * 9) +
                    ((ing.nutritionalInfo.fiber || 0) * 2);
                totalNutrients.energy += calculatedE * factor;
            }
        });

        if (totalBatchWeight === 0) return null; // Avoid division by zero

        // 2. Calculate values per 100g of FINAL PRODUCT
        const per100g = {};
        for (const [key, value] of Object.entries(totalNutrients)) {
            per100g[key] = (value / totalBatchWeight) * 100;
        }

        // 3. Calculate values per Portion
        const perPortion = {};
        const portionFactor = portionSize / 100;
        for (const [key, value] of Object.entries(per100g)) {
            perPortion[key] = value * portionFactor;
        }

        // 4. Apply Rounding and Thresholds Rules (IN 75 Annex IV)
        // We need to return: rounded value (string), raw value (number), and %VD (string)

        return {
            per100g: this.formatResultSet(per100g),
            perPortion: this.formatResultSet(perPortion, true)
        };
    }

    /**
     * Formats a set of nutrient values according to ANVISA rules
     * @param {object} nutrients - Raw nutrient values
     * @param {boolean} calculateVD - Whether to calculate %VD (only for portion usually, but visually displayed for both sometimes)
     */
    static formatResultSet(nutrients, calculateVD = false) {
        const formatted = {};

        // Define mapping to rules
        const map = {
            energy: 'energy',
            carbs: 'macronutrients',
            proteins: 'macronutrients',
            totalFat: 'macronutrients',
            saturatedFat: 'macronutrients',
            transFat: 'transFat',
            fiber: 'macronutrients',
            sodium: 'sodium'
        };

        for (const [key, rawValue] of Object.entries(nutrients)) {
            const ruleType = map[key];
            const rule = AnvisaConstants.RULES[ruleType];

            // 1. Check Threshold (Insignificance)
            let finalValue = rawValue;
            let displayValue = "";

            if (rawValue <= rule.threshold) {
                finalValue = 0;
                // Special case: if it requires specific format for zero? Usually just "0"
                // For macros < 0.5g, declare "0"
                displayValue = "0";
            } else {
                // 2. Rounding
                displayValue = this.roundValue(rawValue, rule);
                finalValue = parseFloat(displayValue.replace(',', '.')); // Back to number for VD calc if needed
            }

            // 3. Calculate %VD
            let vdValue = "";
            if (calculateVD && AnvisaConstants.VD[key] !== null && AnvisaConstants.VD[key] !== undefined) {
                const percent = (finalValue / AnvisaConstants.VD[key]) * 100;
                // VD Rounding: usually integers
                if (percent < 1) {
                    vdValue = "0"; // Or "< 1"? Standard usually just 1 or 0. Let's use 0 if very small.
                } else {
                    vdValue = Math.round(percent).toString();
                }
            }

            // Trans fat doesn't have VD
            if (key === 'transFat') vdValue = "";

            formatted[key] = {
                raw: rawValue,
                display: displayValue.replace('.', ','), // PT-BR format
                vd: vdValue
            };
        }

        return formatted;
    }

    static roundValue(value, rule) {
        // Find matching rounding rule
        const roundRule = rule.rounding.find(r => r.limit === null || value < r.limit);

        if (!roundRule) return value.toFixed(0); // Fallback

        if (roundRule.decimal !== undefined) {
            // Round to N decimal places
            return value.toFixed(roundRule.decimal);
        } else if (roundRule.step) {
            // Round to nearest step (e.g. integer)
            return Math.round(value).toString();
        }

        return value.toString();
    }
}

// Make available globally
window.AnvisaCalculator = AnvisaCalculator;
