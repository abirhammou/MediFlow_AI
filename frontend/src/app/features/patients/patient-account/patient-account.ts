import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, input, signal, untracked } from '@angular/core';
import { Observable } from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../../shared/icon/icon';
import { formatDateTime } from '../birth-date';

interface Account {
  exists: boolean;
  userId: string | null;
  email: string | null;
  isActive: boolean | null;
  mustChangePassword: boolean | null;
  lastLoginAt: string | null;
  createdAt: string | null;
  temporaryPassword?: string;
}

/**
 * "Compte patient" card (SECRETARY / ADMIN): create the patient's portal login or give
 * a new temporary password. The password is shown once, to hand to the patient.
 */
@Component({
  selector: 'app-patient-account',
  imports: [Icon],
  template: `
    <section class="card account" aria-labelledby="account-title">
      <h2 id="account-title"><app-icon name="user" [size]="18" /> Compte patient (portail)</h2>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }
      @if (account(); as a) {
        @if (a.exists) {
          <p>
            <strong>{{ a.email }}</strong> ·
            @if (a.mustChangePassword) { <span class="chip warn">Mot de passe temporaire non changé</span> }
            @else { <span class="chip ok">Actif</span> }
          </p>
          <p class="meta">Créé le {{ formatDateTime(a.createdAt) }} · dernière connexion : {{ a.lastLoginAt ? formatDateTime(a.lastLoginAt) : 'jamais' }}</p>
          <button type="button" class="btn btn-outline btn-sm" [disabled]="busy()" (click)="reset()">Nouveau mot de passe temporaire</button>
        } @else {
          <p class="meta">Le patient n'a pas encore accès au portail (comptes rendus, documents, rendez-vous, factures).</p>
          <form class="create" (submit)="$event.preventDefault(); create()">
            <input class="input" type="email" placeholder="Email du patient (vide : celui du dossier)" [value]="email()"
                   (input)="email.set($any($event.target).value)" aria-label="Email du compte" />
            <button type="submit" class="btn btn-primary btn-sm" [disabled]="busy()">Créer le compte</button>
          </form>
        }
        @if (password(); as p) {
          <div class="password" role="status">
            <p>Mot de passe temporaire à remettre au patient (affiché une seule fois) :</p>
            <code>{{ p }}</code>
            <p class="meta">Il devra le changer à sa première connexion.</p>
          </div>
        }
      } @else if (!error()) {
        <p class="muted">Chargement…</p>
      }
    </section>
  `,
  styles: `
    :host { display: block; margin-bottom: 1rem; }
    .account { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: .6rem; }
    h2 { display: flex; align-items: center; gap: .5rem; font-size: 1rem; font-weight: 700; }
    .meta { font-size: .8rem; color: var(--muted); }
    .create { display: flex; gap: .5rem; flex-wrap: wrap; .input { flex: 1; min-width: 220px; } }
    .chip { padding: .1rem .55rem; border-radius: 999px; font-size: .72rem; font-weight: 700;
      &.ok { background: #f0fdf4; color: #15803d; } &.warn { background: #fff7ed; color: #c2410c; } }
    .password { padding: .75rem 1rem; border-radius: var(--radius-sm); background: #f0fdf4; border: 1px solid #bbf7d0;
      font-size: .85rem; code { display: inline-block; margin: .35rem 0; padding: .3rem .6rem; border-radius: 6px;
      background: #fff; font-size: 1.1rem; letter-spacing: .08em; user-select: all; } }
  `,
})
export class PatientAccountCard {
  readonly patientId = input.required<string>();
  private http = inject(HttpClient);
  private confirm = inject(ConfirmService);
  protected readonly formatDateTime = formatDateTime;

  protected account = signal<Account | null>(null);
  protected password = signal<string | null>(null);
  protected email = signal('');
  protected busy = signal(false);
  protected error = signal<string | null>(null);

  constructor() {
    effect(() => {
      const url = this.url(this.patientId());
      untracked(() => {
        this.password.set(null);
        this.http.get<Account>(url).subscribe({
          next: (account) => this.account.set(account),
          error: (err) => this.error.set(apiErrorMessage(err)),
        });
      });
    });
  }

  private url(patientId = this.patientId(), suffix = ''): string {
    return `/api/patients/${encodeURIComponent(patientId)}/account${suffix}`;
  }

  private show(request: Observable<Account>): void {
    this.busy.set(true);
    this.error.set(null);
    request.subscribe({
      next: (account) => {
        this.busy.set(false);
        this.account.set(account);
        this.password.set(account.temporaryPassword ?? null);
      },
      error: (err) => {
        this.busy.set(false);
        this.error.set(apiErrorMessage(err));
      },
    });
  }

  protected create(): void {
    this.show(this.http.post<Account>(this.url(), { email: this.email().trim() || null }));
  }

  protected async reset(): Promise<void> {
    const confirmed = await this.confirm.ask({
      title: 'Nouveau mot de passe temporaire ?',
      message: "L'ancien mot de passe ne fonctionnera plus. Le patient devra changer le nouveau à sa connexion.",
      confirmLabel: 'Générer',
    });
    if (confirmed) this.show(this.http.post<Account>(this.url(this.patientId(), '/reset-password'), null));
  }
}
