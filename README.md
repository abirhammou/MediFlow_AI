# MediFlow_AI

Maquette du projet MediFlow AI. Le frontend Angular se trouve dans [`frontend/`](./frontend/); l'API FastAPI + MongoDB est décrite dans [`backend/README.md`](./backend/README.md). Le schéma MongoDB est dans [`database/mongo-init.js`](./database/mongo-init.js) et le modèle de données dans [`docs/erd.html`](./docs/erd.html).

## Prérequis

- Python 3.12 ou plus récent
- Node.js 20 ou plus récent (avec npm)
- Docker Desktop 

## Installation (une seule fois)

Depuis la racine du dépôt, dans PowerShell :

```powershell
# Mots de passe MongoDB pour Docker Compose : éditer .env après la copie
Copy-Item .env.example .env

# Backend : dans backend/.env, mettre dans MONGODB_URI le mot de passe MONGO_APP_PASSWORD
# et le port MONGO_PORT de .env, ainsi qu'un JWT_SECRET personnel
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

Au premier lancement, remplir la base avec les comptes de démonstration (ré-exécutable sans doublon) :

```powershell
cd backend
.\.venv\Scripts\python -m scripts.seed
cd ..
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

Le frontend appelle l'API via le proxy `frontend/proxy.conf.json` (`/api` → `localhost:8000`).

## Comptes de connexion

Page de connexion : http://localhost:4200/login (ou le bouton « Authorize » de http://localhost:8000/docs, avec l'email dans le champ `username`).

Ces comptes sont créés par le seed (`python -m scripts.seed`, voir [Lancer l'application](#lancer-lapplication)). Comptes de **développement uniquement**, toutes les données sont fictives.

| Email | Mot de passe | Rôle | Nom | Remarque |
|---|---|---|---|---|
| `admin@mediflow.local` | `MediFlow2026!` | `ADMIN` | Sami Admin | Gestion des comptes (`/api/users`) |
| `dr.benali@mediflow.local` | `MediFlow2026!` | `DOCTOR` | Dr Hela Benali | Médecine générale, lun–ven 8h30–12h30 |
| `dr.trabelsi@mediflow.local` | `MediFlow2026!` | `DOCTOR` | Dr Mehdi Trabelsi | Cardiologie, mar et jeu 14h–18h |
| `secretariat@mediflow.local` | `MediFlow2026!` | `SECRETARY` | Ines Mejri | Peut lier un compte patient à son dossier |
| `gestion@mediflow.local` | `MediFlow2026!` | `ADMIN_STAFF` | Rami Khelifi | Gestion administrative |
| `patient@mediflow.local` | `MediFlow2026!` | `PATIENT` | Leila Haddad | Lié au dossier patient de Leila Haddad, voit ses rendez-vous |
| `medecin.attente@mediflow.local` | `MediFlow2026!` | `DOCTOR` | Dr Sarra Attente | **Inactif** : connexion refusée (403) tant que l'admin ne l'a pas approuvé (`PATCH /api/users/{id}/approve`) |

- Si `SEED_PASSWORD` est renseigné dans `backend/.env`, c'est ce mot de passe qui est utilisé à la place de `MediFlow2026!`.
- Le seed ne modifie jamais un compte existant : un mot de passe changé reste changé. Pour retrouver les comptes d'origine : `docker compose down -v`, `docker compose up -d mongo`, puis relancer le seed.
- Après 5 mots de passe erronés, le compte est verrouillé 15 minutes.
- « Créer un compte » sur la page d'inscription crée un compte `PATIENT` actif et connecte directement (sans dossier patient lié tant que le secrétariat ne l'a pas associé).

## Base de données

MongoDB 7 tourne dans Docker (`docker-compose.yml`). Les données sont dans le volume nommé `mediflow_mongo_data` : elles sont conservées quand le conteneur est arrêté ou supprimé.

| Commande | Données |
|---|---|
| `docker compose stop mongo` / `docker compose start mongo` | conservées |
| `docker compose down` puis `docker compose up -d mongo` | conservées |
| `docker compose down -v` | **supprimées** (volume effacé) |

Le port côté machine est `MONGO_PORT` dans `.env` (27017 par défaut). Mettre `27018` pour faire tourner le conteneur à côté d'un MongoDB local qui occupe déjà 27017 ; le port de `MONGODB_URI` dans `backend/.env` doit être le même.

**Démarrer MongoDB**

```powershell
docker compose up -d mongo
docker compose ps          # attendre l'état "healthy"
```

Le port `MONGO_PORT` doit être libre : si un service MongoDB local utilise déjà 27017, mettre `MONGO_PORT=27018` (voir ci-dessus) ou arrêter le service (`Stop-Service MongoDB` dans un PowerShell administrateur).

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

**Base locale (sans Docker)** : l'API fonctionne aussi avec un MongoDB installé sur la machine (service Windows `MongoDB`, sans authentification).

```powershell
winget install MongoDB.Shell                                       # mongosh, une seule fois
mongosh "mongodb://localhost:27017/mediflow" database/mongo-init.js  # crée le schéma (ré-exécutable)
```

Puis, dans `backend/.env`, remplacer `MONGODB_URI` par `mongodb://localhost:27017`, lancer le seed et redémarrer l'API. `00-create-user.js` n'est pas nécessaire en local. Pour revenir à Docker, remettre l'URI `mediflow_app` (port `MONGO_PORT`). Les deux bases sont indépendantes : chacune a ses propres données.

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
