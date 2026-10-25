import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable, of, switchMap, throwError } from 'rxjs';
import { apiErrorMessage } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import {
  PatientOption,
  ReportListItem,
  ReportOut,
  ReportsApi,
  ReportStatus,
  ReportUpdate,
} from './reports.api';

const MISSING = 'Non précisé dans les notes.'; // même texte que MISSING_SECTION côté backend
const SECTION_ICONS = ['🎯', '📚', '🩺', '🧾', '🗓️'];

@Component({
  selector: 'app-report-doctor',
  imports: [Icon, FormsModule, DatePipe],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#dbeafe;color:#2563eb">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>ReportWriter AI</h1>
          <p>Des notes brutes au compte rendu structuré</p>
        </div>
      </div>

      @if (error()) { <div class="alert error">{{ error() }}</div> }
      @if (info()) { <div class="alert ok">{{ info() }}</div> }

      <div class="cols">
        <!-- 1. Notes cliniques -->
        <section class="card">
          <div class="card-head">
            <h2>Notes cliniques</h2>
            <button type="button" class="chip" (click)="newReport()">+ Nouveau</button>
          </div>

          <label class="field">
            <span>Titre</span>
            <input type="text" [(ngModel)]="title" [disabled]="locked()" placeholder="Ex. Consultation du jour" maxlength="200" />
          </label>

          <label class="field">
            <span>Patient</span>
            @if (patients().length) {
              <select [(ngModel)]="patientId" [disabled]="!!current()">
                <option value="">— Choisir un patient —</option>
                @if (patientId && !patientName(patientId)) {
                  <option [value]="patientId">{{ shortId(patientId) }}</option>
                }
                @for (p of patients(); track p.id) {
                  <option [value]="p.id">{{ p.name }}</option>
                }
              </select>
            } @else {
              <input type="text" [(ngModel)]="patientId" [disabled]="!!current()" placeholder="24 caractères (ObjectId)" />
            }
          </label>

          <label class="field grow">
            <span>Notes brutes</span>
            <textarea [(ngModel)]="notes" [disabled]="locked()" rows="11" [attr.maxlength]="MAX"
                      placeholder="Saisissez vos notes de consultation…"></textarea>
            <small class="counter" [class.low]="notes.trim().length < MIN">{{ notes.length }}/{{ MAX }}</small>
          </label>

          @if (locked()) {
            <p class="hint">Ce compte rendu est verrouillé : il ne peut plus être modifié.</p>
          } @else {
            <div class="actions">
              <button type="button" class="btn" [disabled]="busy() !== null" (click)="save()">
                {{ busy() === 'save' ? 'Enregistrement…' : 'Enregistrer le brouillon' }}
              </button>
              <button type="button" class="btn primary wide" [disabled]="busy() !== null" (click)="generate()">
                ✨ {{ busy() === 'generate' ? 'Génération en cours…' : 'Générer le compte rendu' }}
              </button>
            </div>
          }
        </section>

        <!-- 2. Aperçu -->
        <section class="card">
          <div class="card-head">
            <h2>Aperçu du compte rendu</h2>
            @if (current(); as c) {
              <span class="pill" [attr.data-status]="c.status">
                {{ c.status === 'DRAFT' ? 'Brouillon — à valider par le médecin' : statusLabel(c.status) }}
              </span>
            }
          </div>

          @if (editing()) {
            <textarea class="edit" [(ngModel)]="draftContent" rows="18"></textarea>
            <div class="actions">
              <button type="button" class="btn" (click)="editing.set(false)">Annuler</button>
              <button type="button" class="btn primary" [disabled]="busy() !== null" (click)="saveEdit()">
                {{ busy() === 'edit' ? 'Enregistrement…' : 'Enregistrer les modifications' }}
              </button>
            </div>
          } @else if (sections().length) {
            <div class="sections">
              @for (s of sections(); track s.title; let i = $index) {
                <article class="sec" [class.missing]="s.body === MISSING">
                  <span class="sec-icon">{{ icon(i) }}</span>
                  <div>
                    <h3>{{ s.title }}</h3>
                    <p>{{ s.body }}</p>
                  </div>
                </article>
              }
            </div>
            <div class="actions end">
              @if (!locked()) {
                <button type="button" class="btn" (click)="startEdit()">✏️ Modifier</button>
              }
              <button type="button" class="btn" (click)="copy()">{{ copied() ? 'Copié ✓' : 'Copier le texte' }}</button>
              @if (current(); as c) {
                <button type="button" class="btn pdf" [disabled]="busy() !== null || exporting()" (click)="exportPdf(c)">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                       stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M12 3v12" />
                    <path d="m7 10 5 5 5-5" />
                    <path d="M5 21h14" />
                  </svg>
                  {{ exporting() ? 'Export…' : 'PDF' }}
                </button>
              }
              @if (!locked()) {
                <button type="button" class="btn primary" [disabled]="busy() !== null" (click)="finalize()">
                  {{ busy() === 'finalize' ? 'Validation…' : '🖊️ Valider et signer' }}
                </button>
              }
            </div>
          } @else {
            <div class="empty">
              <p>Rédigez vos notes, puis cliquez sur <b>« Générer le compte rendu »</b>.</p>
              <small>L'IA organise vos notes en cinq sections, sans rien ajouter.</small>
            </div>
          }
        </section>

        <!-- 3. Vérification -->
        <aside class="card check">
          <div class="check-head">
            <span class="shield">🛡️</span>
            <div>
              <h2>Vérification avant validation</h2>
              <p>Contrôle automatique du compte rendu par rapport à vos notes.</p>
            </div>
          </div>

          @if (!sections().length) {
            <p class="muted">La vérification apparaît dès que le compte rendu est généré.</p>
          } @else {
            <div class="item" [class.ok]="!missing().length">
              <header>
                <b>Sections manquantes</b>
                <span class="tag" [class.todo]="missing().length">{{ missing().length ? 'À compléter' : 'OK' }}</span>
              </header>
              @if (missing().length) {
                <ul>@for (m of missing(); track m.title) { <li>{{ m.title }}</li> }</ul>
              } @else {
                <p>Toutes les sections sont renseignées.</p>
              }
            </div>

            <div class="item" [class.ok]="!warnings().length">
              <header>
                <b>Valeurs à vérifier</b>
                <span class="tag" [class.warn]="warnings().length">{{ warnings().length ? 'À vérifier' : 'OK' }}</span>
              </header>
              @if (warnings().length) {
                <ul>@for (w of warnings(); track w) { <li>{{ w }}</li> }</ul>
              } @else {
                <p>Chaque valeur du compte rendu figure dans vos notes.</p>
              }
            </div>
          }

          <div class="note">
            <span>ℹ️</span>
            <p>
              <b>L'IA n'invente jamais de faits médicaux.</b>
              Seules vos notes lui sont transmises (ni nom, ni identifiant patient).
            </p>
          </div>
        </aside>
      </div>

      <!-- 4. Mes comptes rendus -->
      <section class="card list-card">
        <div class="card-head">
          <h2>Mes comptes rendus <span class="muted">({{ total() }})</span></h2>
          <form class="filters" (ngSubmit)="applyFilters()">
            <input type="search" name="q" [(ngModel)]="q" placeholder="Rechercher par titre…" />
            <select name="status" [(ngModel)]="statusFilter" (ngModelChange)="applyFilters()">
              <option value="">Actifs</option>
              <option value="DRAFT">Brouillons</option>
              <option value="FINAL">Finalisés</option>
              <option value="ARCHIVED">Archivés</option>
            </select>
            <button type="submit" class="btn">Rechercher</button>
          </form>
        </div>

        @if (!list().length) {
          <p class="muted pad">Aucun compte rendu trouvé.</p>
        } @else {
          <div class="table-wrap">
            <table>
              <thead>
                <tr><th>Titre</th><th>Patient</th><th>Statut</th><th>Mis à jour</th><th class="right">Actions</th></tr>
              </thead>
              <tbody>
                @for (r of list(); track r.id) {
                  <tr [class.active]="current()?.id === r.id">
                    <td class="strong">{{ r.title }}</td>
                    <td [class.mono]="!patientName(r.patient_id)">{{ patientLabel(r.patient_id) }}</td>
                    <td><span class="pill" [attr.data-status]="r.status">{{ statusLabel(r.status) }}</span></td>
                    <td>{{ r.updated_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    <td class="right">
                      <button type="button" class="btn small" (click)="openReport(r)">Ouvrir</button>
                      @if (r.status !== 'ARCHIVED') {
                        <button type="button" class="btn small danger" (click)="archiveItem(r)">Archiver</button>
                      }
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
    </div>
  `,
  styleUrl: './report-doctor.scss',
})
export class ReportDoctor {
  private readonly api = inject(ReportsApi);

  readonly MAX = 20000;
  readonly MIN = 20;
  readonly MISSING = MISSING;

  // Formulaire
  title = '';
  patientId = '';
  notes = '';
  draftContent = '';

  // Liste « Mes comptes rendus »
  q = '';
  statusFilter: ReportStatus | '' = '';
  readonly total = signal(0);
  readonly page = signal(1);
  readonly size = 8;
  readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / this.size)));

  // Patients (liste déroulante ; vide si le module patients n'est pas accessible)
  readonly patients = signal<PatientOption[]>([]);
  private readonly patientNames = computed(
    () => new Map(this.patients().map((p) => [p.id, p.name] as const)),
  );

  readonly list = signal<ReportListItem[]>([]);
  readonly current = signal<ReportOut | null>(null);
  readonly busy = signal<'save' | 'generate' | 'finalize' | 'edit' | null>(null);
  readonly editing = signal(false);
  readonly copied = signal(false);
  readonly exporting = signal(false);
  readonly error = signal<string | null>(null);
  readonly info = signal<string | null>(null);

  readonly locked = computed(() => {
    const c = this.current();
    return !!c && c.status !== 'DRAFT';
  });

  readonly sections = computed(() => {
    const content = this.current()?.structured_content;
    if (!content) return [];
    return content
      .split(/^## /m)
      .filter((part) => part.trim())
      .map((part) => {
        const [title, ...rest] = part.split('\n');
        return { title: title.trim(), body: rest.join('\n').trim() };
      });
  });

  readonly missing = computed(() => this.sections().filter((s) => s.body === MISSING));
  readonly warnings = computed(() => this.current()?.warnings ?? []);

  constructor() {
    this.refresh();
    this.api.patients().subscribe((p) => this.patients.set(p));
  }

  icon(i: number): string {
    return SECTION_ICONS[i % SECTION_ICONS.length];
  }

  statusLabel(status: string): string {
    return { DRAFT: 'Brouillon', FINAL: 'Finalisé', ARCHIVED: 'Archivé' }[status] ?? status;
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

  // ── Navigation ─────────────────────────────────────────────────────────────
  newReport(): void {
    this.current.set(null);
    this.title = this.patientId = this.notes = '';
    this.editing.set(false);
    this.clearMessages();
  }

  openById(id: string): void {
    if (!id) return this.newReport();
    this.clearMessages();
    this.api.get(id).subscribe({ next: (r) => this.load(r), error: (e) => this.fail(e) });
  }

  openReport(item: ReportListItem): void {
    this.openById(item.id);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  private load(r: ReportOut): void {
    this.current.set(r);
    this.title = r.title;
    this.patientId = r.patient_id;
    this.notes = r.raw_notes;
    this.editing.set(false);
  }

  // ── Liste ──────────────────────────────────────────────────────────────────
  private refresh(): void {
    this.api
      .list({ status: this.statusFilter, q: this.q, page: this.page(), size: this.size })
      .subscribe({
        next: (p) => {
          // Dernière page vidée (archivage) : on recule d'une page.
          if (!p.items.length && this.page() > 1) {
            this.page.set(this.page() - 1);
            this.refresh();
            return;
          }
          this.list.set(p.items);
          this.total.set(p.total);
        },
        error: (e) => this.fail(e),
      });
  }

  applyFilters(): void {
    this.page.set(1);
    this.refresh();
  }

  goTo(page: number): void {
    this.page.set(page);
    this.refresh();
  }

  archiveItem(item: ReportListItem): void {
    if (!confirm(`Archiver « ${item.title} » ? Il ne sera plus modifiable.`)) return;
    this.clearMessages();
    this.api.archive(item.id).subscribe({
      next: () => {
        if (this.current()?.id === item.id) this.newReport();
        this.info.set('Compte rendu archivé.');
        this.refresh();
      },
      error: (e) => this.fail(e),
    });
  }

  // ── Actions ────────────────────────────────────────────────────────────────
  /** Crée le brouillon, ou envoie uniquement ce qui a changé. */
  private persist(): Observable<ReportOut> {
    const cur = this.current();
    const title = this.title.trim();
    const notes = this.notes.trim();
    if (!title) return throwError(() => new Error('Donnez un titre au compte rendu.'));
    if (!notes) return throwError(() => new Error('Saisissez vos notes cliniques.'));

    if (!cur) {
      const patient = this.patientId.trim();
      if (!/^[0-9a-f]{24}$/i.test(patient)) {
        return throwError(
          () =>
            new Error(
              this.patients().length
                ? 'Choisissez un patient.'
                : "L'ID patient doit contenir 24 caractères hexadécimaux.",
            ),
        );
      }
      return this.api.create({ patient_id: patient, title, raw_notes: notes });
    }
    const changes: ReportUpdate = {};
    if (title !== cur.title) changes.title = title;
    if (notes !== cur.raw_notes) changes.raw_notes = notes;
    return Object.keys(changes).length ? this.api.update(cur.id, changes) : of(cur);
  }

  save(): void {
    this.start('save');
    this.persist().subscribe({
      next: (r) => this.done(r, 'Brouillon enregistré.'),
      error: (e) => this.fail(e),
    });
  }

  generate(): void {
    if (this.notes.trim().length < this.MIN) {
      this.error.set(`Vos notes sont trop courtes (${this.MIN} caractères minimum).`);
      return;
    }
    this.start('generate');
    this.persist()
      .pipe(switchMap((r) => this.api.generate(r.id)))
      .subscribe({
        next: (r) => this.done(r, 'Compte rendu généré. Relisez-le avant de le valider.'),
        error: (e) => this.fail(e),
      });
  }

  startEdit(): void {
    this.draftContent = this.current()?.structured_content ?? '';
    this.editing.set(true);
  }

  saveEdit(): void {
    const c = this.current();
    if (!c || !this.draftContent.trim()) return;
    this.start('edit');
    this.api.update(c.id, { structured_content: this.draftContent.trim() }).subscribe({
      next: (r) => this.done(r, 'Modifications enregistrées.'),
      error: (e) => this.fail(e),
    });
  }

  finalize(): void {
    const c = this.current();
    if (!c) return;
    const unverified = c.warnings.length > 0;
    const question = unverified
      ? `${c.warnings.length} valeur(s) ne figurent pas dans vos notes. Les avez-vous vérifiées ? Valider et signer ?`
      : 'Valider et signer ce compte rendu ? Il ne pourra plus être modifié.';
    if (!confirm(question)) return;
    this.start('finalize');
    this.api.finalize(c.id, unverified).subscribe({
      next: (r) => this.done(r, 'Compte rendu validé et verrouillé.'),
      error: (e) => this.fail(e),
    });
  }

  copy(): void {
    const text = this.current()?.structured_content;
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      this.copied.set(true);
      setTimeout(() => this.copied.set(false), 1500);
    });
  }

  /** Exporte la dernière version enregistrée du compte rendu. */
  exportPdf(report: ReportOut): void {
    this.clearMessages();
    this.exporting.set(true);
    this.api.downloadPdf(report.id, report.title).subscribe({
      next: () => this.exporting.set(false),
      error: () => {
        this.exporting.set(false);
        this.error.set("Impossible d'exporter le PDF.");
      },
    });
  }

  // ── Utilitaires ────────────────────────────────────────────────────────────
  private start(action: 'save' | 'generate' | 'finalize' | 'edit'): void {
    this.clearMessages();
    this.busy.set(action);
  }

  private done(r: ReportOut, message: string): void {
    this.load(r);
    this.busy.set(null);
    this.info.set(message);
    this.refresh();
  }

  private clearMessages(): void {
    this.error.set(null);
    this.info.set(null);
  }

  private fail(e: unknown): void {
    this.busy.set(null);
    this.error.set(e instanceof Error ? e.message : apiErrorMessage(e));
  }
}