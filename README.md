# MediFlow_AI

Maquette du projet MediFlow AI. Le frontend Angular existant se trouve dans [`frontend/`](./frontend/); l'API FastAPI + MongoDB en mode mock est décrite dans [`backend/README.md`](./backend/README.md).

## Démarrage rapide

```powershell
docker compose up -d mongo
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

L'API est accessible à `http://localhost:8000`; Swagger UI est à `/docs`.
