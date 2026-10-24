import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Icon } from '../../shared/icon/icon';
import { ReportListItem, ReportOut, ReportsApi, ReportStatus } from './reports.api';

@Component({
  selector: 'app-report-writer',
  imports: [Icon, FormsModule, DatePipe],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#ede9fe;color:#7c3aed">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>ReportWriter AI</h1>
          <p>Comptes rendus structurés</p>
        </div>
      </div>

      <form class="filters" (ngSubmit)="applyFilters()">
        <input type="search" name="q" [(ngModel)]="q" placeholder="Rechercher par titre…" />
        <input type="text" name="patientId" [(ngModel)]="patientId" placeholder="ID patient" />
        <select name="status" [(ngModel)]="status">
          <option value="">Brouillons + finalisés</option>
          <option value="DRAFT">Brouillons</option>
          <option value="FINAL">Finalisés</option>
          <option value="ARCHIVED">Archivés</option>
        </select>
        <button type="submit" class="btn primary">Filtrer</button>
        <button type="button" class="btn" (click)="resetFilters()">Réinitialiser</button>
      </form>

      @if (error()) {
        <div class="alert error">{{ error() }}</div>
      }

      <div class="layout" [class.with-detail]="selected()">
        <section class="list">
          @if (loading()) {
            <p class="muted">Chargement…</p>
          } @else if (!reports().length) {
            <p class="muted">Aucun compte rendu trouvé.</p>
          } @else {
            <table>
              <thead>
                <tr>
                  <th>Titre</th>
                  <th>Statut</th>
                  <th>Patient</th>
                  <th>Mis à jour</th>
                </tr>
              </thead>
              <tbody>
                @for (r of reports(); track r.id) {
                  <tr [class.active]="selected()?.id === r.id" (click)="open(r)">
                    <td>{{ r.title }}</td>
                    <td><span class="badge" [attr.data-status]="r.status">{{ label(r.status) }}</span></td>
                    <td class="mono">{{ r.patient_id }}</td>
                    <td>{{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                  </tr>
                }
              </tbody>
            </table>

            <div class="pager">
              <button class="btn" [disabled]="page() <= 1" (click)="goTo(page() - 1)">Précédent</button>
              <span>Page {{ page() }} / {{ totalPages() }} · {{ total() }} résultat(s)</span>
              <button class="btn" [disabled]="page() >= totalPages()" (click)="goTo(page() + 1)">Suivant</button>
            </div>
          }
        </section>

        @if (selected(); as r) {
          <aside class="detail">
            <header>
              <h2>{{ r.title }}</h2>
              <button class="btn" (click)="closeDetail()">Fermer</button>
            </header>

            <p class="meta">
              <span class="badge" [attr.data-status]="r.status">{{ label(r.status) }}</span>
              Créé le {{ r.created_at | date: 'dd/MM/yyyy HH:mm' }}
              @if (r.archived_at) { · Archivé le {{ r.archived_at | date: 'dd/MM/yyyy HH:mm' }} }
            </p>
            <p class="meta mono">Médecin : {{ r.doctor_id }} · Patient : {{ r.patient_id }}</p>

            @if (r.warnings.length) {
              <div class="alert warn">
                <strong>Valeurs absentes des notes :</strong>
                <ul>
                  @for (w of r.warnings; track w) { <li>{{ w }}</li> }
                </ul>
              </div>
            }

            <h3>Notes brutes</h3>
            <pre>{{ r.raw_notes }}</pre>

            <h3>Compte rendu structuré</h3>
            @if (r.structured_content) {
              <pre>{{ r.structured_content }}</pre>
            } @else {
              <p class="muted">Pas encore généré par le médecin.</p>
            }

            @if (r.status !== 'ARCHIVED') {
              <button class="btn danger" [disabled]="archiving()" (click)="archive(r)">
                {{ archiving() ? 'Archivage…' : 'Archiver' }}
              </button>
            }
          </aside>
        }
      </div>
    </div>
  `,
  styleUrl: './report-writer.scss',
})
export class ReportWriter {
  private readonly api = inject(ReportsApi);

  // Filtres (liés au formulaire)
  q = '';
  patientId = '';
  status: ReportStatus | '' = '';

  // État
  readonly reports = signal<ReportListItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 10;
  readonly loading = signal(false);
  readonly archiving = signal(false);
  readonly error = signal<string | null>(null);
  readonly selected = signal<ReportOut | null>(null);

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .list({ status: this.status, patient_id: this.patientId, q: this.q, page: this.page(), size: this.size })
      .subscribe({
        next: (res) => {
          this.reports.set(res.items);
          this.total.set(res.total);
          this.loading.set(false);
        },
        error: (e) => this.fail(e),
      });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  resetFilters(): void {
    this.q = '';
    this.patientId = '';
    this.status = '';
    this.applyFilters();
  }

  goTo(page: number): void {
    this.page.set(page);
    this.load();
  }

  open(item: ReportListItem): void {
    this.error.set(null);
    this.api.get(item.id).subscribe({
      next: (report) => this.selected.set(report),
      error: (e) => this.fail(e),
    });
  }

  closeDetail(): void {
    this.selected.set(null);
  }

  archive(report: ReportOut): void {
    if (!confirm(`Archiver « ${report.title} » ? Le compte rendu ne sera plus modifiable.`)) return;
    this.archiving.set(true);
    this.api.archive(report.id).subscribe({
      next: (updated) => {
        this.selected.set(updated);
        this.archiving.set(false);
        this.load();
      },
      error: (e) => {
        this.archiving.set(false);
        this.fail(e);
      },
    });
  }

  label(status: ReportStatus): string {
    return { DRAFT: 'Brouillon', FINAL: 'Finalisé', ARCHIVED: 'Archivé' }[status];
  }

  private fail(e: unknown): void {
    this.loading.set(false);
    const err = e as HttpErrorResponse;
    this.error.set(
      err.error?.message ??
        (err.status === 403 ? 'Accès refusé.' : err.status === 404 ? 'Compte rendu introuvable.' : 'Une erreur est survenue.'),
    );
  }
}