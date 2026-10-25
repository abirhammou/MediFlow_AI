import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { AuthService, apiErrorMessage, homeFor } from '../../core/auth/auth.service';
import { AuthLayout } from '../../shared/auth-layout/auth-layout';

const MIN_LENGTH = 8;

/** /change-password: mandatory after a temporary password, available to everyone. */
@Component({
  selector: 'app-change-password',
  imports: [AuthLayout],
  template: `
    <app-auth-layout title="Changer de mot de passe"
                     [subtitle]="forced() ? 'Choisissez votre mot de passe personnel pour accéder à votre espace.' : 'Choisissez un nouveau mot de passe.'">
      <form (submit)="$event.preventDefault(); submit()" novalidate>
        @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }
        <div class="field">
          <label for="current">{{ forced() ? 'Mot de passe temporaire reçu' : 'Mot de passe actuel' }}</label>
          <input id="current" type="password" class="input" autocomplete="current-password"
                 [value]="current()" (input)="current.set($any($event.target).value)" />
        </div>
        <div class="field">
          <label for="next">Nouveau mot de passe ({{ min }} caractères minimum)</label>
          <input id="next" type="password" class="input" autocomplete="new-password"
                 [value]="next()" (input)="next.set($any($event.target).value)" />
        </div>
        <div class="field">
          <label for="confirm">Confirmez le nouveau mot de passe</label>
          <input id="confirm" type="password" class="input" autocomplete="new-password"
                 [value]="confirm()" (input)="confirm.set($any($event.target).value)" />
          @if (problem(); as p) { <span class="error">{{ p }}</span> }
        </div>
        <button type="submit" class="btn btn-primary" [disabled]="saving() || !!problem() || !current()">
          {{ saving() ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
        <button type="button" class="btn btn-outline" (click)="auth.logout()">Se déconnecter</button>
      </form>
    </app-auth-layout>
  `,
  styles: `
    form { display: flex; flex-direction: column; gap: 1rem; }
    .field { display: flex; flex-direction: column; gap: .375rem; font-size: .85rem; font-weight: 600; }
    .error { color: #b91c1c; font-size: .8rem; font-weight: 500; }
  `,
})
export class ChangePassword {
  protected auth = inject(AuthService);
  private router = inject(Router);
  protected readonly min = MIN_LENGTH;

  protected current = signal('');
  protected next = signal('');
  protected confirm = signal('');
  protected saving = signal(false);
  protected error = signal<string | null>(null);
  protected forced = computed(() => !!this.auth.user()?.must_change_password);
  protected problem = computed(() => {
    if (!this.next()) return null;
    if (this.next().length < MIN_LENGTH) return `Au moins ${MIN_LENGTH} caractères.`;
    if (this.next() === this.current()) return "Le nouveau mot de passe doit être différent de l'actuel.";
    if (this.confirm() && this.confirm() !== this.next()) return 'Les deux mots de passe ne correspondent pas.';
    return null;
  });

  constructor() {
    if (!this.auth.user()) this.auth.loadProfile().subscribe({ error: () => this.auth.logout() });
  }

  protected submit(): void {
    if (this.saving() || this.problem() || !this.current() || this.next() !== this.confirm()) {
      if (this.next() !== this.confirm()) this.error.set('Les deux mots de passe ne correspondent pas.');
      return;
    }
    this.saving.set(true);
    this.error.set(null);
    this.auth.changePassword(this.current(), this.next()).subscribe({
      next: (user) => this.router.navigateByUrl(homeFor(user)),
      error: (err) => {
        this.saving.set(false);
        this.error.set(apiErrorMessage(err));
      },
    });
  }
}
