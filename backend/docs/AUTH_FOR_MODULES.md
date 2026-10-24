# Authentification et contrats entre modules

## Protéger une route

`get_current_user` valide le JWT, recharge l'utilisateur depuis `users` et refuse tout compte dont le statut n'est pas `active` (401 pour un jeton absent/invalide, 403 pour un compte non actif).

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

```python
from typing import Any

from fastapi import Depends

from app.dependencies import get_current_user, require_roles


@router.get("/staff")
async def staff_only(
    user: dict[str, Any] = Depends(require_roles("doctor", "secretary")),
) -> dict[str, str]:
    return {"full_name": user["full_name"]}


@router.get("/", response_model=list[ItemOut])
async def list_items(user: dict[str, Any] = Depends(require_roles("doctor", "secretary", "admin"))):
    ...


@router.get("/me")
async def current_profile(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    return {"id": str(user["_id"]), "role": user["role"]}
```

Pour une route recevant l'identifiant d'un dossier patient, vérifier la propriété du dossier :

```python
from app.dependencies import get_current_user, owns_patient_record


@router.get("/{patient_id}")
async def get_patient(
    patient_id: str,
    user: dict = Depends(get_current_user),
):
    owns_patient_record(user, patient_id)
    ...
```

Pour le rôle patient, une valeur `users.patient_id` absente ou nulle ne donne accès à aucun dossier. Les rôles internes passent le contrôle de propriété ; protégez-les séparément par `require_roles` si nécessaire.

## Contrats de données

| Collection | Champ | Contrat |
|---|---|---|
| `users` | `patient_id` | Nullable ; identifiant du dossier lié, renseigné par l'action de liaison |
| `patients` | `user_id` | Optionnel ; identifiant de l'utilisateur associé |
| `documents` | `patient_id` | Chaîne contenant l'identifiant du dossier patient |

Chaque module ne lit et n'écrit que les collections dont il est propriétaire. **Aucun module n'écrit dans la collection d'un autre module.** Les liaisons entre collections sont faites par identifiants, sans création ou modification croisée de documents.

## Droits par module

| Module / opération | Droits |
|---|---|
| Authentification et profil (`auth`) | Routes publiques d'inscription/connexion ; `me` et changement de mot de passe pour tout compte actif |
| Gestion des utilisateurs (`users`) | Admin ; liaison/déliaison patient : admin ou secrétaire |
| Tableau de bord (`dashboard`) | Tout compte actif, contenu filtré selon son rôle |
| Patients | Admin, médecin et secrétaire pour la gestion ; patient uniquement sur son propre dossier |
| Rendez-vous | Admin, médecin et secrétaire pour la gestion ; patient pour ses propres rendez-vous |
| Documents | Admin, médecin et secrétaire selon les règles métier ; patient uniquement pour ses documents |
| Rapports et suivis | Admin, médecin et secrétaire selon les règles métier |
| FAQ | Tout compte actif selon les règles métier |

## Envoi à un LLM

Tout envoi à un fournisseur LLM doit construire une **liste blanche explicite de champs** autorisés. Ne jamais transmettre directement un document Mongo complet : exclure notamment les identifiants, coordonnées, secrets, données d'authentification et tout champ non indispensable au traitement.
