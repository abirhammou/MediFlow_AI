# MediFlow_AI

Maquette du projet MediFlow AI. Le frontend Angular se trouve dans [`frontend/`](./frontend/); l'API FastAPI + MongoDB est décrite dans [`backend/README.md`](./backend/README.md). Le schéma MongoDB est dans [`database/mongo-init.js`](./database/mongo-init.js) et le modèle de données dans [`docs/erd.html`](./docs/erd.html).

## Prérequis

- Python 3.12 ou plus récent
- Node.js 20 ou plus récent (avec npm)
- Docker Desktop (le compte Windows doit être membre du groupe local `docker-users`)

## Installation (une seule fois)

Depuis la racine du dépôt, dans PowerShell :

```powershell
# Mots de passe MongoDB pour Docker Compose : éditer .env après la copie
Copy-Item .env.example .env

# Backend : dans backend/.env, mettre dans MONGODB_URI la valeur de MONGO_APP_PASSWORD
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
cd ..

# Frontend
cd frontend
npm ci
cd ..
```

Le fichier `backend/.env` active le mode mock par défaut : aucun appel à un vrai LLM. Les deux fichiers `.env` ne sont jamais commités.

## Lancer l'application

Il faut trois éléments : MongoDB, l'API et le frontend. Ouvrir un terminal par service.

**1. MongoDB** : démarrer Docker Desktop puis (voir [Base de données](#base-de-données)) :

```powershell
docker compose up -d mongo
```

**2. API (terminal 1)**

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

**3. Frontend (terminal 2)**

```powershell
cd frontend
npm start
```

| Service | URL |
|---|---|
| Frontend | http://localhost:4200 |
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| Contrôle de santé (ping MongoDB) | http://localhost:8000/api/health |
| mongo-express (optionnel) | http://localhost:8081 |

## Base de données

MongoDB 7 tourne dans Docker (`docker-compose.yml`). Les données sont dans le volume `mediflow_mongo_data`.

**Démarrer MongoDB**

```powershell
docker compose up -d mongo
docker compose ps          # attendre l'état "healthy"
```

Le port `27017` doit être libre : si un service MongoDB local tourne aussi, l'arrêter d'abord (`Stop-Service MongoDB` dans un PowerShell administrateur).

**Scripts d'initialisation** : au **premier démarrage seulement** (volume vide), MongoDB exécute les scripts de `database/` par ordre alphabétique :

1. `00-create-user.js` crée l'utilisateur applicatif `mediflow_app` (`readWrite` sur `mediflow` uniquement, mot de passe `MONGO_APP_PASSWORD`).
2. `mongo-init.js` crée les 14 collections, leurs validateurs `$jsonSchema`, leurs index et les données de référence.

L'API se connecte toujours avec `mediflow_app`, jamais avec le compte root. Le compte root sert uniquement aux scripts d'initialisation et à mongo-express.

Si le volume existe déjà, les scripts ne sont **pas** relancés. Après une modification de `mongo-init.js` (le script est ré-exécutable, il met à jour les validateurs avec `collMod`), soit on le relance à la main :

```powershell
docker compose exec mongo sh -c 'mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin /docker-entrypoint-initdb.d/mongo-init.js'
```

soit on repart d'une base vide.

**Réinitialiser la base** (supprime toutes les données, les scripts seront rejoués au prochain démarrage) :

```powershell
docker compose down -v
docker compose up -d mongo
```

**mongo-express** (interface web, profil `tools`) : `docker compose --profile tools up -d`, puis http://localhost:8081 avec `MONGO_EXPRESS_USERNAME` / `MONGO_EXPRESS_PASSWORD` du `.env`.

**Lancer l'API** : `cd backend` puis `.\.venv\Scripts\python -m uvicorn app.main:app --reload`. Au démarrage, l'API initialise Beanie; elle ne crée ni collection ni index (ils appartiennent à `mongo-init.js`). `GET /api/health` renvoie `{"status": "ok", "database": "ok"}` si MongoDB répond, sinon une erreur 503.

**Lancer les tests** : `cd backend` puis `.\.venv\Scripts\python -m pytest`. Les tests de base de données démarrent leur propre conteneur `mongo:7` (Testcontainers), y exécutent les deux scripts d'initialisation et se connectent en `mediflow_app`. Docker doit donc tourner; sinon ces tests sont marqués « skipped » avec la raison affichée.

## Arrêter l'application

- **API et frontend** : appuyer sur `Ctrl+C` dans chacun des deux terminaux.
- **MongoDB via Docker** : `docker compose stop mongo` (ou `docker compose down` pour supprimer le conteneur; les données restent dans le volume `mediflow_mongo_data`).

Si un port reste occupé (processus lancé en arrière-plan) :

```powershell
Get-NetTCPConnection -LocalPort 8000,4200 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
```
