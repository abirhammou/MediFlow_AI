# Claude Code prompt — Phase 2: Login & authentication (MediFlow AI)

> Run this only after Phase 1 is done (Mongo up with 14 collections, `/api/health` ok, `pytest` green).
> Copy everything below the line into Claude Code from the repo root.

---

You are implementing **authentication and the login screen** for **MediFlow AI** (clinic management app, academic group project). Phase 1 created the MongoDB collections (`database/mongo-init.js`, strict `$jsonSchema` validators), the FastAPI skeleton and the Beanie models. Read them first; reuse `User` (with embedded `DoctorProfile`), `RefreshToken` and the repository helpers, do not redefine them.

## Stack
- Backend: FastAPI, Beanie, **PyJWT** (HS256), **passlib[bcrypt]** or `bcrypt` (cost 12)
- Frontend: Angular 17+ (standalone components, signals, reactive forms), Angular Material or plain SCSS
- Collections used: `users`, `refresh_tokens`

## Before you write anything
1. Read `database/mongo-init.js` (`users`, `refresh_tokens`: fields, validators, indexes) and the Phase 1 models. Any field you save must exist in the validator.
2. Check whether an Angular app exists in `frontend/`. If not, create it with the Angular CLI (`ng new frontend --standalone --routing --style=scss`).
3. Give me a short plan (endpoints, modules, Angular files), then implement it.

## Backend tasks (`backend/app/modules/auth/`)
1. **Security utilities** (`security.py`)
   - Hash / verify passwords with bcrypt.
   - Access token: JWT, 15 min, claims `sub` (user id), `email`, `role`, `exp`, `iat`. Secret from env `JWT_SECRET` (≥ 32 random bytes), never committed.
   - Refresh token: `secrets.token_urlsafe(64)`. Store only its **SHA-256 hash** in `refresh_tokens.tokenHash`, with `userAgent`, `ipAddress`, `expiresAt` (7 days; a TTL index already deletes expired ones).
2. **Dependencies** (`deps.py`)
   - `get_current_user` (reads `Authorization: Bearer`, decodes JWT, loads an active user, else 401).
   - `require_roles(*roles)` dependency factory → 403 if role not allowed. Other modules will use `Depends(require_roles("DOCTOR", "SECRETARY"))`.
3. **Router** `/api/auth`
   - `POST /login` `{email, password}` → `{accessToken, expiresIn, user: {id, email, firstName, lastName, role}}` and sets the refresh token in an **HttpOnly, Secure, SameSite=Strict cookie** (path `/api/auth`, 7 days). Allow `Secure=False` only when `ENV=dev`.
   - `POST /refresh` → new access token + rotated cookie. **Rotation**: set `revokedAt` and `replacedByTokenHash` on the old document and issue a new one. If an already revoked token is reused, revoke all of that user's tokens and return 401.
   - `POST /logout` → revoke the current refresh token, delete the cookie.
   - `GET /me` → current user.
   - `POST /change-password` (authenticated) `{currentPassword, newPassword}` → revokes all refresh tokens.
4. **Login rules**
   - Unknown email or wrong password → same `401` "Email ou mot de passe incorrect" (no user enumeration; still run a dummy bcrypt verify for unknown emails so timing is similar).
   - `isActive = false` → `403`.
   - 5 failed attempts → `lockedUntil = now + 15 min`; while locked → `423` with the unlock time. Increment `failedLoginAttempts` with an atomic `$inc` (`find_one_and_update`), not read-modify-save, so parallel requests can't bypass the limit. On success reset the counter and set `lastLoginAt`.
   - Password policy (create/change): ≥ 8 chars, at least one letter and one digit.
5. **Errors** — exception handlers returning `{timestamp, status, error, message, path}`; Pydantic validation errors return the list of field messages.
6. **Dev seeder** — `app/scripts/seed_dev_users.py` (run with `python -m app.scripts.seed_dev_users`, and automatically on startup only when `ENV=dev`), idempotent upsert by email, passwords hashed with the app's own hasher:
   - `admin@mediflow.tn` (ADMIN), `secretaire@mediflow.tn` (SECRETARY), `staff@mediflow.tn` (ADMIN_STAFF)
   - `dr.benali@mediflow.tn` (DOCTOR, `doctorProfile`: specialty "Médecine générale", availabilities Monday–Friday 08:30–12:30 and 14:00–17:00, 30-minute slots)
   - Password for all from env `DEV_SEED_PASSWORD`, documented in `.env.example`.
7. **Tests** (pytest + httpx `AsyncClient` + Mongo Testcontainer with `mongo-init.js` applied):
   - JWT encode / decode / expired
   - login OK, wrong password 401, unknown email 401, inactive 403
   - lockout after 5 failures (423), reset after success
   - refresh rotation, reuse of a revoked token revokes all
   - `/me` without token 401, logout, `require_roles` returns 403 for a wrong role

## Frontend tasks (Angular, `frontend/`)
1. `src/environments/` with `apiUrl = 'http://localhost:8000/api'`.
2. `core/auth/`: `AuthService` (login, logout, refresh, `currentUser` signal), functional `authInterceptor` (adds the Bearer token; on 401 calls `/auth/refresh` once, then retries; if that fails → logout and go to `/login`), `authGuard` and `roleGuard(roles)`.
   - Keep the access token **in memory only** (not localStorage). Restore the session at startup with `APP_INITIALIZER` / `provideAppInitializer` calling `/auth/refresh`. All API calls use `withCredentials: true`.
3. **Login page** `/login` (French UI): "MediFlow AI" branding, email + password, show/hide password, "Se connecter" button with loading state, client validation (required, email format), server errors shown inline (401, 403, 423 with the unlock time).
   - On success redirect by role: DOCTOR → `/doctor`, SECRETARY → `/appointments`, ADMIN / ADMIN_STAFF → `/dashboard`. Respect a `returnUrl` query param.
4. Protected **layout shell** (top bar with user name, role badge, "Se déconnecter", side menu filtered by role) with placeholder pages for each module so teammates can plug theirs in. Include `/patients` (Patient Records) for SECRETARY, DOCTOR, ADMIN.
5. `/forbidden` page for role errors and a `**` not-found route.

## Rules
- No secrets in code or git. Add `JWT_SECRET`, `DEV_SEED_PASSWORD`, `CORS_ORIGINS` to `.env.example`.
- Never log passwords or tokens.
- Don't change the database schema. If you need a new field, add it to the validator in `database/mongo-init.js` and tell me why.
- Code in English, UI text in French.

## Done when
- `pytest` passes.
- With `uvicorn` and `ng serve` running, I can log in as each seeded user, land on the right page, reload the browser and stay logged in, log out, and get locked after 5 bad passwords.

Finish with: endpoints table, how to run both apps, the seeded accounts, and a short note showing how another module protects a route with `require_roles`.
