/**
 * UI condivisa per card ricette e modale dettaglio (Home + Ricette).
 */
(function (global) {
    const API_BASE = (window.location.port === "8000")
        ? `${window.location.protocol}//${window.location.host}/api`
        : "http://127.0.0.1:8000/api";
    const PLACEHOLDER_IMAGE = "img/pasta.png";

    function normalizeDifficulty(d) {
        const n = parseInt(d) || 1;
        if (n >= 5) return 3;
        return Math.max(1, Math.min(3, n));
    }

    function formatDifficultyStars(d) {
        return "★".repeat(normalizeDifficulty(d));
    }

    function parseIngredientsForDisplay(raw) {
        if (!raw) return [];
        const t = String(raw).trim();
        if (t.startsWith("[")) {
            try {
                return JSON.parse(t).map(i => {
                    if (typeof i === "object" && i !== null) {
                        const qty = i.qty ? `${i.qty} ` : "";
                        const unit = i.unit ? `${i.unit} ` : "";
                        return `${qty}${unit}${i.name || ""}`.trim();
                    }
                    return String(i);
                }).filter(Boolean);
            } catch (e) { /* formato legacy */ }
        }
        return t.split(",").map(s => s.trim()).filter(Boolean);
    }

    function initRecipeModal(options) {
        const {
            isUserLoggedIn = false,
            onRequireLogin = null,
            onLogClick = null,
        } = options || {};

        const modalOverlay = document.getElementById("recipe-modal-overlay");
        const modalCloseBtn = document.getElementById("recipe-modal-close-btn");
        const modalImg = document.getElementById("recipe-modal-img");
        const modalTitle = document.getElementById("recipe-modal-title");
        const modalDescription = document.getElementById("recipe-modal-description");
        const modalInfoBar = document.getElementById("recipe-modal-info-bar");
        const modalIngredients = document.getElementById("recipe-modal-ingredients");
        const modalSteps = document.getElementById("recipe-modal-steps");
        const modalNotesBox = document.getElementById("recipe-modal-notes-box");
        const modalNotes = document.getElementById("recipe-modal-notes");

        if (!modalOverlay) {
            console.error("RecipeUI: elemento #recipe-modal-overlay non trovato");
            return { openRecipeModal: () => {} };
        }

        // Il modale deve stare su body, non dentro main/section (evita problemi di stacking)
        if (modalOverlay.parentElement !== document.body) {
            document.body.appendChild(modalOverlay);
        }

        function closeModal() {
            modalOverlay.classList.remove("open");
            document.body.style.overflow = "";
        }

        if (modalCloseBtn) {
            modalCloseBtn.addEventListener("click", closeModal);
        }
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) closeModal();
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && modalOverlay.classList.contains("open")) {
                closeModal();
            }
        });

        function openRecipeModal(recipeId) {
            const id = parseInt(recipeId, 10);
            if (!id || Number.isNaN(id)) return;

            if (isUserLoggedIn && onLogClick) onLogClick(id);

            fetch(`${API_BASE}/recipes/${id}`)
                .then(response => {
                    if (!response.ok) throw new Error("Errore caricamento dettagli ricetta");
                    return response.json();
                })
                .then(recipe => {
                    if (recipe.error) {
                        alert(recipe.error);
                        return;
                    }
                    modalImg.src = recipe.image || PLACEHOLDER_IMAGE;
                    modalImg.onerror = function () {
                        this.onerror = null;
                        if (!this.src.includes("pasta.png")) {
                            this.src = PLACEHOLDER_IMAGE;
                        }
                    };
                    modalTitle.innerText = recipe.title;

                    if (recipe.description && recipe.description.trim()) {
                        modalDescription.innerText = recipe.description;
                        modalDescription.classList.remove("hidden");
                    } else {
                        modalDescription.classList.add("hidden");
                    }

                    const stars = formatDifficultyStars(recipe.difficulty);
                    const categoryText = recipe.category ? `🍽 ${recipe.category}` : "🍽 Primo";
                    const portionsText = recipe.portions ? `👥 ${recipe.portions}` : "👥 4 persone";
                    const cookMethodText = recipe.cooking_method ? `🍳 ${recipe.cooking_method}` : "";
                    const equipmentText = recipe.equipment ? `🔧 ${recipe.equipment}` : "";
                    const timeDetail = recipe.prep_time_min != null
                        ? `⏱ ${recipe.prep_time_min} min prep${recipe.cook_time_min ? ` + ${recipe.cook_time_min} min cottura` : ""}`
                        : `⏱ ${recipe.prep_time} min`;

                    modalInfoBar.innerHTML = `
                        <span class="recipe-modal-info-tag">${categoryText}</span>
                        <span class="recipe-modal-info-tag">${portionsText}</span>
                        <span class="recipe-modal-info-tag">${timeDetail}</span>
                        <span class="recipe-modal-info-tag">Difficoltà: ${stars}</span>
                        ${cookMethodText ? `<span class="recipe-modal-info-tag">${cookMethodText}</span>` : ""}
                        ${equipmentText ? `<span class="recipe-modal-info-tag">${equipmentText}</span>` : ""}
                    `;

                    const dietTags = recipe.dietary_tags ? String(recipe.dietary_tags) : "";
                    if (dietTags) {
                        dietTags.split(",").forEach(tag => {
                            const trimTag = tag.trim();
                            if (trimTag) {
                                modalInfoBar.innerHTML += `<span class="recipe-modal-info-tag diet-tag">${trimTag}</span>`;
                            }
                        });
                    }

                    modalIngredients.innerHTML = "";
                    const ingredientLines = parseIngredientsForDisplay(recipe.ingredients);
                    if (ingredientLines.length > 0) {
                        ingredientLines.forEach(trimIng => {
                            if (trimIng) {
                                const label = document.createElement("label");
                                label.className = "modal-ingredient-item";
                                label.innerHTML = `
                                    <input type="checkbox" class="modal-ingredient-checkbox">
                                    <span class="modal-ingredient-text">${trimIng}</span>
                                `;
                                modalIngredients.appendChild(label);
                            }
                        });
                    } else {
                        modalIngredients.innerHTML = "<p style='color:#777; font-style:italic;'>Nessun ingrediente specificato.</p>";
                    }

                    modalSteps.innerHTML = "";
                    let stepImagesMap = {};
                    if (recipe.step_images) {
                        try {
                            stepImagesMap = JSON.parse(recipe.step_images);
                        } catch (e) {
                            console.warn("Immagini passaggi non valide:", e);
                        }
                    }
                    if (recipe.steps) {
                        const stepsArray = recipe.steps.includes("|||")
                            ? recipe.steps.split("|||")
                            : recipe.steps.split("\n");
                        let stepCount = 1;
                        stepsArray.forEach((step, index) => {
                            const trimStep = step.trim();
                            if (trimStep) {
                                const cleanedStep = trimStep.replace(/^\d+[\.\s\-–—]*/, "");
                                const stepImg = stepImagesMap[index] || stepImagesMap[String(index)] || "";
                                const stepDiv = document.createElement("div");
                                stepDiv.className = "modal-step-item";
                                stepDiv.innerHTML = `
                                    <div class="modal-step-number">${stepCount}</div>
                                    <div class="modal-step-body">
                                        <div class="modal-step-content">${cleanedStep}</div>
                                        ${stepImg ? `<img class="modal-step-image" src="${stepImg}" alt="Foto passaggio ${stepCount}">` : ""}
                                    </div>
                                `;
                                modalSteps.appendChild(stepDiv);
                                stepCount++;
                            }
                        });
                    } else {
                        modalSteps.innerHTML = "<p style='color:#777; font-style:italic;'>Nessun procedimento specificato.</p>";
                    }

                    if (recipe.notes && recipe.notes.trim()) {
                        modalNotes.innerText = recipe.notes;
                        modalNotesBox.classList.remove("hidden");
                    } else {
                        modalNotesBox.classList.add("hidden");
                    }

                    modalOverlay.classList.add("open");
                    document.body.style.overflow = "hidden";
                })
                .catch(err => {
                    console.error(err);
                    alert("Impossibile caricare i dettagli completi della ricetta.");
                });
        }

        return { openRecipeModal, formatDifficultyStars, normalizeDifficulty };
    }

    function buildDietBadgesHtml(dietaryTags) {
        if (!dietaryTags) return "";
        let html = "";
        dietaryTags.split(",").map(t => t.trim()).forEach(tag => {
            if (tag) {
                const tagClass = tag.toLowerCase().replace(/\s+/g, "-");
                html += `<span class="recipe-dietary-badge ${tagClass}">${tag}</span>`;
            }
        });
        return html;
    }

    function appendRecipeCard(recipeGrid, recipe, options) {
        const {
            savedIds = new Set(),
            isAdmin = false,
            openRecipeModal,
            animateIndex = 0,
        } = options;

        const card = document.createElement("div");
        card.className = "recipe-card";
        card.style.cursor = "pointer";
        if (animateIndex > 0) {
            card.classList.add("recipe-card-enter");
            card.style.animationDelay = `${animateIndex * 0.05}s`;
        }

        const isSaved = savedIds.has(recipe.id);
        const stars = formatDifficultyStars(recipe.difficulty);
        const categoryText = recipe.category ? `🍽 ${recipe.category}` : "🍽 Primo";
        const portionsText = recipe.portions ? `👥 ${recipe.portions}` : "👥 4 persone";
        const dietBadgesHtml = buildDietBadgesHtml(recipe.dietary_tags);

        const adminActions = isAdmin ? `
            <div class="card-manage-actions">
                <button class="card-manage-btn delete-btn" onclick="deleteRecipe(${recipe.id}, this); event.stopPropagation();" title="Elimina (Admin)">
                    <svg width="16" height="16" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                </button>
            </div>
        ` : "";

        card.innerHTML = `
            ${adminActions}
            <button class="save-btn ${isSaved ? "saved" : ""}" onclick="toggleSaveRecipe(${recipe.id}, this); event.stopPropagation();">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
                </svg>
            </button>
            <img src="${recipe.image || PLACEHOLDER_IMAGE}" alt="${recipe.title}" onerror="this.onerror=null;this.src='${PLACEHOLDER_IMAGE}'">
            <div class="recipe-info">
                <h3>${recipe.title}</h3>
                <div class="recipe-card-meta">
                    <span>${categoryText}</span>
                    <span>${portionsText}</span>
                </div>
                <p style="font-size: 0.9rem; color: #666; margin-bottom: 5px;">
                    ⏱ ${recipe.prep_time} min | <span style="color: var(--yellow); font-weight: bold; letter-spacing: 2px;">${stars}</span>
                </p>
                <div class="recipe-dietary-badges">${dietBadgesHtml}</div>
                <div style="display: flex; justify-content: flex-end; align-items: center; margin-top: 10px;">
                    <span style="font-size: 0.85rem; color: var(--green); font-weight: bold;">Leggi ricetta &rarr;</span>
                </div>
            </div>
        `;

        card.dataset.recipeId = String(recipe.id);
        card.addEventListener("click", (e) => {
            if (e.target.closest(".save-btn, .card-manage-actions")) return;
            openRecipeModal(recipe.id);
        });
        recipeGrid.appendChild(card);
        return card;
    }

    global.RecipeUI = {
        API_BASE,
        initRecipeModal,
        appendRecipeCard,
        formatDifficultyStars,
        normalizeDifficulty,
        parseIngredientsForDisplay,
    };
})(window);
