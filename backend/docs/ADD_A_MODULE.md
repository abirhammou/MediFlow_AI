# Ajouter un module

1. Depuis `backend/`, exécuter `python scripts/new_module.py <nom>`.
2. Adapter `schemas.py`, `repository.py`, `service.py` et `prompts.py` dans le nouveau dossier.
3. Renseigner ses 3 variables LLM (`<NOM>_LLM_BASE_URL`, `<NOM>_LLM_MODEL` et `<NOM>_LLM_API_KEY`) dans son `.env` local.
4. Lancer `python -m pytest`, puis tester les routes du module dans `/docs`.

Les noms acceptés sont en minuscules, composés de lettres et d'underscores. Le générateur ajoute les réglages LLM à `.env.example` et `.env`, et copie les tests du module modèle.

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
