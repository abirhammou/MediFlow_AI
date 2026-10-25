import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { of, switchMap, throwError } from 'rxjs';
import { apiErrorMessage, AuthService } from '../../core/auth/auth.service';
import { Icon } from '../../shared/icon/icon';
import {
  DocumentCreate,
  DocumentExtraction,
  DocumentListItem,
  DocumentReview,
  DocumentStatus,
  DocumentUpdate,
  ExtractedFieldProposal,
  MedDocApi,
  MedicalDocument,
} from './med-doc.api';

interface ReviewField {
  name: string;
  value: string;
}

@Component({
  selector: 'app-med-doc',
  imports: [DatePipe, FormsModule, Icon],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#dcfce7;color:#16a34a">
          <app-icon name="file-plus" [size]="24" />
        </div>
        <div>
          <h1>MedDoc AI</h1>
          <p>Documents médicaux et extraction assistée</p>
        </div>
        @if (canWrite()) {
          <button type="button" class="btn primary new-button" (click)="newDocument()">+ Nouveau document</button>
        }
      </div>

      @if (error()) { <div class="alert error" role="alert">{{ error() }}</div> }
      @if (info()) { <div class="alert ok" role="status">{{ info() }}</div> }

      <div class="layout">
        <section class="card list-card">
          <div class="card-head">
            <div>
              <h2>{{ isPatient() ? 'Mes documents validés' : 'Historique des documents' }}</h2>
              <p class="muted">{{ pageTotal() }} document(s)</p>
            </div>
            @if (!isPatient()) {
              <form class="filter" (ngSubmit)="applyFilter()">
                <input name="patientIdFilter" [(ngModel)]="patientFilter" placeholder="ID patient" aria-label="Filtrer par ID patient" />
                <button type="submit" class="btn">Filtrer</button>
              </form>
            }
          </div>

          @if (loading()) {
            <p class="empty">Chargement des documents…</p>
          } @else if (!documents().length) {
            <p class="empty">Aucun document à afficher.</p>
          } @else {
            <div class="document-list">
              @for (document of documents(); track document.id) {
                <button type="button" class="document-row" [class.selected]="current()?.id === document.id"
                        (click)="open(document.id)">
                  <span class="row-main">
                    <strong>{{ document.title }}</strong>
                    <small>{{ document.patient_id }}</small>
                  </span>
                  <span class="row-meta">
                    <span class="status" [attr.data-status]="document.status">{{ statusLabel(document.status) }}</span>
                    <small>{{ document.created_at | date:'dd/MM/yyyy' }}</small>
                  </span>
                </button>
              }
            </div>
          }
        </section>

        <section class="card detail-card">
          <div class="card-head">
            <div>
              <h2>{{ createMode() ? 'Nouveau document' : current()?.title || 'Détail du document' }}</h2>
              @if (current(); as document) {
                <span class="status" [attr.data-status]="document.status">{{ statusLabel(document.status) }}</span>
              }
            </div>
            @if (current() && canDelete()) {
              <button type="button" class="btn danger" [disabled]="busy() !== null" (click)="remove()">Supprimer</button>
            }
          </div>

          @if (createMode() || current()) {
            <label class="field">
              <span>Titre</span>
              <input [(ngModel)]="title" [disabled]="!canWrite() || busy() !== null" maxlength="200" />
            </label>
            @if (createMode()) {
              <label class="field">
                <span>ID du dossier patient</span>
                <input [(ngModel)]="patientId" [disabled]="busy() !== null" placeholder="ObjectId du dossier patient" />
              </label>
            } @else if (current(); as document) {
              <label class="field">
                <span>ID du dossier patient</span>
                <input [value]="document.patient_id" disabled />
              </label>
            }
            <label class="field">
              <span>Texte brut du document</span>
              <textarea [(ngModel)]="rawText" [disabled]="!canWrite() || busy() !== null" rows="8"></textarea>
            </label>

            @if (current(); as document) {
              <div class="field">
                <span>Catégorie validée</span>
                <input [value]="document.category_code || 'Non définie'" disabled />
              </div>
              @if (document.extracted_fields.length) {
                <section class="fields">
                  <h3>Informations enregistrées</h3>
                  @for (field of document.extracted_fields; track $index) {
                    <div class="extracted-row">
                      <strong>{{ field.name }}</strong>
                      <span>{{ field.value ?? 'Non trouvé' }}</span>
                      <span class="status" [attr.data-status]="field.status">{{ statusLabel(field.status) }}</span>
                      @if (field.validated_at) {
                        <small>Revu le {{ field.validated_at | date:'dd/MM/yyyy HH:mm' }}</small>
                      }
                    </div>
                  }
                </section>
              }
            }

            @if (canWrite()) {
              <div class="actions">
                <button type="button" class="btn primary" [disabled]="busy() !== null" (click)="save()">
                  {{ busy() === 'save' ? 'Enregistrement…' : 'Enregistrer' }}
                </button>
                @if (current()) {
                  <button type="button" class="btn" [disabled]="busy() !== null" (click)="extract()">
                    {{ busy() === 'extract' ? 'Extraction…' : '✨ Extraire avec l’IA' }}
                  </button>
                }
              </div>
            }

            @if (extraction(); as proposal) {
              <section class="review">
                <h3>Proposition IA — à relire et corriger</h3>
                @if (proposal.warnings.length) {
                  <ul class="warnings">
                    @for (warning of proposal.warnings; track $index) { <li>{{ warning }}</li> }
                  </ul>
                }
                @if (!reviewFields().length) {
                  <p class="muted">Aucun champ proposé.</p>
                }
                @for (field of reviewFields(); track $index) {
                  <div class="proposal-row">
                    <label class="field">
                      <span>Champ</span>
                      <input [ngModel]="field.name" (ngModelChange)="updateField($index, 'name', $event)" />
                    </label>
                    <label class="field">
                      <span>Valeur (vide = non trouvé)</span>
                      <input [ngModel]="field.value" (ngModelChange)="updateField($index, 'value', $event)" />
                    </label>
                    <button type="button" class="btn danger" (click)="removeField($index)">Retirer</button>
                  </div>
                }
                <label class="field">
                  <span>Catégorie proposée (code)</span>
                  <input [(ngModel)]="reviewCategory" placeholder="Code de catégorie" />
                </label>
                @if (canReview()) {
                  <div class="actions">
                    <button type="button" class="btn primary" [disabled]="busy() !== null || !reviewFields().length" (click)="review('VALIDATED')">
                      {{ busy() === 'review' ? 'Enregistrement…' : 'Valider les champs' }}
                    </button>
                    <button type="button" class="btn danger" [disabled]="busy() !== null || !reviewFields().length" (click)="review('REJECTED')">
                      Rejeter les champs
                    </button>
                  </div>
                } @else {
                  <p class="hint">Vous pouvez corriger le texte, mais seul un médecin ou un administrateur peut valider ou rejeter les champs.</p>
                }
              </section>
            }
          } @else {
            <p class="empty">Sélectionnez un document dans l’historique ou créez-en un nouveau.</p>
          }
        </section>
      </div>
    </div>
  `,
  styleUrl: './med-doc.scss',
})
export class MedDoc {
  private readonly api = inject(MedDocApi);
  private readonly auth = inject(AuthService);

  readonly role = computed(() => this.auth.user()?.role ?? null);
  readonly isPatient = computed(() => this.role() === 'PATIENT');
  readonly canWrite = computed(() => ['DOCTOR', 'SECRETARY', 'ADMIN_STAFF', 'ADMIN'].includes(this.role() ?? ''));
  readonly canDelete = computed(() => this.role() === 'ADMIN');
  readonly canReview = computed(() => ['DOCTOR', 'ADMIN'].includes(this.role() ?? ''));

  readonly documents = signal<DocumentListItem[]>([]);
  readonly pageTotal = signal(0);
  readonly current = signal<MedicalDocument | null>(null);
  readonly extraction = signal<DocumentExtraction | null>(null);
  readonly reviewFields = signal<ReviewField[]>([]);
  readonly loading = signal(false);
  readonly busy = signal<'save' | 'extract' | 'review' | 'delete' | null>(null);
  readonly error = signal<string | null>(null);
  readonly info = signal<string | null>(null);
  readonly createMode = signal(false);

  patientFilter = '';
  patientId = '';
  title = '';
  rawText = '';
  reviewCategory = '';

  constructor() {
    if (!this.auth.user()) {
      this.auth.loadProfile().subscribe({
        next: () => this.refresh(),
        error: (e: unknown) => this.fail(e),
      });
    } else {
      this.refresh();
    }
  }

  statusLabel(status: DocumentStatus): string {
    return { DRAFT: 'Brouillon', VALIDATED: 'Validé', REJECTED: 'Rejeté' }[status];
  }

  newDocument(): void {
    this.current.set(null);
    this.createMode.set(true);
    this.title = '';
    this.patientId = '';
    this.rawText = '';
    this.clearProposal();
    this.clearMessages();
  }

  applyFilter(): void {
    this.refresh();
  }

  open(id: string): void {
    this.clearMessages();
    this.api.get(id).subscribe({
      next: (document) => this.load(document),
      error: (e: unknown) => this.fail(e),
    });
  }

  save(): void {
    this.start('save');
    this.persist().subscribe({
      next: (document) => this.finish(document, 'Document enregistré.'),
      error: (e: unknown) => this.fail(e),
    });
  }

  extract(): void {
    this.start('extract');
    this.persist()
      .pipe(
        switchMap((document) => {
          this.load(document);
          return this.api.extract(document.id);
        }),
      )
      .subscribe({
        next: (proposal) => {
          this.extraction.set(proposal);
          this.reviewFields.set(proposal.fields.map((field) => ({
            name: field.name,
            value: field.value ?? '',
          })));
          this.reviewCategory = proposal.suggested_category_code ?? '';
          this.busy.set(null);
          this.info.set('Extraction terminée. Relisez et corrigez la proposition avant validation.');
          this.refresh();
        },
        error: (e: unknown) => this.fail(e),
      });
  }

  updateField(index: number, key: keyof ReviewField, value: string): void {
    this.reviewFields.update((fields) =>
      fields.map((field, currentIndex) =>
        currentIndex === index ? { ...field, [key]: value } : field,
      ),
    );
  }

  removeField(index: number): void {
    this.reviewFields.update((fields) => fields.filter((_, currentIndex) => currentIndex !== index));
  }

  review(status: 'VALIDATED' | 'REJECTED'): void {
    const document = this.current();
    if (!document) return;
    const fields: ExtractedFieldProposal[] = this.reviewFields().map((field) => ({
      name: field.name.trim(),
      value: field.value.trim() || null,
    }));
    const body: DocumentReview = {
      status,
      fields,
      category_code: status === 'VALIDATED' ? this.reviewCategory.trim() || null : null,
      ai_suggested_category_code: this.extraction()?.suggested_category_code ?? null,
    };
    this.start('review');
    this.api.review(document.id, body).subscribe({
      next: (updated) => {
        this.clearProposal();
        this.finish(updated, status === 'VALIDATED' ? 'Champs validés.' : 'Champs rejetés.');
      },
      error: (e: unknown) => this.fail(e),
    });
  }

  remove(): void {
    const document = this.current();
    if (!document || !confirm(`Supprimer définitivement « ${document.title} » ?`)) return;
    this.start('delete');
    this.api.delete(document.id).subscribe({
      next: () => {
        this.current.set(null);
        this.createMode.set(false);
        this.clearProposal();
        this.busy.set(null);
        this.info.set('Document supprimé.');
        this.refresh();
      },
      error: (e: unknown) => this.fail(e),
    });
  }

  private persist() {
    const title = this.title.trim();
    const rawText = this.rawText.trim();
    if (!title) return throwError(() => new Error('Saisissez un titre pour le document.'));
    if (!rawText) return throwError(() => new Error('Saisissez le texte brut du document.'));

    const document = this.current();
    if (!document) {
      const patientId = this.patientId.trim();
      if (!/^[0-9a-f]{24}$/i.test(patientId)) {
        return throwError(() => new Error("L'ID patient doit contenir 24 caractères hexadécimaux."));
      }
      return this.api.create({ patient_id: patientId, title, raw_text: rawText } satisfies DocumentCreate);
    }
    const changes: DocumentUpdate = {};
    if (title !== document.title) changes.title = title;
    if (rawText !== document.raw_text) changes.raw_text = rawText;
    return Object.keys(changes).length ? this.api.update(document.id, changes) : of(document);
  }

  private refresh(): void {
    if (!this.role()) return;
    this.loading.set(true);
    this.api.list(this.isPatient() ? '' : this.patientFilter).subscribe({
      next: (page) => {
        this.documents.set(page.items);
        this.pageTotal.set(page.total);
        this.loading.set(false);
      },
      error: (e: unknown) => {
        this.loading.set(false);
        this.fail(e);
      },
    });
  }

  private load(document: MedicalDocument): void {
    this.current.set(document);
    this.createMode.set(false);
    this.title = document.title;
    this.patientId = document.patient_id;
    this.rawText = document.raw_text;
    this.clearProposal();
  }

  private start(action: 'save' | 'extract' | 'review' | 'delete'): void {
    this.clearMessages();
    this.busy.set(action);
  }

  private finish(document: MedicalDocument, message: string): void {
    this.load(document);
    this.busy.set(null);
    this.info.set(message);
    this.refresh();
  }

  private clearProposal(): void {
    this.extraction.set(null);
    this.reviewFields.set([]);
    this.reviewCategory = '';
  }

  private clearMessages(): void {
    this.error.set(null);
    this.info.set(null);
  }

  private fail(error: unknown): void {
    this.busy.set(null);
    this.error.set(error instanceof Error ? error.message : apiErrorMessage(error));
  }
}
