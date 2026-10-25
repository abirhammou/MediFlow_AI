import { DatePipe } from '@angular/common';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Component, HostListener, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Icon } from '../../shared/icon/icon';
import { ReportListItem, ReportOut, ReportsApi, ReportStats, ReportStatus } from './reports.api';

const STATUS_LABEL: Record<ReportStatus, string> = {
  DRAFT: 'Brouillon',
  FINAL: 'Finalisé',
  ARCHIVED: 'Archivé',
};
const STATUS_COLOR: Record<ReportStatus, string> = {
  DRAFT: '#f59e0b',
  FINAL: '#10b981',
  ARCHIVED: '#94a3b8',
};

@Component({
  selector: 'app-report-admin',
  imports: [Icon, FormsModule, DatePipe],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#ede9fe;color:#7c3aed">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>ReportWriter AI</h1>
          <p>Suivi des comptes rendus structurés</p>
        </div>
      </div>

      @if (error()) {
        <div class="alert error">{{ error() }}</div>
      }

      <!-- KPI -->
      <section class="kpis">
        <article class="kpi">
          <span class="kpi-icon" style="background:#ede9fe;color:#7c3aed">∑</span>
          <div><small>Comptes rendus</small><strong>{{ totalReports() }}</strong></div>
        </article>
        <article class="kpi">
          <span class="kpi-icon" style="background:#fef3c7;color:#d97706">✎</span>
          <div><small>En attente de validation</small><strong>{{ stats()?.draft ?? '–' }}</strong></div>
        </article>
        <article class="kpi">
          <span class="kpi-icon" style="background:#d1fae5;color:#059669">✓</span>
          <div><small>Finalisés</small><strong>{{ stats()?.final ?? '–' }}</strong></div>
        </article>
        <article class="kpi">
          <span class="kpi-icon" style="background:#e2e8f0;color:#475569">▣</span>
          <div><small>Archivés</small><strong>{{ stats()?.archived ?? '–' }}</strong></div>
        </article>
      </section>

      <div class="grid">
        <!-- Tableau -->
        <section class="card">
          <div class="card-head">
            <h2>Comptes rendus</h2>
            <form class="filters" (ngSubmit)="applyFilters()">
              <input type="search" name="q" [(ngModel)]="q" placeholder="Titre…" />
              <input type="text" name="patientId" [(ngModel)]="patientId" placeholder="ID patient" />
              <select name="status" [(ngModel)]="status" (ngModelChange)="applyFilters()">
                <option value="">Actifs</option>
                <option value="DRAFT">Brouillons</option>
                <option value="FINAL">Finalisés</option>
                <option value="ARCHIVED">Archivés</option>
              </select>
              <button type="submit" class="btn primary">Filtrer</button>
            </form>
          </div>

          @if (loading()) {
            <p class="muted pad">Chargement…</p>
          } @else if (!reports().length) {
            <p class="muted pad">Aucun compte rendu trouvé.</p>
          } @else {
            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>Titre</th><th>Patient</th><th>Statut</th><th>Mis à jour</th><th class="right">Actions</th></tr>
                </thead>
                <tbody>
                  @for (r of reports(); track r.id) {
                    <tr>
                      <td class="strong">{{ r.title }}</td>
                      <td class="mono">{{ patientLabel(r.patient_id) }}</td>
                      <td><span class="badge" [attr.data-status]="r.status">{{ label(r.status) }}</span></td>
                      <td>{{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                      <td class="right">
                        <button class="icon-btn" title="Voir le compte rendu" aria-label="Voir le compte rendu"
                                [disabled]="opening() === r.id" (click)="open(r)">
                          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="pager">
              <button class="btn" [disabled]="page() <= 1" (click)="goTo(page() - 1)">Précédent</button>
              <span>Page {{ page() }} / {{ totalPages() }} · {{ total() }} résultat(s)</span>
              <button class="btn" [disabled]="page() >= totalPages()" (click)="goTo(page() + 1)">Suivant</button>
            </div>
          }
        </section>

        <!-- Colonne droite -->
        <div class="side">
          <section class="card">
            <div class="card-head"><h2>Activité · 30 derniers jours</h2></div>
            @if (chart(); as c) {
              <svg viewBox="0 0 600 180" class="chart" preserveAspectRatio="none" role="img"
                   aria-label="Comptes rendus créés par jour">
                <defs>
                  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#7c3aed" stop-opacity=".25" />
                    <stop offset="100%" stop-color="#7c3aed" stop-opacity="0" />
                  </linearGradient>
                </defs>
                @for (y of [0, 1, 2, 3]; track y) {
                  <line x1="0" x2="600" [attr.y1]="10 + y * 50" [attr.y2]="10 + y * 50" stroke="#eef2f7" />
                }
                <path [attr.d]="c.area" fill="url(#area)" />
                <path [attr.d]="c.line" fill="none" stroke="#7c3aed" stroke-width="2.5" stroke-linejoin="round" />
              </svg>
              <p class="chart-foot muted">Maximum : {{ c.max }} par jour (sur les 100 derniers comptes rendus)</p>
            }
          </section>

          <section class="card">
            <div class="card-head"><h2>Répartition par statut</h2></div>
            <div class="donut-row">
              <svg viewBox="0 0 140 140" width="140" height="140" role="img" aria-label="Répartition par statut">
                <circle cx="70" cy="70" r="50" fill="none" stroke="#f1f5f9" stroke-width="18" />
                @for (s of donut(); track s.status) {
                  <circle cx="70" cy="70" r="50" fill="none" stroke-width="18" [attr.stroke]="s.color"
                          [attr.stroke-dasharray]="s.dash" [attr.stroke-dashoffset]="s.offset"
                          transform="rotate(-90 70 70)" />
                }
                <text x="70" y="68" text-anchor="middle" class="donut-total">{{ totalReports() }}</text>
                <text x="70" y="86" text-anchor="middle" class="donut-sub">au total</text>
              </svg>
              <ul class="legend">
                @for (s of donut(); track s.status) {
                  <li>
                    <i [style.background]="s.color"></i>{{ label(s.status) }}
                    <b>{{ s.value }}</b><em>{{ s.pct }}%</em>
                  </li>
                }
              </ul>
            </div>
          </section>
        </div>
      </div>

      <!-- Popup détail -->
      @if (selected(); as r) {
        <div class="backdrop" (click)="closeDetail()">
          <div class="modal" role="dialog" aria-modal="true" [attr.aria-label]="r.title" (click)="$event.stopPropagation()">
            <header class="modal-head">
              <div class="head-icon"><app-icon name="file-text" [size]="26" /></div>
              <div class="head-text">
                <span class="badge" [attr.data-status]="r.status">{{ label(r.status) }}</span>
                <h2>{{ r.title }}</h2>
                <p>Compte rendu du {{ r.created_at | date: 'dd/MM/yyyy' }}</p>
              </div>
              <button class="close" aria-label="Fermer" (click)="closeDetail()">✕</button>
            </header>

            <div class="modal-body">
              <main class="content">
                @if (r.warnings.length) {
                  <div class="alert warn">
                    <strong>⚠ Valeurs absentes des notes du médecin</strong>
                    <ul>@for (w of r.warnings; track w) { <li>{{ w }}</li> }</ul>
                  </div>
                }

                <h3>Compte rendu structuré</h3>
                @if (sections().length) {
                  @for (s of sections(); track s.title; let i = $index) {
                    <article class="section" [attr.data-i]="i % 5">
                      <h4>{{ s.title }}</h4>
                      <p>{{ s.body }}</p>
                    </article>
                  }
                } @else {
                  <div class="empty">Le médecin n'a pas encore généré le compte rendu structuré.</div>
                }

                <details class="notes">
                  <summary>Notes brutes du médecin</summary>
                  <pre>{{ r.raw_notes }}</pre>
                </details>
              </main>

              <aside class="meta">
                <div class="person">
                  <span class="avatar patient">{{ initials(patientName(r.patient_id)) }}</span>
                  <div>
                    <small>Patient</small>
                    <strong>{{ patientName(r.patient_id) ?? 'Patient' }}</strong>
                    <code [title]="r.patient_id">{{ shortId(r.patient_id) }}</code>
                  </div>
                </div>
                <div class="person">
                  <span class="avatar doctor">{{ initials(doctorName(r.doctor_id)) }}</span>
                  <div>
                    <small>Médecin</small>
                    <strong>{{ doctorName(r.doctor_id) ?? 'Médecin' }}</strong>
                    <code [title]="r.doctor_id">{{ shortId(r.doctor_id) }}</code>
                  </div>
                </div>

                <h5>Historique</h5>
                <ol class="timeline">
                  <li><b>Créé</b><span>{{ r.created_at | date: 'dd/MM/yyyy HH:mm' }}</span></li>
                  @if (r.updated_at !== r.created_at) {
                    <li><b>Modifié</b><span>{{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }}</span></li>
                  }
                  @if (r.archived_at) {
                    <li class="archived"><b>Archivé</b><span>{{ r.archived_at | date: 'dd/MM/yyyy HH:mm' }}</span></li>
                  }
                </ol>
              </aside>
            </div>

            <footer class="modal-foot">
              @if (r.structured_content) {
                <button class="btn" (click)="copy(r)">{{ copied() ? 'Copié ✓' : 'Copier le texte' }}</button>
              }
              @if (r.status !== 'ARCHIVED' && canArchive()) {
                <button class="btn danger" [disabled]="archiving()" (click)="archive(r)">
                  {{ archiving() ? 'Archivage…' : 'Archiver' }}
                </button>
              }
              <button class="btn primary" (click)="closeDetail()">Fermer</button>
            </footer>
          </div>
        </div>
      }
    </div>
  `,
  styleUrl: './report-admin.scss',
})
export class ReportAdmin {
  private readonly api = inject(ReportsApi);
  readonly canArchive = input(true); // false pour la secrétaire (lecture seule)

  // Filtres
  q = '';
  patientId = '';
  status: ReportStatus | '' = '';

  // État
  readonly reports = signal<ReportListItem[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 8;
  readonly loading = signal(false);
  readonly opening = signal<string | null>(null);
  readonly archiving = signal(false);
  readonly error = signal<string | null>(null);
  readonly selected = signal<ReportOut | null>(null);
  readonly stats = signal<ReportStats | null>(null);
  readonly doctors = signal<Record<string, string>>({});
  readonly patients = signal<Record<string, string>>({});
  readonly copied = signal(false);

  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));
  readonly totalReports = computed(() => {
    const s = this.stats();
    return s ? s.draft + s.final + s.archived : '–';
  });

  /** Découpe « ## Titre\ntexte » en sections lisibles. */
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

  readonly donut = computed(() => {
    const s = this.stats();
    if (!s) return [];
    const total = s.draft + s.final + s.archived;
    const circumference = 2 * Math.PI * 50;
    let offset = 0;
    return (['FINAL', 'DRAFT', 'ARCHIVED'] as ReportStatus[]).map((status) => {
      const value = { DRAFT: s.draft, FINAL: s.final, ARCHIVED: s.archived }[status];
      const length = total ? (value / total) * circumference : 0;
      const segment = {
        status,
        value,
        color: STATUS_COLOR[status],
        pct: total ? Math.round((value / total) * 100) : 0,
        dash: `${length} ${circumference - length}`,
        offset: -offset,
      };
      offset += length;
      return segment;
    });
  });

  /** Comptes rendus créés par jour sur 30 jours, tracés en SVG. */
  readonly chart = computed(() => {
    const s = this.stats();
    if (!s) return null;
    const days = 30;
    const counts = new Array<number>(days).fill(0);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (const r of s.recent) {
      const d = new Date(r.created_at);
      d.setHours(0, 0, 0, 0);
      const ago = Math.round((today.getTime() - d.getTime()) / 86_400_000);
      if (ago >= 0 && ago < days) counts[days - 1 - ago]++;
    }
    const max = Math.max(1, ...counts);
    const pts = counts.map((c, i) => [(i / (days - 1)) * 600, 160 - (c / max) * 140] as const);
    const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
    return { line, area: `${line} L600,170 L0,170 Z`, max: Math.max(...counts) };
  });

  constructor() {
    this.load();
    this.loadStats();
    this.api.doctors().subscribe((m) => this.doctors.set(m));
    // TODO patients : this.api.patients().subscribe((m) => this.patients.set(m));
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.closeDetail();
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

  loadStats(): void {
    this.api.stats().subscribe({ next: (s) => this.stats.set(s), error: (e) => this.fail(e) });
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
      error: (e) => {
        this.opening.set(null);
        this.fail(e);
      },
    });
  }

  closeDetail(): void {
    this.selected.set(null);
  }

  archive(report: ReportOut): void {
    if (!confirm(`Archiver « ${report.title} » ? Il ne sera plus modifiable.`)) return;
    this.archiving.set(true);
    this.api.archive(report.id).subscribe({
      next: (updated) => {
        this.selected.set(updated);
        this.archiving.set(false);
        this.load();
        this.loadStats();
      },
      error: (e) => {
        this.archiving.set(false);
        this.fail(e);
      },
    });
  }

  label(status: ReportStatus): string {
    return STATUS_LABEL[status];
  }

  // Le backend des comptes rendus ne renvoie que des identifiants : les noms viennent d'autres modules.
  patientName(id: string): string | null {
    return this.patients()[id] ?? null;
  }

  doctorName(id: string): string | null {
    return this.doctors()[id] ?? null;
  }

  patientLabel(id: string): string {
    return this.patientName(id) ?? this.shortId(id);
  }

  shortId(id: string): string {
    return '…' + id.slice(-6);
  }

  initials(name: string | null): string {
    if (!name) return '?';
    const words = name.replace(/^Dr\.?\s+/i, '').split(/\s+/).filter(Boolean);
    return (words[0]?.[0] ?? '?').toUpperCase() + (words[1]?.[0] ?? '').toUpperCase();
  }

  copy(report: ReportOut): void {
    navigator.clipboard.writeText(`${report.title}\n\n${report.structured_content ?? ''}`).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    });
  }

  private fail(e: unknown): void {
    this.loading.set(false);
    this.opening.set(null);
    this.error.set(apiErrorMessage(e));
  }
}