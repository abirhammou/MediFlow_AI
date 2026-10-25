import { DatePipe } from '@angular/common';
import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import { PatientOption, ReportListItem, ReportOut, ReportsApi } from './reports.api';

const MISSING = 'Non précisé dans les notes.'; // même texte que MISSING_SECTION côté backend

@Component({
  selector: 'app-report-secretary',
  imports: [Icon, FormsModule, DatePipe],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#ccfbf1;color:#0f766e">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>ReportWriter AI</h1>
          <p>Comptes rendus finalisés</p>
        </div>
      </div>

      <div class="banner">
        <span>🔒</span>
        <p>
          <b>Lecture seule.</b>
          Vous voyez uniquement les comptes rendus validés par les médecins. Les notes brutes et les brouillons ne vous sont pas accessibles.
        </p>
      </div>

      @if (error()) { <div class="alert error">{{ error() }}</div> }

      <section class="card">
        <div class="card-head">
          <h2>Comptes rendus finalisés <span class="muted">({{ total() }})</span></h2>
          <form class="filters" (ngSubmit)="applyFilters()">
            <input type="search" name="q" [(ngModel)]="q" placeholder="Rechercher par titre…" />
            @if (patients().length) {
              <select name="patientId" [(ngModel)]="patientId" (ngModelChange)="applyFilters()">
                <option value="">Tous les patients</option>
                @for (p of patients(); track p.id) {
                  <option [value]="p.id">{{ p.name }}</option>
                }
              </select>
            } @else {
              <input type="text" name="patientId" [(ngModel)]="patientId" placeholder="ID patient" />
            }
            <button type="submit" class="btn primary">Filtrer</button>
          </form>
        </div>

        @if (loading()) {
          <p class="muted pad">Chargement…</p>
        } @else if (!reports().length) {
          <p class="muted pad">Aucun compte rendu finalisé pour le moment.</p>
        } @else {
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Titre</th><th>Patient</th><th>Médecin</th><th>Validé le</th><th class="right">Actions</th></tr>
              </thead>
              <tbody>
                @for (r of reports(); track r.id) {
                  <tr>
                    <td class="strong">{{ r.title }}</td>
                    <td [class.mono]="!patientName(r.patient_id)">{{ patientLabel(r.patient_id) }}</td>
                    <td class="mono">{{ shortId(r.doctor_id) }}</td>
                    <td>{{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td class="right">
                      <button type="button" class="btn small" [disabled]="opening() === r.id" (click)="open(r)">
                        {{ opening() === r.id ? 'Ouverture…' : 'Consulter' }}
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="pager">
            <button type="button" class="btn" [disabled]="page() <= 1" (click)="goTo(page() - 1)">Précédent</button>
            <span>Page {{ page() }} / {{ totalPages() }} · {{ total() }} résultat(s)</span>
            <button type="button" class="btn" [disabled]="page() >= totalPages()" (click)="goTo(page() + 1)">Suivant</button>
          </div>
        }
      </section>

      @if (selected(); as r) {
        <div class="backdrop" (click)="close()">
          <div class="modal" role="dialog" aria-modal="true" [attr.aria-label]="r.title" (click)="$event.stopPropagation()">
            <header class="modal-head">
              <div>
                <span class="pill">Finalisé</span>
                <h2>{{ r.title }}</h2>
                <p class="muted">Validé le {{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }} · {{ patientLabel(r.patient_id) }}</p>
              </div>
              <button type="button" class="close" aria-label="Fermer" (click)="close()">✕</button>
            </header>

            <div class="modal-body">
              @for (s of sections(); track s.title) {
                <article class="sec" [class.missing]="s.body === MISSING">
                  <h3>{{ s.title }}</h3>
                  <p>{{ s.body }}</p>
                </article>
              } @empty {
                <p class="muted">Ce compte rendu ne contient pas de texte.</p>
              }
            </div>

            <footer class="modal-foot">
              <button type="button" class="btn" (click)="copy(r)">{{ copied() ? 'Copié ✓' : 'Copier le texte' }}</button>
              <button type="button" class="btn pdf" [disabled]="exporting()" (click)="exportPdf(r)">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M12 3v12" />
                  <path d="m7 10 5 5 5-5" />
                  <path d="M5 21h14" />
                </svg>
                {{ exporting() ? 'Export…' : 'Exporter en PDF' }}
              </button>
              <button type="button" class="btn primary" (click)="close()">Fermer</button>
            </footer>
          </div>
        </div>
      }
    </div>
  `,
  styleUrl: './report-secretary.scss',
})
export class ReportSecretary {
  private readonly api = inject(ReportsApi);

  readonly MISSING = MISSING;

  // Filtres
  q = '';
  patientId = '';

  // État
  readonly reports = signal<ReportListItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 10;
  readonly loading = signal(false);
  readonly opening = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly selected = signal<ReportOut | null>(null);
  readonly copied = signal(false);
  readonly exporting = signal(false);

  // Patients (liste déroulante ; vide si le module patients n'est pas accessible)
  readonly patients = signal<PatientOption[]>([]);
  private readonly patientNames = computed(
    () => new Map(this.patients().map((p) => [p.id, p.name] as const)),
  );

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  readonly sections = computed(() => {
    const content = this.selected()?.structured_content;
    if (!content) return [];
    return content
      .split(/^## /m)
      .filter((part) => part.trim())
      .map((part) => {
        const [title, ...rest] = part.split('\n');
        return { title: title.trim(), body: rest.join('\n').trim() };
      });
  });

  constructor() {
    this.load();
    this.api.patients().subscribe((p) => this.patients.set(p));
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.close();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    // Le backend ne renvoie à la secrétaire que les comptes rendus finalisés.
    this.api
      .list({ patient_id: this.patientId, q: this.q, page: this.page(), size: this.size })
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

  goTo(page: number): void {
    this.page.set(page);
    this.load();
  }

  open(item: ReportListItem): void {
    this.error.set(null);
    this.opening.set(item.id);
    this.api.get(item.id).subscribe({
      next: (report) => {
        this.selected.set(report);
        this.opening.set(null);
      },
      error: (e) => this.fail(e),
    });
  }

  close(): void {
    this.selected.set(null);
  }

  copy(report: ReportOut): void {
    navigator.clipboard.writeText(`${report.title}\n\n${report.structured_content ?? ''}`).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    });
  }

  exportPdf(report: ReportOut): void {
    this.error.set(null);
    this.exporting.set(true);
    this.api.downloadPdf(report.id, report.title).subscribe({
      next: () => this.exporting.set(false),
      error: () => {
        this.exporting.set(false);
        this.error.set("Impossible d'exporter le PDF.");
      },
    });
  }

  shortId(id: string): string {
    return '…' + id.slice(-6);
  }

  patientName(id: string): string | null {
    return this.patientNames().get(id) ?? null;
  }

  patientLabel(id: string): string {
    return this.patientName(id) ?? this.shortId(id);
  }

  private fail(e: unknown): void {
    this.loading.set(false);
    this.opening.set(null);
    this.error.set(apiErrorMessage(e));
  }
}