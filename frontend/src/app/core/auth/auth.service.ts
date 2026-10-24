import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, switchMap, tap } from 'rxjs';

export type Role = 'ADMIN' | 'SECRETARY' | 'DOCTOR' | 'ADMIN_STAFF' | 'PATIENT';

export const ROLE_LABELS: Record<Role, string> = {
  ADMIN: 'Administrateur',
  SECRETARY: 'Secrétariat',
  DOCTOR: 'Médecin',
  ADMIN_STAFF: 'Gestion administrative',
  PATIENT: 'Patient',
};

export interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_active: boolean;
  patient_id: string | null;
  created_at: string;
  last_login_at: string | null;
}

export interface RegisterPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  role: Role;
  first_name: string;
  last_name: string;
}

const TOKEN_KEY = 'mediflow.token';

// Storage can be unavailable (private mode, blocked site data): never let it break the app.
function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null, remember = false): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    if (token) (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
  } catch {
    /* token stays in memory only */
  }
}

/** Readable message from an API error ({detail, code}) or a network failure. */
export function apiErrorMessage(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'Une erreur inattendue est survenue.';
  if (error.status === 0) return "Le serveur est injoignable. Vérifiez que l'API est démarrée.";
  const detail = error.error?.detail;
  if (typeof detail === 'string') return detail;
  if (error.status === 422) return 'Certaines informations saisies sont invalides.';
  return 'Une erreur est survenue. Réessayez plus tard.';
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private readonly tokenValue = signal<string | null>(readToken());
  readonly user = signal<UserProfile | null>(null);
  readonly isLoggedIn = computed(() => this.tokenValue() !== null);

  token(): string | null {
    return this.tokenValue();
  }

  /** POST /api/auth/login expects an OAuth2 form: `username` is the email. */
  login(email: string, password: string, remember: boolean): Observable<UserProfile> {
    const body = new HttpParams().set('username', email.trim()).set('password', password);
    return this.http.post<LoginResponse>('/api/auth/login', body).pipe(
      tap(response => {
        writeToken(response.access_token, remember);
        this.tokenValue.set(response.access_token);
      }),
      switchMap(() => this.loadProfile()),
    );
  }

  register(payload: RegisterPayload): Observable<UserProfile> {
    return this.http.post<UserProfile>('/api/auth/register', payload);
  }

  loadProfile(): Observable<UserProfile> {
    return this.http.get<UserProfile>('/api/auth/me').pipe(tap(profile => this.user.set(profile)));
  }

  logout(): void {
    writeToken(null);
    this.tokenValue.set(null);
    this.user.set(null);
    this.router.navigate(['/login']);
  }
}
