# Backend MediFlow AI

MediFlow AI est une maquette d'API FastAPI asynchrone avec MongoDB via Motor. Le mode mock est activé par défaut : les tests et l'application ne contactent aucun fournisseur LLM. Aucune authentification n'est installée dans cette maquette.

## Prérequis

- Python 3.11 ou plus récent
- MongoDB 7 (local ou lancé avec Docker Compose depuis la racine du dépôt)

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

L'API répond sur `http://localhost:8000`, la documentation interactive sur `/docs` et le contrôle de santé sur `/health`. Les routes fonctionnelles de démonstration du module notes sont sous `/api/notes`.

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

Le test MongoDB utilise `mongomock-motor`; aucun serveur MongoDB n'est nécessaire pour les tests.

## Workflow Git

1. Créer une branche dédiée depuis la branche de travail à jour, par exemple `feature/nom-du-module` ou `fix/description-courte`.
2. Faire des commits ciblés avec des messages descriptifs, par exemple `feat: ajouter le module documents`.
3. Pousser sa branche et ouvrir une pull request vers la branche cible du dépôt.
4. Attendre les vérifications et la revue, puis intégrer la pull request selon les règles de l'équipe.
