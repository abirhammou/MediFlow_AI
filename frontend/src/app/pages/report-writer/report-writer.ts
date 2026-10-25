import { Component, computed, inject } from '@angular/core';
import { AuthService } from '../../core/auth/auth.service';
import { ReportAdmin } from './report-admin';
import { ReportDoctor } from './report-doctor';
import { ReportPatient } from './report-patient';
import { ReportSecretary } from './report-secretary';

/** Aiguillage : chaque rôle voit sa propre version du module ReportWriter. */
@Component({
  selector: 'app-report-writer',
  imports: [ReportAdmin, ReportDoctor, ReportSecretary, ReportPatient],
  template: `
    @if (!role()) {
      <p class="loading">Chargement…</p>
    } @else {
      @switch (role()) {
        @case ('DOCTOR') { <app-report-doctor /> }
        @case ('ADMIN') { <app-report-admin /> }
        @case ('SECRETARY') { <app-report-secretary /> }
        @case ('PATIENT') { <app-report-patient /> }
        @default {
          <div class="no-access">
            <h2>ReportWriter AI</h2>
            <p>Cet espace n'est pas disponible pour votre rôle.</p>
          </div>
        }
      }
    }
  `,
  styles: [
    `.loading { padding: 32px; color: #64748b; }
     .no-access { max-width: 520px; margin: 48px auto; padding: 32px; text-align: center; background: #fff;
       border: 1px solid #e5e7eb; border-radius: 16px; color: #475569; }
     .no-access h2 { margin: 0 0 8px; color: #111827; }`,
  ],
})
export class ReportWriter {
  private readonly auth = inject(AuthService);
  readonly role = computed(() => this.auth.user()?.role ?? null);

  constructor() {
    // Après un rechargement de page le profil n'est pas encore connu : on le charge.
    if (!this.auth.user()) this.auth.loadProfile().subscribe({ error: () => undefined });
  }
}