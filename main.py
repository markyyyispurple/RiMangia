import os
import re
import unicodedata
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RECIPE_IMAGE = "img/pasta.png"

class AuthRequest(BaseModel):
    username: str
    password: str

class PreferencesUpdate(BaseModel):
    preferences: list[str] = []

USER_COLUMNS = ['id', 'username', 'password', 'Preferenze', 'Preferenze_Completate']
VALID_PREFERENCES = {'Vegetariano', 'Vegano', 'Senza Glutine', 'Senza Lattosio'}

def load_users() -> pd.DataFrame:
    try:
        df = pd.read_csv('utenti.csv', sep=';', dtype=str)
    except Exception:
        df = pd.DataFrame(columns=USER_COLUMNS)
        df.to_csv('utenti.csv', sep=';', index=False)
    for col in USER_COLUMNS:
        if col not in df.columns:
            df[col] = 1 if col == 'Preferenze_Completate' else ""

    df = df[USER_COLUMNS].copy()
    df['id'] = pd.to_numeric(df['id'], errors='coerce').fillna(0).astype(int)
    df['username'] = df['username'].fillna("").astype(str)
    df['password'] = df['password'].fillna("").astype(str)
    df['Preferenze'] = df['Preferenze'].fillna("").astype(str)
    df['Preferenze_Completate'] = pd.to_numeric(
        df['Preferenze_Completate'], errors='coerce'
    ).fillna(0).astype(int)
    return df

def user_auth_response(row) -> dict:
    prefs_done = int(row['Preferenze_Completate']) == 1
    prefs = str(row['Preferenze']) if str(row['Preferenze']) not in ('', 'nan') else ""
    return {
        "user_id": int(row['id']),
        "username": str(row['username']),
        "needs_preferences": not prefs_done,
        "preferences": prefs,
    }

class RecipeCreate(BaseModel):
    title: str
    image: str
    description: str = ""
    prep_time: int
    cook_time: int = 0
    difficulty: int
    author_id: int = 0
    ingredients: str = ""
    dietary_tags: str = ""
    category: str = ""
    portions: str = ""
    steps: str = ""
    notes: str = ""
    step_images: str = ""
    cooking_method: str = ""
    equipment: str = ""

RECIPE_COLUMNS = [
    'ID_Ricetta', 'Titolo', 'Immagine', 'Descrizione',
    'Tempo_Preparazione_Min', 'Tempo_Cottura_Min', 'Difficolta_1_a_5', 'Autore_ID',
    'Ingredienti', 'Diete', 'Categoria', 'Porzioni', 'Procedimento', 'Note',
    'Immagini_Passaggi', 'Metodo_Cottura', 'Strumentazione'
]

INTERACTIONS_FILE = 'database_interazioni_utenti.csv'
INTERACTION_COLUMNS = [
    'interazione_id', 'utente_id', 'ricetta_id', 'tipo_interazione',
    'valore', 'timestamp', 'nome_utente', 'nome_ricetta'
]
VALID_INTERACTION_TYPES = {
    'click', 'preferito', 'ingrediente_cercato', 'testo_cercato', 'mi_piace'
}
WEIGHT_SEARCH_DISH = 8
WEIGHT_FAVORITES = 8
WEIGHT_PROFILE = 8
WEIGHT_INGREDIENT = 5
WEIGHT_CLICK = 3
RECOMMENDED_LIMIT = 6

class InteractionCreate(BaseModel):
    tipo_interazione: str
    valore: str = ""
    ricetta_id: int | None = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def ensure_recipe_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in RECIPE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[RECIPE_COLUMNS]

def carica_ricette():
    try:
        df = pd.read_csv('ricette.csv')
        df = ensure_recipe_columns(df)
    except Exception:
        df = pd.DataFrame(columns=RECIPE_COLUMNS)
        df.to_csv('ricette.csv', index=False)
    return df

def recipe_row_from_create(recipe: RecipeCreate, recipe_id: int) -> dict:
    prep = max(0, int(recipe.prep_time))
    cook = max(0, int(recipe.cook_time))
    return {
        'ID_Ricetta': recipe_id,
        'Titolo': recipe.title,
        'Immagine': recipe.image if recipe.image else DEFAULT_RECIPE_IMAGE,
        'Descrizione': recipe.description or "",
        'Tempo_Preparazione_Min': prep,
        'Tempo_Cottura_Min': cook,
        'Difficolta_1_a_5': max(1, min(3, recipe.difficulty)),
        'Autore_ID': recipe.author_id,
        'Ingredienti': recipe.ingredients or "",
        'Diete': recipe.dietary_tags or "",
        'Categoria': recipe.category or "",
        'Porzioni': recipe.portions or "",
        'Procedimento': recipe.steps or "",
        'Note': recipe.notes or "",
        'Immagini_Passaggi': recipe.step_images or "",
        'Metodo_Cottura': recipe.cooking_method or "",
        'Strumentazione': recipe.equipment or "",
    }

def ricarica_dataset():
    global dataset_ricette
    dataset_ricette = carica_ricette()

def clamp_difficulty(value) -> int:
    try:
        d = int(value)
    except (TypeError, ValueError):
        return 2
    if d >= 5:
        return 3
    return max(1, min(3, d))

def _cell(row, col: str) -> str:
    if col not in row or pd.isna(row[col]):
        return ""
    return str(row[col])

def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')

def _normalize_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = _strip_accents(str(value).strip().lower())
    return re.sub(r'\s+', ' ', text)

def parse_ingredients_set(raw) -> set[str]:
    text = _normalize_text(raw)
    if not text:
        return set()
    if text.startswith('['):
        try:
            import json
            items = json.loads(raw if isinstance(raw, str) else str(raw))
            names = []
            for item in items:
                if isinstance(item, dict):
                    names.append(_normalize_text(item.get('name', '')))
                else:
                    names.append(_normalize_text(item))
            return {n for n in names if n}
        except Exception:
            pass
    return {p.strip() for p in text.split(',') if p.strip()}

def ingredient_tokens(raw) -> set[str]:
    """Token ingredienti: nome intero + parole (es. 'pecorino' da 'pecorino romano')."""
    tokens: set[str] = set()
    for ing in parse_ingredients_set(raw):
        tokens.add(ing)
        for word in ing.split():
            if len(word) >= 2:
                tokens.add(word)
    return tokens

def count_ingredient_overlap(tokens_a: set[str], tokens_b: set[str]) -> int:
    if not tokens_a or not tokens_b:
        return 0
    matches = 0
    for a in tokens_a:
        if any(a in b or b in a for b in tokens_b):
            matches += 1
    return matches

def _token_in_text(token: str, text: str) -> bool:
    """Match parola intera (evita 'pasta' dentro 'pastiera')."""
    if not token or not text:
        return False
    pattern = r'(^|[\s,;])' + re.escape(token) + r'($|[\s,;])'
    if re.search(pattern, f' {text} '):
        return True
    return token == text

def recipe_matches_search_query(title: str, ingredients_raw, query: str) -> bool:
    """Match titolo o ingredienti per ricerche tipo 'carbonara', 'arancini', 'pasta'."""
    q = _normalize_text(query)
    if not q or len(q) < 2:
        return False
    title_n = _normalize_text(title)
    if q in title_n or title_n in q:
        return True
    q_words = [w for w in q.split() if len(w) >= 3]
    if q_words and all(_token_in_text(w, title_n) for w in q_words):
        return True
    if q_words and any(_token_in_text(w, title_n) for w in q_words):
        return True
    for ing in parse_ingredients_set(ingredients_raw):
        if q in ing or ing in q:
            return True
        if q_words and any(_token_in_text(w, ing) for w in q_words):
            return True
    return False

def ingredient_query_matches_recipe(query: str, ingredients_raw) -> bool:
    q = _normalize_text(query)
    if not q:
        return False
    tokens = ingredient_tokens(ingredients_raw)
    if any(q == t or q in t.split() or t in q.split() for t in tokens):
        return True
    if _token_in_text(q, ' '.join(tokens)):
        return True
    q_words = [w for w in q.split() if len(w) >= 2]
    return any(_token_in_text(w, ' '.join(tokens)) for w in q_words)

def parse_diet_tags(raw) -> set[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return set()
    return {t.strip() for t in str(raw).split(',') if t.strip()}

def parse_user_preferences(prefs_str: str) -> list[str]:
    if not prefs_str or str(prefs_str) in ('', 'nan'):
        return []
    return [p.strip() for p in str(prefs_str).split(',') if p.strip() in VALID_PREFERENCES]

def recipe_matches_user_preferences(diete_raw, user_prefs: list[str]) -> bool:
    if not user_prefs:
        return True
    recipe_tags = parse_diet_tags(diete_raw)
    return all(pref in recipe_tags for pref in user_prefs)

def load_interactions() -> pd.DataFrame:
    try:
        df = pd.read_csv(INTERACTIONS_FILE, sep=';', dtype=str)
    except Exception:
        df = pd.DataFrame(columns=INTERACTION_COLUMNS)
        df.to_csv(INTERACTIONS_FILE, sep=';', index=False)
        return df

    if 'azione' in df.columns:
        if 'tipo_interazione' not in df.columns:
            df['tipo_interazione'] = df['azione'].replace({'mi_piace': 'preferito'})
        else:
            mask = df['tipo_interazione'].isna() | (df['tipo_interazione'] == '')
            df.loc[mask, 'tipo_interazione'] = df.loc[mask, 'azione'].replace({'mi_piace': 'preferito'})

    for col in INTERACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[INTERACTION_COLUMNS].copy()
    df['interazione_id'] = pd.to_numeric(df['interazione_id'], errors='coerce').fillna(0).astype(int)
    df['utente_id'] = pd.to_numeric(df['utente_id'], errors='coerce').fillna(0).astype(int)
    df['ricetta_id'] = pd.to_numeric(df['ricetta_id'], errors='coerce').fillna(0).astype(int)
    df['tipo_interazione'] = df['tipo_interazione'].fillna("").astype(str)
    df['valore'] = df['valore'].fillna("").astype(str)
    df['timestamp'] = df['timestamp'].fillna("").astype(str)
    df['nome_utente'] = df['nome_utente'].fillna("").astype(str)
    df['nome_ricetta'] = df['nome_ricetta'].fillna("").astype(str)
    return df

def save_interactions(df: pd.DataFrame) -> None:
    df = df[INTERACTION_COLUMNS].copy()
    df.to_csv(INTERACTIONS_FILE, sep=';', index=False)

def get_username(user_id: int) -> str:
    df_utenti = load_users()
    user_row = df_utenti[df_utenti['id'] == user_id]
    if user_row.empty:
        return "Utente"
    return str(user_row.iloc[0]['username'])

def get_recipe_title(recipe_id: int) -> str:
    recipe_row = dataset_ricette[dataset_ricette['ID_Ricetta'] == recipe_id]
    if recipe_row.empty:
        return "Ricetta"
    return str(recipe_row.iloc[0]['Titolo'])

def log_interaction(
    user_id: int,
    tipo: str,
    valore: str = "",
    ricetta_id: int = 0,
) -> dict:
    tipo = tipo.strip().lower()
    if tipo == 'mi_piace':
        tipo = 'preferito'
    if tipo not in VALID_INTERACTION_TYPES - {'mi_piace'}:
        return {"error": f"tipo_interazione non valido. Valori ammessi: click, preferito, ingrediente_cercato, testo_cercato"}

    interazioni = load_interactions()
    new_id = int(interazioni['interazione_id'].max()) + 1 if len(interazioni) > 0 else 1
    nome_ricetta = get_recipe_title(ricetta_id) if ricetta_id else ""

    nuova = pd.DataFrame([{
        'interazione_id': new_id,
        'utente_id': user_id,
        'ricetta_id': int(ricetta_id) if ricetta_id else 0,
        'tipo_interazione': tipo,
        'valore': valore.strip(),
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'nome_utente': get_username(user_id),
        'nome_ricetta': nome_ricetta,
    }])
    interazioni = pd.concat([interazioni, nuova], ignore_index=True)
    save_interactions(interazioni)
    return {"success": True, "interazione_id": new_id}

def user_interactions_df(interazioni: pd.DataFrame, user_id: int) -> pd.DataFrame:
    return interazioni[interazioni['utente_id'] == user_id].copy()

def compute_recipe_scores(user_id: int, recipes_df: pd.DataFrame, with_breakdown: bool = False):
    interazioni = load_interactions()
    user_ix = user_interactions_df(interazioni, user_id)

    recipe_ids = recipes_df['ID_Ricetta'].astype(int)
    scores = pd.Series(0.0, index=recipe_ids.values)
    breakdown: dict[int, dict[str, float]] = {int(rid): {
        'ricerca_piatto': 0.0, 'preferiti': 0.0, 'profilo': 0.0,
        'ingredienti': 0.0, 'click': 0.0,
    } for rid in recipe_ids}

    def add_score(rid, factor: str, points: float) -> None:
        """Applica bonus comportamentali anche se la ricetta era esclusa dal filtro dieta."""
        if points <= 0:
            return
        rid = int(rid)
        if rid not in scores.index:
            return
        if scores[rid] == float('-inf'):
            scores[rid] = 0.0
        scores[rid] += points
        breakdown[rid][factor] += points

    df_utenti = load_users()
    user_row = df_utenti[df_utenti['id'] == user_id]
    user_prefs = []
    if not user_row.empty:
        user_prefs = parse_user_preferences(user_row.iloc[0]['Preferenze'])

    recipe_ingredients = {
        int(r['ID_Ricetta']): ingredient_tokens(r['Ingredienti'])
        for _, r in recipes_df.iterrows()
    }
    recipe_categories = {
        int(r['ID_Ricetta']): _normalize_text(r['Categoria'])
        for _, r in recipes_df.iterrows()
    }
    recipe_diete = {
        int(r['ID_Ricetta']): parse_diet_tags(r['Diete'])
        for _, r in recipes_df.iterrows()
    }

    fav_rows_early = user_ix[user_ix['tipo_interazione'].isin(['preferito', 'mi_piace'])]
    saved_fav_ids = {
        int(x) for x in fav_rows_early['ricetta_id'].tolist() if int(x) > 0
    }

    compatible_mask = pd.Series(True, index=recipe_ids.values)
    for rid in recipe_ids:
        row = recipes_df[recipes_df['ID_Ricetta'] == rid].iloc[0]
        if user_prefs and not recipe_matches_user_preferences(row['Diete'], user_prefs):
            if int(rid) not in saved_fav_ids:
                compatible_mask[rid] = False
                scores[rid] = float('-inf')

    # 1. Ricerca specifica di ricette (peso 8) — ingredienti condivisi con piatti cercati
    search_rows = user_ix[user_ix['tipo_interazione'] == 'testo_cercato']
    if not search_rows.empty:
        target_ingredients: set[str] = set()
        source_recipe_ids: set[int] = set()
        seen_queries: set[str] = set()
        for _, ix_row in search_rows.iterrows():
            query = str(ix_row['valore']).strip()
            q_norm = _normalize_text(query)
            if not q_norm or q_norm in seen_queries:
                continue
            seen_queries.add(q_norm)
            for _, r in recipes_df.iterrows():
                rid = int(r['ID_Ricetta'])
                if recipe_matches_search_query(
                    str(r['Titolo']), r['Ingredienti'], query
                ):
                    source_recipe_ids.add(rid)
                    target_ingredients |= recipe_ingredients.get(rid, set())

        # Bonus al piatto cercato/trovato (es. "arancini" → la ricetta Arancini)
        for rid in source_recipe_ids:
            add_score(rid, 'ricerca_piatto', WEIGHT_SEARCH_DISH)

        for rid in recipe_ids:
            if rid in source_recipe_ids:
                continue
            shared = count_ingredient_overlap(
                recipe_ingredients.get(rid, set()), target_ingredients
            )
            if shared > 0:
                add_score(rid, 'ricerca_piatto', WEIGHT_SEARCH_DISH * shared)

    # 2. Preferiti (peso 8) — bonus diretto ai salvati + simili per categoria/tag
    fav_rows = user_ix[user_ix['tipo_interazione'].isin(['preferito', 'mi_piace'])]
    fav_ids = list(dict.fromkeys(
        int(x) for x in fav_rows['ricetta_id'].tolist() if int(x) > 0
    ))
    fav_categories: set[str] = set()
    fav_diet_tags: set[str] = set()
    for fid in fav_ids:
        if scores[fid] == float('-inf'):
            scores[fid] = 0.0
        scores[fid] += WEIGHT_FAVORITES
        breakdown[fid]['preferiti'] += WEIGHT_FAVORITES
        compatible_mask[fid] = True
        if fid in recipe_categories:
            cat = recipe_categories[fid]
            if cat:
                fav_categories.add(cat)
        if fid in recipe_diete:
            fav_diet_tags |= recipe_diete[fid]

    for rid in recipe_ids:
        if rid in fav_ids:
            continue
        if recipe_categories.get(rid) in fav_categories and fav_categories:
            scores[rid] += WEIGHT_FAVORITES
            breakdown[rid]['preferiti'] += WEIGHT_FAVORITES
        diet_overlap = recipe_diete.get(rid, set()) & fav_diet_tags
        if diet_overlap:
            scores[rid] += WEIGHT_FAVORITES
            breakdown[rid]['preferiti'] += WEIGHT_FAVORITES

    # 3. Preferenze profilo (peso 8) — solo ricette realmente compatibili con la dieta
    if user_prefs:
        for rid in recipe_ids:
            row = recipes_df[recipes_df['ID_Ricetta'] == rid].iloc[0]
            if recipe_matches_user_preferences(row['Diete'], user_prefs):
                scores[rid] += WEIGHT_PROFILE
                breakdown[rid]['profilo'] += WEIGHT_PROFILE

    # 4. Ricerca ingredienti (peso 5)
    ing_rows = user_ix[user_ix['tipo_interazione'] == 'ingrediente_cercato']
    if not ing_rows.empty:
        ing_counts = ing_rows['valore'].astype(str).str.strip()
        ing_counts = ing_counts[ing_counts != ''].value_counts()
        for ing, count in ing_counts.items():
            weight = WEIGHT_INGREDIENT * min(int(count), 5)
            for rid in recipe_ids:
                row = recipes_df[recipes_df['ID_Ricetta'] == rid].iloc[0]
                if ingredient_query_matches_recipe(ing, row['Ingredienti']):
                    add_score(rid, 'ingredienti', weight)

    # 5. Click (peso 3) — bonus diretto alla ricetta aperta + categorie visitate
    click_rows = user_ix[user_ix['tipo_interazione'] == 'click']
    if not click_rows.empty:
        clicked_ids = click_rows['ricetta_id'].astype(int)
        clicked_ids = clicked_ids[clicked_ids > 0]
        for rid, count in clicked_ids.value_counts().items():
            add_score(int(rid), 'click', WEIGHT_CLICK * min(int(count), 10))

        cat_counts: dict[str, int] = {}
        for rid, count in clicked_ids.value_counts().items():
            cat = recipe_categories.get(int(rid), '')
            if cat:
                cat_counts[cat] = cat_counts.get(cat, 0) + int(count)
        for rid in recipe_ids:
            cat = recipe_categories.get(rid, '')
            if cat and cat in cat_counts:
                add_score(rid, 'click', WEIGHT_CLICK * cat_counts[cat])

    if with_breakdown:
        return scores, breakdown
    return scores

def fallback_recommendations(recipes_df: pd.DataFrame, limit: int = RECOMMENDED_LIMIT) -> list[dict]:
    interazioni = load_interactions()
    popularity = pd.Series(dtype=float)

    if len(interazioni) > 0:
        subset = interazioni[
            interazioni['tipo_interazione'].isin(('click', 'preferito', 'mi_piace'))
        ]
        counts = subset['ricetta_id'].astype(int)
        counts = counts[counts > 0].value_counts()
        popularity = counts.astype(float)

    if popularity.empty or popularity.sum() == 0:
        ordered = recipes_df.sort_values('ID_Ricetta', ascending=False)
    else:
        recipes_df = recipes_df.copy()
        recipes_df['popularity'] = recipes_df['ID_Ricetta'].map(
            lambda x: popularity.get(int(x), 0)
        )
        ordered = recipes_df.sort_values(
            ['popularity', 'ID_Ricetta'], ascending=[False, False]
        )

    result = []
    for _, row in ordered.head(limit).iterrows():
        result.append(recipe_card_summary(row, score=0.0, fallback=True))
    return result

def get_recommended_recipes(user_id: int) -> dict:
    df_utenti = load_users()
    if user_id not in df_utenti['id'].values:
        return {"error": "Utente non trovato"}

    recipes_df = dataset_ricette.copy()
    if recipes_df.empty:
        return {"recipes": [], "fallback": True}

    interazioni = load_interactions()
    user_ix = user_interactions_df(interazioni, user_id)
    behavioral_types = {'click', 'preferito', 'mi_piace', 'ingrediente_cercato', 'testo_cercato'}
    has_behavior = not user_ix.empty and user_ix['tipo_interazione'].isin(behavioral_types).any()

    if not has_behavior:
        return {"recipes": fallback_recommendations(recipes_df), "fallback": True}

    scores, breakdown = compute_recipe_scores(user_id, recipes_df, with_breakdown=True)
    valid = scores[scores > float('-inf')]
    if valid.empty or valid.max() <= 0:
        return {"recipes": fallback_recommendations(recipes_df), "fallback": True}

    fav_rows = user_ix[user_ix['tipo_interazione'].isin(['preferito', 'mi_piace'])]
    saved_ids = list(dict.fromkeys(
        int(x) for x in fav_rows['ricetta_id'].tolist() if int(x) > 0
    ))

    priority_ids: list[int] = list(saved_ids)
    seen_search: set[str] = set()
    for _, ix_row in user_ix[user_ix['tipo_interazione'] == 'testo_cercato'].iterrows():
        query = str(ix_row['valore']).strip()
        q_norm = _normalize_text(query)
        if not query or q_norm in seen_search:
            continue
        seen_search.add(q_norm)
        for _, r in recipes_df.iterrows():
            rid = int(r['ID_Ricetta'])
            if recipe_matches_search_query(str(r['Titolo']), r['Ingredienti'], query):
                if rid not in priority_ids:
                    priority_ids.append(rid)
    click_series = user_ix[user_ix['tipo_interazione'] == 'click']['ricetta_id'].astype(int)
    click_series = click_series[click_series > 0]
    for cid in click_series.value_counts().index.tolist():
        cid = int(cid)
        if cid not in priority_ids:
            priority_ids.append(cid)

    ranked_ids = valid.sort_values(ascending=False).index.tolist()
    top_ids: list[int] = []

    for pid in priority_ids:
        if len(top_ids) >= RECOMMENDED_LIMIT:
            break
        if pid in recipes_df['ID_Ricetta'].values and pid not in top_ids:
            top_ids.append(int(pid))

    for rid in ranked_ids:
        if len(top_ids) >= RECOMMENDED_LIMIT:
            break
        if int(rid) not in top_ids:
            top_ids.append(int(rid))

    recipes = []
    for rid in top_ids:
        row = recipes_df[recipes_df['ID_Ricetta'] == rid].iloc[0]
        factors = breakdown.get(int(rid), {})
        display_score = float(scores[rid]) if scores[rid] > float('-inf') else 0.0
        recipes.append(recipe_card_summary(
            row,
            score=round(display_score, 2),
            fallback=False,
            score_factors={k: round(v, 1) for k, v in factors.items() if v > 0},
        ))
    return {"recipes": recipes, "fallback": False}

def recipe_card_summary(
    row, score: float = 0.0, fallback: bool = False, score_factors: dict | None = None
) -> dict:
    item = recipe_to_dict(row)
    result = {
        "id": item["id"],
        "title": item["title"],
        "image": item["image"],
        "prep_time": item["prep_time"],
        "difficulty": item["difficulty"],
        "category": item["category"],
        "dietary_tags": item["dietary_tags"],
        "portions": item["portions"],
        "score": score,
        "fallback": fallback,
    }
    if score_factors:
        result["score_factors"] = score_factors
    return result

def recipe_to_dict(row) -> dict:
    prep = int(row['Tempo_Preparazione_Min']) if not pd.isna(row['Tempo_Preparazione_Min']) else 0
    cook = int(row['Tempo_Cottura_Min']) if 'Tempo_Cottura_Min' in row and not pd.isna(row['Tempo_Cottura_Min']) else 0
    return {
        "id": int(row['ID_Ricetta']),
        "title": str(row['Titolo']),
        "image": str(row['Immagine']),
        "description": _cell(row, 'Descrizione'),
        "prep_time": prep + cook,
        "prep_time_min": prep,
        "cook_time_min": cook,
        "difficulty": clamp_difficulty(row['Difficolta_1_a_5']),
        "ingredients": _cell(row, 'Ingredienti'),
        "dietary_tags": _cell(row, 'Diete'),
        "category": _cell(row, 'Categoria'),
        "portions": _cell(row, 'Porzioni'),
        "steps": _cell(row, 'Procedimento'),
        "notes": _cell(row, 'Note'),
        "step_images": _cell(row, 'Immagini_Passaggi'),
        "cooking_method": _cell(row, 'Metodo_Cottura'),
        "equipment": _cell(row, 'Strumentazione'),
    }

dataset_ricette = carica_ricette()

@app.get("/api/recipes")
def get_all_recipes():
    lista_ricette = []
    for _, row in dataset_ricette.iterrows():
        lista_ricette.append(recipe_to_dict(row))
    return {"recipes": lista_ricette}

@app.post("/api/auth/register")
def register(request: AuthRequest):
    df_utenti = load_users()
    if request.username in df_utenti['username'].values:
        return {"error": "Username già in uso"}
    new_id = int(df_utenti['id'].max()) + 1 if len(df_utenti) > 0 else 101
    new_row = pd.DataFrame([{
        'id': new_id,
        'username': request.username,
        'password': request.password,
        'Preferenze': "",
        'Preferenze_Completate': 0,
    }])
    df_utenti = pd.concat([df_utenti, new_row], ignore_index=True)
    df_utenti.to_csv('utenti.csv', sep=';', index=False)
    return user_auth_response(new_row.iloc[0])

@app.post("/api/auth/login")
def login(request: AuthRequest):
    df_utenti = load_users()
    user = df_utenti[(df_utenti['username'] == request.username) & (df_utenti['password'] == request.password)]
    if len(user) > 0:
        return user_auth_response(user.iloc[0])
    return {"error": "Credenziali errate"}

@app.get("/api/user/{user_id}/preferences")
def get_user_preferences(user_id: int):
    df_utenti = load_users()
    df_utenti['id'] = df_utenti['id'].astype(int)
    user = df_utenti[df_utenti['id'] == user_id]
    if user.empty:
        return {"error": "Utente non trovato"}
    row = user.iloc[0]
    return {
        "user_id": user_id,
        "needs_preferences": int(row['Preferenze_Completate']) != 1,
        "preferences": str(row['Preferenze']) if not pd.isna(row['Preferenze']) else "",
    }

@app.put("/api/user/{user_id}/preferences")
def update_user_preferences(user_id: int, body: PreferencesUpdate):
    df_utenti = load_users()
    df_utenti['id'] = df_utenti['id'].astype(int)
    if user_id not in df_utenti['id'].values:
        return {"error": "Utente non trovato"}

    cleaned = []
    for pref in body.preferences:
        pref = pref.strip()
        if pref in VALID_PREFERENCES and pref not in cleaned:
            cleaned.append(pref)

    prefs_str = ", ".join(cleaned)
    df_utenti.loc[df_utenti['id'] == user_id, 'Preferenze'] = prefs_str
    df_utenti.loc[df_utenti['id'] == user_id, 'Preferenze_Completate'] = 1
    df_utenti.to_csv('utenti.csv', sep=';', index=False)

    row = df_utenti[df_utenti['id'] == user_id].iloc[0]
    return user_auth_response(row)

@app.get("/api/recipes/recommended/{user_id}")
def recommended_recipes(user_id: int):
    return get_recommended_recipes(user_id)

@app.post("/api/user/{user_id}/interactions")
def register_interaction(user_id: int, body: InteractionCreate):
    df_utenti = load_users()
    if user_id not in df_utenti['id'].values:
        return {"error": "Utente non trovato"}
    return log_interaction(
        user_id=user_id,
        tipo=body.tipo_interazione,
        valore=body.valore,
        ricetta_id=body.ricetta_id or 0,
    )

@app.get("/api/user/{user_id}/saved_recipes")
def saved_recipes(user_id: int):
    interazioni = load_interactions()
    saved = interazioni[
        (interazioni['utente_id'] == user_id) &
        (interazioni['tipo_interazione'].isin(['preferito', 'mi_piace']))
    ]
    saved_ids = [int(x) for x in saved['ricetta_id'].tolist() if int(x) > 0]
    
    lista_ricette = []
    for _, row in dataset_ricette.iterrows():
        if int(row['ID_Ricetta']) in saved_ids:
            lista_ricette.append(recipe_to_dict(row))
    return {"recipes": lista_ricette}


@app.post("/api/user/{user_id}/toggle_save/{recipe_id}")
def toggle_save_recipe(user_id: int, recipe_id: int):
    df_utenti = load_users()
    if user_id not in df_utenti['id'].values:
        return {"error": "Utente non trovato"}

    recipe_row = dataset_ricette[dataset_ricette['ID_Ricetta'] == recipe_id]
    if recipe_row.empty:
        return {"error": "Ricetta non trovata"}

    interazioni = load_interactions()
    condizione = (
        (interazioni['utente_id'] == user_id) &
        (interazioni['ricetta_id'] == recipe_id) &
        (interazioni['tipo_interazione'].isin(['preferito', 'mi_piace']))
    )
    already_saved = interazioni[condizione]

    if not already_saved.empty:
        interazioni = interazioni[~condizione]
        save_interactions(interazioni)
        return {"saved": False, "message": "Ricetta rimossa dai salvati"}

    log_interaction(user_id, 'preferito', valore='', ricetta_id=recipe_id)
    return {"saved": True, "message": "Ricetta salvata con successo"}

@app.post("/api/recipes/add")
def add_recipe(recipe: RecipeCreate):
    if not recipe.title.strip():
        return {"error": "Il titolo non può essere vuoto"}
        
    try:
        df = pd.read_csv('ricette.csv')
        df = ensure_recipe_columns(df)
        
        if len(df) > 0:
            new_id = int(df['ID_Ricetta'].max()) + 1
        else:
            new_id = 1

        new_row = pd.DataFrame([recipe_row_from_create(recipe, new_id)])
        df = pd.concat([df, new_row], ignore_index=True)
        df = ensure_recipe_columns(df)
        df.to_csv('ricette.csv', index=False)
        
        ricarica_dataset()
        
        return {"success": True, "recipe_id": new_id, "message": "Ricetta aggiunta con successo!"}
        
    except Exception as e:
        return {"error": f"Errore durante l'aggiunta al database: {str(e)}"}

@app.get("/api/user/{user_id}/added_recipes")
def get_user_added_recipes(user_id: int):
    lista_ricette = []
    if 'Autore_ID' in dataset_ricette.columns:
        user_recipes = dataset_ricette[dataset_ricette['Autore_ID'] == user_id]
        for _, row in user_recipes.iterrows():
            lista_ricette.append(recipe_to_dict(row))
    return {"recipes": lista_ricette}

@app.get("/api/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    recipe_row = dataset_ricette[dataset_ricette['ID_Ricetta'] == recipe_id]
    if recipe_row.empty:
        return {"error": "Ricetta non trovata"}
    
    row = recipe_row.iloc[0]
    result = recipe_to_dict(row)
    result["author_id"] = int(row['Autore_ID']) if 'Autore_ID' in row and not pd.isna(row['Autore_ID']) else 0
    return result

@app.put("/api/recipes/{recipe_id}")
def update_recipe(recipe_id: int, recipe: RecipeCreate):
    try:
        df = pd.read_csv('ricette.csv')
        df = ensure_recipe_columns(df)
        if recipe_id not in df['ID_Ricetta'].values:
            return {"error": "Ricetta non trovata"}

        row_data = recipe_row_from_create(recipe, recipe_id)
        for col, val in row_data.items():
            if col != 'ID_Ricetta':
                df.loc[df['ID_Ricetta'] == recipe_id, col] = val
        
        df.to_csv('ricette.csv', index=False)
        
        ricarica_dataset()
        return {"success": True, "message": "Ricetta aggiornata con successo!"}
    except Exception as e:
        return {"error": f"Errore durante l'aggiornamento: {str(e)}"}

@app.delete("/api/recipes/{recipe_id}")
def delete_recipe(recipe_id: int):
    try:
        df = pd.read_csv('ricette.csv')
        if recipe_id not in df['ID_Ricetta'].values:
            return {"error": "Ricetta non trovata"}
            
        df = df[df['ID_Ricetta'] != recipe_id]
        df.to_csv('ricette.csv', index=False)
        
        try:
            interazioni = load_interactions()
            interazioni = interazioni[interazioni['ricetta_id'] != recipe_id]
            save_interactions(interazioni)
        except Exception:
            pass
            
        ricarica_dataset()
        return {"success": True, "message": "Ricetta eliminata con successo!"}
    except Exception as e:
        return {"error": f"Errore durante l'eliminazione: {str(e)}"}

@app.get("/")
def serve_home():
    return FileResponse(os.path.join(BASE_DIR, "Home.html"))

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="gigantic-ignore-wrench.ngrok-free.dev", port=8000, reload=True)