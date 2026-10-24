# Ajouter un module

1. Depuis `backend/`, exécuter `python scripts/new_module.py <nom>`.
2. Adapter `schemas.py`, `repository.py`, `service.py` et `prompts.py` dans le nouveau dossier.
3. Renseigner ses 3 variables LLM (`<NOM>_LLM_BASE_URL`, `<NOM>_LLM_MODEL` et `<NOM>_LLM_API_KEY`) dans son `.env` local.
4. Si le module a des modèles Beanie (`models.py`), les ajouter à `DOCUMENT_MODELS` dans `app/core/db.py`; leurs champs doivent exister dans `database/mongo-init.js`.
5. Lancer `python -m pytest`, puis tester les routes du module dans `/docs`.

Les noms acceptés sont en minuscules, composés de lettres et d'underscores. Le générateur ajoute les réglages LLM à `.env.example` et `.env`, et copie les tests du module modèle.

> **Attention : le template n'est pas protégé**
>
> Les routes de `_template` (`/api/notes`) sont publiques : elles n'ont aucune dépendance d'authentification, car c'est un exemple pour apprendre. Tout module copié depuis `_template` **DOIT** protéger ses routes avec `Depends(require_roles(...))` selon le tableau de droits, avant d'être mergé dans `main`.
>
> Pour la démonstration et le déploiement, mettre `EXPOSE_TEMPLATE=false` dans `backend/.env`.
>
> **Checklist avant de merger un module**
> - Toutes les routes sont protégées.
> - Un patient ne voit que ses propres données (`owns_patient_record`).
> - Aucune écriture n'est faite dans la collection d'un autre module.
> - Aucune donnée personnelle brute n'est envoyée au LLM : utiliser une liste blanche de champs.
> - Pour chaque route, ajouter un test avec un compte autorisé et un test avec un compte refusé.

**ne modifiez pas main.py, il découvre les modules automatiquement** : chaque dossier de module avec un `router.py` exportant `router` est chargé au démarrage.

Le module interne `_template` n'est exposé que si `EXPOSE_TEMPLATE=true` (valeur du `.env` de développement).

## Exemple d'adaptation

Pour un module `documents`, le générateur crée notamment `DocumentCreate`, `DocumentRepository` et `DocumentService`. Adaptez le schéma de création au besoin métier :

```python
class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    category: str = Field(default="general")
```

Puis faites persister les nouveaux champs dans `DocumentRepository` et ajoutez la logique métier correspondante dans `DocumentService`. Le `router.py` généré sera découvert automatiquement ; les tests doivent couvrir le comportement attendu de ces routes.
