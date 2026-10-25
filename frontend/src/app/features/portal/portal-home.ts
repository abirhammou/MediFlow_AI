import { Component, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { ReportListItem, ReportsApi } from '../../pages/report-writer/reports.api';
import { Icon } from '../../shared/icon/icon';
import { ToastService } from '../../shared/toast/toast.service';
import { formatBirthDate, formatDateTime } from '../patients/birth-date';
import { PatientFilesCard } from '../patients/patient-files/patient-files';
import { GENDER_LABELS } from '../patients/patient.model';
import { PortalProfile, PortalService } from './portal.service';

/** /portal "Mon dossier": my record, my finalized reports, my documents. */
@Component({
  selector: 'app-portal-home',
  imports: [Icon, PatientFilesCard],
  template: `
    <div class="portal">
      <header class="page-head">
        <h1>Mon dossier</h1>
        <p class="muted">Vos informations, vos comptes rendus finalisés et vos documents.</p>
      </header>
      @if (error()) { <div class="alert" role="alert">{{ error() }}</div> }

      @if (profile(); as p) {
        <section class="card card-pad">
          <h2><app-icon name="user" [size]="18" /> {{ p.firstName }} {{ p.lastName }} <span class="meta">· {{ p.recordNumber }}</span></h2>
          <dl class="profile">
            <div><dt>Date de naissance</dt><dd>{{ formatBirthDate(p.dateOfBirth) }}</dd></div>
            <div><dt>Sexe</dt><dd>{{ genderLabels[p.gender] }}</dd></div>
            <div><dt>Groupe sanguin</dt><dd>{{ p.bloodType || 'Non renseigné' }}</dd></div>
            <div><dt>Téléphone</dt><dd>{{ p.phone || 'Non renseigné' }}</dd></div>
            <div><dt>Email</dt><dd>{{ p.email || 'Non renseigné' }}</dd></div>
            <div><dt>Ville</dt><dd>{{ p.city || 'Non renseignée' }}</dd></div>
            <div><dt>Assurance</dt><dd>{{ p.insuranceProvider || 'Non renseignée' }}@if (p.insuranceNumber) { · {{ p.insuranceNumber }} }</dd></div>
          </dl>
          <p class="meta">Une information est inexacte ? Signalez-la au secrétariat lors de votre prochain passage.</p>
        </section>

        <section class="card card-pad">
          <h2><app-icon name="file-text" [size]="18" /> Mes comptes rendus</h2>
          @if (reports().length === 0) {
            <div class="empty"><strong>Aucun compte rendu finalisé</strong><span>Ils apparaissent ici dès que votre médecin les a validés.</span></div>
          } @else {
            <ul class="list">
              @for (r of reports(); track r.id) {
                <li>
                  <div class="main">
                    <strong>{{ r.title }}</strong>
                    <span class="meta">{{ r.doctor_name ? 'Dr ' + r.doctor_name + ' · ' : '' }}{{ formatDateTime(r.updated_at) }}</span>
                  </div>
                  <button type="button" class="btn btn-outline btn-sm" [disabled]="exporting() === r.id" (click)="pdf(r)">Télécharger (PDF)</button>
                </li>
              }
            </ul>
          }
        </section>

        <app-patient-files [patientId]="p.patientId" />
      } @else if (!error()) {
        <p class="muted">Chargement de votre dossier…</p>
      }
    </div>
  `,
  styleUrl: './portal.scss',
})
export class PortalHome {
  private portal = inject(PortalService);
  private reportsApi = inject(ReportsApi);
  private toasts = inject(ToastService);

  protected readonly genderLabels = GENDER_LABELS;
  protected readonly formatBirthDate = formatBirthDate;
  protected readonly formatDateTime = formatDateTime;
  protected profile = signal<PortalProfile | null>(null);
  protected reports = signal<ReportListItem[]>([]);
  protected error = signal<string | null>(null);
  protected exporting = signal<string | null>(null);

  constructor() {
    this.portal.me().subscribe({
      next: (profile) => this.profile.set(profile),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
    // The API only returns a patient's own FINAL reports.
    this.reportsApi.list({ page: 1, size: 50 }).subscribe({
      next: (page) => this.reports.set(page.items),
      error: () => this.reports.set([]),
    });
  }

  protected pdf(report: ReportListItem): void {
    this.exporting.set(report.id);
    this.reportsApi.downloadPdf(report.id, report.title).subscribe({
      next: () => this.exporting.set(null),
      error: (err) => {
        this.exporting.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }
}
