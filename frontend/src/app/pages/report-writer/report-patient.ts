import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import { ReportListItem, ReportOut, ReportsApi } from './reports.api';

const MISSING = 'Non précisé dans les notes.'; // même texte que MISSING_SECTION côté backend

@Component({
  selector: 'app-report-patient',
  imports: [Icon, DatePipe],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#fce7f3;color:#be185d">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>Mes comptes rendus</h1>
          <p>Les comptes rendus de vos consultations, validés par votre médecin</p>
        </div>
      </div>

      @if (error()) { <div class="alert error">{{ error() }}</div> }

      <div class="layout">
        <section class="card">
          <div class="card-head">
            <h2>Consultations <span class="muted">({{ total() }})</span></h2>
          </div>

          @if (loading()) {
            <p class="muted pad">Chargement…</p>
          } @else if (!reports().length) {
            <p class="muted pad">
              Aucun compte rendu disponible pour le moment. Ils apparaissent ici une fois validés par votre médecin.
            </p>
          } @else {
            <ul class="items">
              @for (r of reports(); track r.id) {
                <li>
                  <button type="button" class="item" [class.active]="selected()?.id === r.id" (click)="open(r)">
                    <b>{{ r.title }}</b>
                    <small>{{ r.updated_at | date: 'dd/MM/yyyy' }}</small>
                  </button>
                </li>
              }
            </ul>
            <div class="pager">
              <button type="button" class="btn" [disabled]="page() <= 1" (click)="goTo(page() - 1)">Précédent</button>
              <span>{{ page() }} / {{ totalPages() }}</span>
              <button type="button" class="btn" [disabled]="page() >= totalPages()" (click)="goTo(page() + 1)">Suivant</button>
            </div>
          }
        </section>

        <section class="card detail">
          @if (opening()) {
            <p class="muted pad">Ouverture…</p>
          } @else if (selected(); as r) {
            <div class="detail-head">
              <div>
                <span class="pill">Validé par votre médecin</span>
                <h2>{{ r.title }}</h2>
                <p class="muted">Compte rendu du {{ r.updated_at | date: 'dd/MM/yyyy' }}</p>
              </div>
              <div class="head-actions">
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
              </div>
            </div>

            @for (s of sections(); track s.title) {
              <article class="sec" [class.missing]="s.body === MISSING">
                <h3>{{ s.title }}</h3>
                <p>{{ s.body }}</p>
              </article>
            } @empty {
              <p class="muted">Ce compte rendu ne contient pas de texte.</p>
            }
          } @else {
            <div class="empty">
              <p>Sélectionnez un compte rendu pour le lire.</p>
            </div>
          }
        </section>
      </div>
    </div>
  `,
  styleUrl: './report-patient.scss',
})
export class ReportPatient {
  private readonly api = inject(ReportsApi);

  readonly MISSING = MISSING;

  readonly reports = signal<ReportListItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 10;
  readonly loading = signal(false);
  readonly opening = signal(false);
  readonly error = signal<string | null>(null);
  readonly selected = signal<ReportOut | null>(null);
  readonly copied = signal(false);
  readonly exporting = signal(false);

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
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    // Le backend ne renvoie au patient que ses propres comptes rendus finalisés.
    this.api.list({ page: this.page(), size: this.size }).subscribe({
      next: (res) => {
        this.reports.set(res.items);
        this.total.set(res.total);
        this.loading.set(false);
      },
      error: (e) => this.fail(e),
    });
  }

  goTo(page: number): void {
    this.page.set(page);
    this.load();
  }

  open(item: ReportListItem): void {
    this.error.set(null);
    this.opening.set(true);
    this.api.get(item.id).subscribe({
      next: (report) => {
        this.selected.set(report);
        this.opening.set(false);
      },
      error: (e) => this.fail(e),
    });
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

  private fail(e: unknown): void {
    this.loading.set(false);
    this.opening.set(false);
    this.error.set(apiErrorMessage(e));
  }
}