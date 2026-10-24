# Backend MediFlow AI

MediFlow AI est une maquette d'API FastAPI asynchrone avec MongoDB via Beanie (ODM asynchrone sur PyMongo). Le mode mock est activé par défaut : les tests et l'application ne contactent aucun fournisseur LLM. Aucune authentification n'est installée dans cette maquette.

## Prérequis

- Python 3.12 ou plus récent
- MongoDB 7 lancé avec Docker Compose depuis la racine du dépôt (voir la section « Base de données » du [README racine](../README.md#base-de-données))

## Installation et démarrage

Depuis la racine du dépôt, démarrer MongoDB puis préparer l'environnement virtuel :

```powershell
docker compose up -d mongo
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

L'API répond sur `http://localhost:8000`, la documentation interactive sur `/docs` et le contrôle de santé (ping MongoDB) sur `/api/health`. Les routes fonctionnelles de démonstration du module notes sont sous `/api/notes`.

## Modèles de données

- `database/mongo-init.js` est la source de vérité : collections, champs, enums, validateurs (`additionalProperties: false`) et index. Un champ de modèle absent du validateur fait échouer l'insertion. Les index ne sont jamais déclarés dans Beanie.
- Un fichier `app/modules/<module>/models.py` par module (MedDoc AI : `documents/`), enregistré dans `DOCUMENT_MODELS` (`app/core/db.py`).
- Attributs Python en snake_case, champs MongoDB en camelCase via un générateur d'alias (`first_name` ↔ `firstName`).
- Bases communes dans `app/core/models.py` : `TimestampedDocument` (`createdAt` + `updatedAt`) et `CreatedAtDocument` (`createdAt` seul), remplis par des hooks Beanie sur `insert()`, `replace()` et `save()`. `insert_many()`, `set()` et `update()` ne déclenchent pas les hooks.
- Dates en UTC avec fuseau. `dateOfBirth` est stocké à minuit UTC (`Patient.birth_date` renvoie une `date`). Les e-mails sont mis en minuscules avant l'enregistrement.
- Numéros de dossier : `app/core/sequence.py` (`next_record_number()` → `PAT-2026-00001`).
- Requêtes partagées : `repository.py` de chaque module (`auth`, `patients`, `appointments`, `faq`).

## Configuration LLM

Les configurations et clés sont indépendantes par module. La clé n'est jamais exposée par l'API. Une clé absente en environnement de développement active le mock; hors développement, elle produit une erreur 503.

| Module | Responsable | Fournisseur | Modèle |
|---|---|---|---|
| documents | Amal | À compléter | À compléter |
| template | À compléter | À compléter | À compléter |
| À créer | À compléter | À compléter | À compléter |

Pour brancher un vrai LLM :

1. Créer une clé chez le fournisseur.
2. Renseigner les 3 variables de son module dans son `.env` local (`*_LLM_BASE_URL`, `*_LLM_MODEL`, `*_LLM_API_KEY`).
3. Mettre `LLM_MOCK=false`.
4. Tester via `/api/llm/status`.

`*_LLM_PROVIDER` accepte `mock`, `openai_compatible` ou `anthropic`. Pour les fournisseurs compatibles OpenAI, `*_LLM_BASE_URL` correspond à l'URL de base de l'API. L'anonymisation est appliquée au texte avant tout appel externe.

## Tests

Dans `backend/` :

```powershell
python -m pytest
```

Les tests de base de données démarrent un conteneur `mongo:7` avec Testcontainers (Docker requis, sinon ils sont ignorés). Le test du module modèle `_template` utilise `mongomock-motor`.

## Workflow Git

1. Créer une branche dédiée depuis la branche de travail à jour, par exemple `feature/nom-du-module` ou `fix/description-courte`.
2. Faire des commits ciblés avec des messages descriptifs, par exemple `feat: ajouter le module documents`.
3. Pousser sa branche et ouvrir une pull request vers la branche cible du dépôt.
4. Attendre les vérifications et la revue, puis intégrer la pull request selon les règles de l'équipe.
