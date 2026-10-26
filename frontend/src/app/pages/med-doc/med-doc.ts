import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { jsPDF } from 'jspdf';
import { Subject, catchError, debounceTime, map, of, switchMap, throwError } from 'rxjs';
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
  PatientOption,
} from './med-doc.api';

interface ReviewField {
  name: string;
  value: string;
}

type PatientSearchTarget = 'create' | 'filter';

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
        @if (canCreate()) {
          <button type="button" class="btn primary new-button" (click)="newDocument()">+ Nouveau document</button>
        }
      </div>

      @if (toast(); as notification) {
        <div class="toast" [class.success]="notification.type === 'success'"
          [class.error]="notification.type === 'error'" [class.info]="notification.type === 'info'"
          [attr.role]="notification.type === 'error' ? 'alert' : 'status'" aria-live="polite">
          <span class="toast-indicator" aria-hidden="true"></span>
          <span>{{ notification.message }}</span>
        </div>
      }

      <section class="kpis" aria-label="Statistiques des documents">
        <article class="kpi-card">
          <span class="kpi-icon total"><app-icon name="file-text" [size]="21" /></span>
          <div><small>Total Documents</small><strong>{{ pageTotal() }}</strong></div>
        </article>
        <article class="kpi-card">
          <span class="kpi-icon pending"><app-icon name="activity" [size]="21" /></span>
          <div><small>En attente</small><strong>{{ pendingCount() }}</strong></div>
        </article>
        <article class="kpi-card">
          <span class="kpi-icon validated"><app-icon name="shield" [size]="21" /></span>
          <div><small>Validés</small><strong>{{ validatedCount() }}</strong></div>
        </article>
      </section>

      @if (!isPatient()) {
        <section class="status-chart card" aria-label="Répartition des statuts des documents">
          <div class="card-head">
            <div>
              <h2>Répartition des statuts</h2>
              <p class="muted">Documents chargés dans l’historique</p>
            </div>
          </div>
          <div class="chart-bars">
            @for (item of statusBreakdown(); track item.status) {
              <div class="chart-row">
                <span class="chart-label">{{ item.label }}</span>
                <div
                  class="chart-track"
                  role="progressbar"
                  [attr.aria-label]="item.label"
                  [attr.aria-valuenow]="item.count"
                  [attr.aria-valuemin]="0"
                  [attr.aria-valuemax]="documents().length"
                >
                  <span
                    class="chart-bar"
                    [attr.data-status]="item.status"
                    [style.width.%]="item.percentage"
                  ></span>
                </div>
                <strong class="chart-count">{{ item.count }}</strong>
              </div>
            }
          </div>
        </section>
      }

      <div class="layout">
        <section class="card list-card">
          <div class="card-head">
            <div>
              <h2>{{ isPatient() ? 'Mes documents validés' : 'Historique des documents' }}</h2>
              <p class="muted">
                {{ visibleDocuments().length }}
                @if (visibleDocuments().length !== pageTotal()) { sur {{ pageTotal() }} }
                document(s)
              </p>
            </div>
          </div>
          @if (isPatient()) {
            <div class="history-filters">
              <label class="patient-search">
                <span class="sr-only">Filtrer mes documents par date ou catégorie</span>
                <input
                  type="search"
                  aria-label="Filtrer mes documents par date ou catégorie"
                  [ngModel]="patientDocumentSearch()"
                  (ngModelChange)="patientDocumentSearch.set($event)"
                  placeholder="Rechercher par date ou catégorie (ex. Ordonnance)"
                />
              </label>
              <label class="filter-select">
                <span class="sr-only">Filtrer par catégorie</span>
                <select aria-label="Filtrer par catégorie"
                  [ngModel]="categoryFilter()"
                  (ngModelChange)="categoryFilter.set($event)">
                  <option value="ALL">Toutes catégories</option>
                  @for (category of categoryOptions(); track category) {
                    <option [value]="category">{{ categoryLabel(category) }}</option>
                  }
                </select>
              </label>
            </div>
          } @else {
            <div class="history-filters">
              <form class="filter" (ngSubmit)="applyFilter()">
                <label class="patient-search">
                  <span class="sr-only">Rechercher un patient ou un dossier</span>
                  <input name="patientFilter" [(ngModel)]="filterPatientQuery"
                    (ngModelChange)="searchPatients($event, 'filter')"
                    placeholder="Rechercher un patient ou un dossier..." autocomplete="off" />
                  @if (filterPatientResults().length) {
                    <div class="suggestions" role="listbox">
                      @for (patient of filterPatientResults(); track patient.id) {
                        <button type="button" role="option" (click)="selectPatient(patient, 'filter')">
                          {{ patient.lastName }} {{ patient.firstName }} - {{ patient.recordNumber }}
                        </button>
                      }
                    </div>
                  }
                </label>
                @if (filterPatient()) {
                  <button type="button" class="btn" (click)="clearFilter()">Tous</button>
                }
              </form>
              <label class="filter-select">
                <span class="sr-only">Filtrer par statut</span>
                <select aria-label="Filtrer par statut"
                  [ngModel]="statusFilter()"
                  (ngModelChange)="statusFilter.set($event)">
                  <option value="ALL">Tous les statuts</option>
                  @for (status of statusOptions; track status) {
                    <option [value]="status">{{ statusLabel(status) }}</option>
                  }
                </select>
              </label>
              <label class="filter-select">
                <span class="sr-only">Filtrer par catégorie</span>
                <select aria-label="Filtrer par catégorie"
                  [ngModel]="categoryFilter()"
                  (ngModelChange)="categoryFilter.set($event)">
                  <option value="ALL">Toutes catégories</option>
                  @for (category of categoryOptions(); track category) {
                    <option [value]="category">{{ categoryLabel(category) }}</option>
                  }
                </select>
              </label>
            </div>
          }

          @if (loading()) {
            <p class="empty">Chargement des documents…</p>
          } @else if (!documents().length) {
            <p class="empty">Aucun document à afficher.</p>
          } @else if (!visibleDocuments().length) {
            <p class="empty">Aucun document ne correspond à votre recherche.</p>
          } @else {
            <div class="document-list">
              @for (document of visibleDocuments(); track document.id) {
                <article class="document-card" [class.selected]="current()?.id === document.id">
                  <button type="button" class="document-open" (click)="open(document.id)">
                    <span class="document-icon"><app-icon name="file-text" [size]="20" /></span>
                    <span class="document-content">
                      <strong class="document-title">{{ document.title }}</strong>
                      @if (!isPatient()) {
                        <small>{{ patientLabel(document.patient_id) }}</small>
                      }
                      <span class="document-badges">
                        <span class="category-badge" [attr.data-kind]="categoryKind(document.category_code ?? document.ai_suggested_category_code)">
                          {{ categoryLabel(document.category_code ?? document.ai_suggested_category_code) }}
                        </span>
                        <span class="status" [attr.data-status]="document.status">{{ statusLabel(document.status) }}</span>
                      </span>
                    </span>
                    <span class="document-date">{{ document.created_at | date:'dd/MM/yyyy' }}</span>
                  </button>
                  @if (!isPatient()) {
                    <div class="document-actions" aria-label="Actions du document">
                      <button type="button" class="icon-action" title="Télécharger le PDF"
                        aria-label="Télécharger le PDF" (click)="downloadDocument(document)">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                          stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <path d="m7 10 5 5 5-5M12 15V3" />
                        </svg>
                      </button>
                      @if (canUpdateDocument(document)) {
                        <button type="button" class="icon-action" title="Modifier le document"
                          aria-label="Modifier le document" (click)="editDocument(document)">
                          <app-icon name="edit" [size]="16" />
                        </button>
                      }
                      @if (canArchiveDocument(document)) {
                        <button type="button" class="icon-action danger" title="Archiver le document"
                          aria-label="Archiver le document" (click)="archiveDocument(document)">
                          <app-icon name="trash" [size]="16" />
                        </button>
                      }
                      @if (canDeleteDocument(document)) {
                        <button type="button" class="icon-action danger" title="Supprimer définitivement le document"
                          aria-label="Supprimer définitivement le document" (click)="deleteDocument(document)">
                          <app-icon name="trash" [size]="16" />
                        </button>
                      }
                    </div>
                  }
                </article>
              }
            </div>
          }
        </section>

        <section class="card detail-card">
          @if (createMode()) {
            <div class="card-head">
              <div><h2>Nouveau document</h2><p class="muted">Associez le document à un dossier patient.</p></div>
            </div>
            <div class="field patient-search">
              <label for="createPatientInput">Patient</label>
              <input id="createPatientInput" name="createPatient" [(ngModel)]="createPatientQuery"
                (ngModelChange)="searchPatients($event, 'create')"
                placeholder="Nom, prénom ou n° dossier" autocomplete="off" />
              @if (createPatientResults().length) {
                <div class="suggestions" role="listbox">
                  @for (patient of createPatientResults(); track patient.id) {
                    <button type="button" role="option" (click)="selectPatient(patient, 'create')">
                      {{ patient.lastName }} {{ patient.firstName }} - {{ patient.recordNumber }}
                    </button>
                  }
                </div>
              }
              @if (createPatient(); as patient) {
                <small class="selected-patient">Sélectionné : {{ patient.lastName }} {{ patient.firstName }} - {{ patient.recordNumber }}</small>
              }
            </div>
            <label class="field"><span>Titre</span>
              <input [ngModel]="title" (ngModelChange)="updateCreateTitle($event)" maxlength="200" />
            </label>
            <label class="field"><span>Texte source</span>
              <textarea [ngModel]="rawText" (ngModelChange)="updateCreateRawText($event)" rows="10"></textarea>
            </label>
            <div class="actions">
              <button type="button" class="btn primary"
                [disabled]="busy() !== null || !isCreateFormValid()" (click)="save()">
                {{ busy() === 'save' ? 'Enregistrement…' : 'Créer le document' }}
              </button>
            </div>
          } @else if (current(); as document) {
            <div class="card-head">
              <div>
                <div class="detail-title">
                  <h2>{{ document.title }}</h2>
                  @if (isPatient()) {
                    <button
                      type="button"
                      class="icon-action"
                      title="Télécharger le PDF (non signé électroniquement)"
                      aria-label="Télécharger le PDF (non signé électroniquement)"
                      (click)="downloadCurrentDocument(document)"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                        stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <path d="m7 10 5 5 5-5M12 15V3" />
                      </svg>
                    </button>
                  }
                </div>
                <p class="muted">{{ document.created_at | date:'dd/MM/yyyy HH:mm' }} · {{ patientLabel(document.patient_id) }}</p>
              </div>
              <span class="status" [attr.data-status]="document.status">{{ statusLabel(document.status) }}</span>
              <div class="actions">
                @if (canUpdate() && !editMode()) {
                  <button type="button" class="btn" (click)="beginEdit()">Modifier</button>
                }
                @if (canArchive()) {
                  <button type="button" class="btn danger" [disabled]="busy() !== null" (click)="remove()">Archiver</button>
                }
                @if (canDelete()) {
                  <button type="button" class="btn danger" [disabled]="busy() !== null" (click)="remove()">Supprimer</button>
                }
                @if (canExtract()) {
                  <button type="button" class="btn primary" [disabled]="busy() !== null" (click)="extract()">
                    {{ busy() === 'extract' ? 'Analyse…' : 'Extraire avec l’IA' }}
                  </button>
                }
              </div>
            </div>
            <div class="split-screen">
              <section class="source-panel">
                <h3 class="panel-heading">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                    stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <path d="M14 2v6h6M8 13h8M8 17h8" />
                  </svg>
                  Document source
                </h3>
                @if (editMode()) {
                  <label class="field"><span>Titre</span><input [(ngModel)]="title" maxlength="200" /></label>
                  <textarea [(ngModel)]="rawText" rows="18" aria-label="Modifier le texte source"></textarea>
                  <div class="actions">
                    <button type="button" class="btn primary" [disabled]="busy() !== null" (click)="save()">Enregistrer</button>
                    <button type="button" class="btn" (click)="cancelEdit()">Annuler</button>
                  </div>
                } @else {
                  <pre>{{ document.raw_text }}</pre>
                }
              </section>
              <section class="review-panel">
                <h3 class="panel-heading">
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                    stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <path d="M14 2v6h6M8 13h8M8 17h8" />
                  </svg>
                  Champs extraits par l’IA
                </h3>
                @if (busy() === 'extract') {
                  <div class="skeleton" role="status" aria-label="Analyse IA en cours">
                    <span></span><span></span><span></span><span></span>
                    <small>Analyse du document…</small>
                  </div>
                } @else if (extraction(); as proposal) {
                  @if (proposal.warnings.length) {
                    <ul class="warnings">@for (warning of proposal.warnings; track $index) { <li>{{ warning }}</li> }</ul>
                  }
                  <label class="field"><span>Catégorie</span><input [(ngModel)]="reviewCategory" /></label>
                  @for (field of reviewFields(); track $index) {
                    <div class="proposal-row">
                      <label class="field"><span>Champ</span><input [ngModel]="field.name" (ngModelChange)="updateField($index, 'name', $event)" /></label>
                      <label class="field"><span>Valeur</span><input [ngModel]="field.value" (ngModelChange)="updateField($index, 'value', $event)" /></label>
                      <button type="button" class="btn danger" (click)="removeField($index)">Retirer</button>
                    </div>
                  }
                  @if (canReview()) {
                    <div class="actions review-actions">
                      <button type="button" class="btn" (click)="previewCurrentDocument(document)">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
                          stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                          <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                        Aperçu PDF
                      </button>
                      <button type="button" class="btn success" [disabled]="busy() !== null || !reviewFields().length" (click)="review('VALIDATED')">Valider</button>
                      <button type="button" class="btn danger" [disabled]="busy() !== null || !reviewFields().length" (click)="review('REJECTED')">Rejeter</button>
                    </div>
                  } @else {
                    <p class="hint">La validation est réservée aux médecins et administrateurs.</p>
                  }
                } @else {
                  @if (document.extracted_fields.length) {
                    @for (field of document.extracted_fields; track $index) {
                      <div class="extracted-row" [attr.data-status]="field.status">
                        <strong>{{ field.name }}</strong><span>{{ field.value ?? 'Non trouvé' }}</span>
                        <span class="status" [attr.data-status]="field.status">{{ statusLabel(field.status) }}</span>
                      </div>
                    }
                  } @else {
                    <p class="empty">Aucune extraction disponible. Lancez l’analyse IA pour proposer des champs.</p>
                  }
                }
              </section>
            </div>
          } @else {
            <div class="empty-selection">
              <span class="empty-selection-icon"><app-icon name="file-text" [size]="34" /></span>
              <h2>Aucun document sélectionné</h2>
              <p>Sélectionnez un document dans l’historique pour consulter son contenu.</p>
              @if (canCreate()) {
                <button type="button" class="btn primary" (click)="newDocument()">
                  <app-icon name="plus" [size]="16" /> Créer un document
                </button>
              }
            </div>
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
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly patientSearch = new Subject<{ query: string; target: PatientSearchTarget }>();

  readonly role = computed(() => this.auth.user()?.role ?? null);
  readonly isPatient = computed(() => this.role() === 'PATIENT');
  readonly pendingCount = computed(() =>
    this.documents().filter((document) => document.status === 'DRAFT').length,
  );
  readonly validatedCount = computed(() =>
    this.documents().filter((document) => document.status === 'VALIDATED').length,
  );
  readonly statusBreakdown = computed(() => {
    const counts = {
      DRAFT: this.documents().filter((document) => document.status === 'DRAFT').length,
      VALIDATED: this.documents().filter((document) => document.status === 'VALIDATED').length,
      REJECTED: this.documents().filter((document) => document.status === 'REJECTED').length,
      ARCHIVED: this.documents().filter((document) => document.status === 'ARCHIVED').length,
    };
    const maximum = Math.max(1, ...Object.values(counts));
    return [
      { status: 'DRAFT', label: 'Brouillon', count: counts.DRAFT },
      { status: 'VALIDATED', label: 'Validés', count: counts.VALIDATED },
      { status: 'REJECTED', label: 'Rejetés', count: counts.REJECTED },
      { status: 'ARCHIVED', label: 'Archivés', count: counts.ARCHIVED },
    ].map((item) => ({ ...item, percentage: (item.count / maximum) * 100 }));
  });
  readonly canCreate = computed(() =>
    ['DOCTOR', 'SECRETARY', 'ADMIN_STAFF', 'ADMIN'].includes(this.role() ?? ''),
  );
  readonly canUpdate = computed(
    () =>
      ['DOCTOR', 'ADMIN_STAFF', 'ADMIN'].includes(this.role() ?? '') &&
      !this.current()?.archived_at,
  );
  readonly canEditForm = computed(() =>
    this.createMode() ? this.canCreate() : this.canUpdate(),
  );
  readonly canExtract = computed(
    () =>
      ['DOCTOR', 'ADMIN_STAFF', 'ADMIN'].includes(this.role() ?? '') &&
      !this.current()?.archived_at,
  );
  readonly canArchive = computed(
    () => this.role() === 'DOCTOR' && !this.current()?.archived_at,
  );
  readonly canDelete = computed(
    () => this.role() === 'ADMIN',
  );
  readonly canReview = computed(() => ['DOCTOR', 'ADMIN'].includes(this.role() ?? ''));

  canUpdateDocument(document: DocumentListItem): boolean {
    return ['DOCTOR', 'ADMIN_STAFF', 'ADMIN'].includes(this.role() ?? '') &&
      document.status !== 'ARCHIVED';
  }

  canArchiveDocument(document: DocumentListItem): boolean {
    return this.role() === 'DOCTOR' && document.status !== 'ARCHIVED';
  }

  canDeleteDocument(document: DocumentListItem): boolean {
    return this.role() === 'ADMIN';
  }

  readonly documents = signal<DocumentListItem[]>([]);
  readonly patientDocumentSearch = signal('');
  readonly statusFilter = signal<'ALL' | DocumentStatus>('ALL');
  readonly categoryFilter = signal('ALL');
  readonly statusOptions: DocumentStatus[] = ['DRAFT', 'VALIDATED', 'REJECTED', 'ARCHIVED'];
  readonly categoryOptions = computed(() => [
    ...new Set([
      'MEDICAL',
      'ORDONNANCE',
      'CERTIFICAT',
      'FINANCIER',
      'CNAM',
      'ADMINISTRATIF',
      ...this.documents()
        .map((document) => document.category_code ?? document.ai_suggested_category_code)
        .filter((category): category is string => category !== null),
    ]),
  ]);
  readonly visibleDocuments = computed(() => {
    const query = this.patientDocumentSearch().trim().toLocaleLowerCase();
    const statusFilter = this.statusFilter();
    const categoryFilter = this.categoryFilter();
    const documents = this.documents();

    return documents.filter((document) => {
      const category = document.category_code ?? document.ai_suggested_category_code ?? '';
      const date = new Date(document.created_at);
      const searchableValues = [
        category,
        this.categoryLabel(category),
        date.toISOString(),
        date.toLocaleDateString('fr-FR'),
        document.created_at,
      ];
      const matchesQuery =
        !this.isPatient() ||
        !query ||
        searchableValues.some((value) => value.toLocaleLowerCase().includes(query));
      const matchesStatus = statusFilter === 'ALL' || document.status === statusFilter;
      const matchesCategory = categoryFilter === 'ALL' || category === categoryFilter;
      return matchesQuery && matchesStatus && matchesCategory;
    });
  });
  readonly pageTotal = signal(0);
  readonly current = signal<MedicalDocument | null>(null);
  readonly extraction = signal<DocumentExtraction | null>(null);
  readonly reviewFields = signal<ReviewField[]>([]);
  readonly createPatient = signal<PatientOption | null>(null);
  readonly filterPatient = signal<PatientOption | null>(null);
  readonly createPatientResults = signal<PatientOption[]>([]);
  readonly filterPatientResults = signal<PatientOption[]>([]);
  readonly patientNames = signal<Record<string, string>>({});
  readonly editMode = signal(false);
  readonly loading = signal(false);
  readonly busy = signal<'save' | 'extract' | 'review' | 'delete' | null>(null);
  readonly toast = signal<{ message: string; type: 'success' | 'error' | 'info' } | null>(null);
  readonly createMode = signal(false);
  private readonly createFormRevision = signal(0);
  private toastTimeout: ReturnType<typeof setTimeout> | null = null;

  patientFilter = '';
  createPatientQuery = '';
  filterPatientQuery = '';
  title = '';
  rawText = '';
  reviewCategory = '';

  constructor() {
    this.destroyRef.onDestroy(() => {
      if (this.toastTimeout) clearTimeout(this.toastTimeout);
    });
    this.patientFilter = this.route.snapshot.queryParamMap.get('patient_id') ?? '';
    this.patientSearch
      .pipe(
        debounceTime(250),
        switchMap(({ query, target }) => {
          if (query.trim().length < 2) return of({ target, items: [] as PatientOption[] });
          return this.api.patientOptions(query).pipe(
            map((items) => ({ target, items })),
            catchError((error: unknown) => {
              this.fail(error);
              return of({ target, items: [] as PatientOption[] });
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe(({ target, items }) => {
        if (target === 'create') {
          this.createPatientResults.set(items);
          const query = this.normalizePatientLabel(this.createPatientQuery);
          const exactMatch = items.find(
            (patient) => this.normalizePatientLabel(this.formatPatient(patient)) === query,
          );
          if (exactMatch) this.selectPatient(exactMatch, 'create');
        } else {
          this.filterPatientResults.set(items);
        }
      });
    if (!this.auth.user()) {
      this.auth.loadProfile().subscribe({
        next: () => {
          this.loadInitialPatient();
          this.refresh();
        },
        error: (e: unknown) => this.fail(e),
      });
    } else {
      this.loadInitialPatient();
      this.refresh();
    }
  }

  statusLabel(status: DocumentStatus): string {
    return {
      DRAFT: 'Brouillon',
      VALIDATED: 'Validé',
      REJECTED: 'Rejeté',
      ARCHIVED: 'Archivé',
    }[status];
  }

  isCreateFormValid(): boolean {
    this.createFormRevision();
    return this.createPatient() !== null && !!this.title.trim() && !!this.rawText.trim();
  }

  updateCreateTitle(value: string): void {
    this.title = value;
    this.createFormRevision.update((revision) => revision + 1);
  }

  updateCreateRawText(value: string): void {
    this.rawText = value;
    this.createFormRevision.update((revision) => revision + 1);
  }

  newDocument(): void {
    this.current.set(null);
    this.createMode.set(true);
    this.title = '';
    this.createPatient.set(this.filterPatient());
    this.createPatientQuery = this.formatPatient(this.createPatient());
    this.rawText = '';
    this.editMode.set(false);
    this.clearProposal();
  }

  applyFilter(): void {
    this.patientFilter = this.filterPatient()?.id ?? '';
    this.refresh();
  }

  clearFilter(): void {
    this.filterPatient.set(null);
    this.filterPatientQuery = '';
    this.patientFilter = '';
    this.filterPatientResults.set([]);
    this.refresh();
  }

  searchPatients(query: string, target: PatientSearchTarget): void {
    if (target === 'create') {
      const selectedPatient = this.createPatient();
      if (selectedPatient && query === this.formatPatient(selectedPatient)) return;
      this.createPatient.set(null);
      this.createPatientResults.set([]);
    } else {
      this.filterPatient.set(null);
      this.patientFilter = '';
      this.filterPatientResults.set([]);
    }
    this.patientSearch.next({ query, target });
  }

  selectPatient(patient: PatientOption, target: PatientSearchTarget): void {
    if (target === 'create') {
      this.createPatient.set(patient);
      this.createPatientQuery = this.formatPatient(patient);
      this.createPatientResults.set([]);
    } else {
      this.filterPatient.set(patient);
      this.filterPatientQuery = this.formatPatient(patient);
      this.patientFilter = patient.id;
      this.filterPatientResults.set([]);
      this.refresh();
    }
  }

  patientLabel(patientId: string): string {
    const patient = this.filterPatient();
    return patient?.id === patientId
      ? this.formatPatient(patient)
      : this.patientNames()[patientId] ?? 'Dossier patient';
  }

  categoryLabel(category: string | null): string {
    if (!category) return 'Non catégorisé';
    return category
      .toLowerCase()
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }

  categoryKind(category: string | null): 'medical' | 'administrative' | 'other' {
    const normalized = category?.toUpperCase() ?? '';
    if (/MED|LAB|RADIO|IMAG|ORDON|PRESCRIPT|CONSULT|VACCIN|ANALY/.test(normalized)) {
      return 'medical';
    }
    if (/ADMIN|INSUR|IDENT|FORM|BILL|FACT|ATTEST/.test(normalized)) {
      return 'administrative';
    }
    return 'other';
  }

  downloadDocument(document: DocumentListItem): void {
    this.api.get(document.id).subscribe({
      next: (fullDocument) => {
        this.downloadDocumentPdf(fullDocument);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  downloadCurrentDocument(document: MedicalDocument): void {
    if (!this.isPatient() || document.status !== 'VALIDATED') return;
    this.downloadDocumentPdf(document);
  }

  previewCurrentDocument(document: MedicalDocument): void {
    if (!this.canReview()) return;
    this.downloadDocumentPdf(document, true);
  }

  editDocument(document: DocumentListItem): void {
    this.api.get(document.id).subscribe({
      next: (fullDocument) => {
        this.load(fullDocument);
        this.beginEdit();
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  archiveDocument(document: DocumentListItem): void {
    if (!this.canArchive() || !confirm(`Archiver « ${document.title} » ?`)) return;
    this.start('delete');
    this.api.delete(document.id).subscribe({
      next: () => {
        if (this.current()?.id === document.id) {
          this.current.set(null);
          this.clearProposal();
        }
        this.busy.set(null);
        this.showToast('Document archivé.', 'success');
        this.refresh();
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  deleteDocument(document: DocumentListItem): void {
    if (!this.canDeleteDocument(document) ||
        !confirm(`Supprimer définitivement « ${document.title} » ? Cette action est irréversible.`)) return;
    this.start('delete');
    this.api.delete(document.id).subscribe({
      next: () => {
        if (this.current()?.id === document.id) {
          this.current.set(null);
          this.clearProposal();
        }
        this.busy.set(null);
        this.showToast('Document supprimé définitivement.', 'success');
        this.refresh();
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  beginEdit(): void {
    const document = this.current();
    if (!document || !this.canUpdate()) return;
    this.title = document.title;
    this.rawText = document.raw_text;
    this.editMode.set(true);
    this.clearProposal();
  }

  cancelEdit(): void {
    const document = this.current();
    if (document) {
      this.title = document.title;
      this.rawText = document.raw_text;
    }
    this.editMode.set(false);
  }

  open(id: string): void {
    this.api.get(id).subscribe({
      next: (document) => this.load(document),
      error: (e: unknown) => this.fail(e),
    });
  }

  save(): void {
    const creating = !this.current();
    this.start('save');
    this.persist().subscribe({
      next: (document) =>
        this.finish(
          document,
          creating ? 'Document créé avec succès' : 'Document enregistré.',
        ),
      error: (e: unknown) => this.fail(e),
    });
  }

  extract(): void {
    if (!this.canExtract()) return;
    const creating = !this.current();
    this.start('extract');
    this.persist()
      .pipe(
        switchMap((document) => {
          if (creating) this.showToast('Document créé avec succès', 'success');
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
          this.showToast('Extraction terminée. Vérifiez les champs.', 'info');
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
    if (!document || !this.canReview()) return;
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
    if (document && this.canDelete()) {
      this.deleteDocument(document);
      return;
    }
    if (!document || !this.canArchive() || !confirm(`Archiver « ${document.title} » ?`)) return;
    this.start('delete');
    this.api.delete(document.id).subscribe({
      next: () => {
        this.current.set(null);
        this.createMode.set(false);
        this.clearProposal();
        this.busy.set(null);
        this.showToast('Document archivé.', 'success');
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
      const patientId = this.createPatient()?.id;
      if (!patientId) return throwError(() => new Error('Sélectionnez un patient dans les résultats.'));
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
    const patientId = this.patientFilter.trim();
    const request =
      patientId && !this.isPatient()
        ? this.api.history(patientId)
        : this.api.list(this.isPatient() ? '' : patientId);
    request.subscribe({
      next: (page) => {
        this.documents.set(page.items);
        this.pageTotal.set(page.total);
        this.loading.set(false);
        if (!this.isPatient()) this.loadPatientNames(page.items);
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
    this.editMode.set(false);
    this.title = document.title;
    this.rawText = document.raw_text;
    this.clearProposal();
  }

  private start(action: 'save' | 'extract' | 'review' | 'delete'): void {
    this.busy.set(action);
  }

  private finish(document: MedicalDocument, message: string): void {
    this.load(document);
    this.busy.set(null);
    this.showToast(message, 'success');
    this.refresh();
  }

  private clearProposal(): void {
    this.extraction.set(null);
    this.reviewFields.set([]);
    this.reviewCategory = '';
  }

  private fail(error: unknown): void {
    this.busy.set(null);
    this.showToast(this.errorMessage(error), 'error');
  }

  private showToast(message: string, type: 'success' | 'error' | 'info'): void {
    if (this.toastTimeout) clearTimeout(this.toastTimeout);
    this.toast.set({ message, type });
    this.toastTimeout = setTimeout(() => {
      this.toast.set(null);
      this.toastTimeout = null;
    }, 3000);
  }

  private errorMessage(error: unknown): string {
    if (!(error instanceof HttpErrorResponse)) {
      return error instanceof Error ? error.message : apiErrorMessage(error);
    }
    const body: unknown = error.error;
    if (typeof body === 'string' && body.trim()) return body.trim();
    if (body && typeof body === 'object') {
      for (const key of ['detail', 'message', 'error']) {
        const value = (body as Record<string, unknown>)[key];
        if (typeof value === 'string' && value.trim()) return value.trim();
        if (value && typeof value === 'object' && 'message' in value) {
          const message = value.message;
          if (typeof message === 'string' && message.trim()) return message.trim();
        }
        if (Array.isArray(value)) {
          const messages = value
            .map((item: unknown) => {
              if (!item || typeof item !== 'object' || !('msg' in item)) return null;
              const detail = item.msg;
              return typeof detail === 'string' ? detail : null;
            })
            .filter((message): message is string => message !== null);
          if (messages.length) return messages.join(' · ');
        }
      }
    }
    return apiErrorMessage(error);
  }

  private loadInitialPatient(): void {
    const patientId = this.patientFilter.trim();
    if (!patientId || this.isPatient()) return;
    this.api.patientOptions('', patientId).subscribe({
      next: ([patient]) => {
        if (!patient) return;
        this.filterPatient.set(patient);
        this.filterPatientQuery = this.formatPatient(patient);
        this.createPatient.set(patient);
        this.createPatientQuery = this.formatPatient(patient);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  private formatPatient(patient: PatientOption | null): string {
    return patient ? `${patient.lastName} ${patient.firstName} - ${patient.recordNumber}` : '';
  }

  private downloadDocumentPdf(document: MedicalDocument, preview = false): void {
    const pdf = new jsPDF({ format: 'a4', unit: 'mm' });
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const margin = 18;
    const contentWidth = pageWidth - margin * 2;
    const safeTitle = document.title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').trim();
    const outputPdf = (filename: string): void => {
      if (preview) {
        if (!window.open(pdf.output('bloburl'), '_blank')) {
          this.showToast('Autorisez les fenêtres contextuelles pour afficher l’aperçu PDF.', 'error');
        }
        return;
      }
      pdf.save(filename);
    };

    if (
      (document.category_code ?? document.ai_suggested_category_code)?.toUpperCase() ===
      'FINANCIER'
    ) {
      const fields = document.extracted_fields;
      const normalizedFieldName = (name: string): string =>
        name
          .toLocaleLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '');
      const fieldValue = (pattern: RegExp): string | null =>
        fields.find((field) => pattern.test(normalizedFieldName(field.name)))?.value?.trim() ||
        null;
      const selectedPatient =
        [this.filterPatient(), this.createPatient()].find(
          (patient) => patient?.id === document.patient_id,
        ) ?? null;
      const cachedPatientLabel =
        this.patientNames()[document.patient_id]?.split(' - ')[0] ?? null;
      const lastName =
        fieldValue(/^(nom|nom du patient|nom de famille|last name|surname)$/) ??
        fieldValue(/^(nom complet|nom et prenom|patient name|full name)$/) ??
        selectedPatient?.lastName ??
        cachedPatientLabel;
      const firstName =
        fieldValue(/^(prenom|prenom du patient|first name|given name)$/) ??
        selectedPatient?.firstName;
      const designation =
        fieldValue(/^(designation|prestation|acte|service|description)$/) ??
        'Consultation médicale';
      const quantityValue = fieldValue(/^(quantite|quantity|qte)$/);
      const unitPriceValue = fieldValue(/^(prix unitaire|unit price|montant ht|prix)$/);
      const toAmount = (value: string | null, fallback: number): number => {
        if (!value) return fallback;
        let normalized = value.replace(/\s/g, '').replace(/[^\d,.-]/g, '');
        if (normalized.includes(',') && normalized.includes('.')) {
          normalized =
            normalized.lastIndexOf(',') > normalized.lastIndexOf('.')
              ? normalized.replace(/\./g, '').replace(',', '.')
              : normalized.replace(/,/g, '');
        } else {
          normalized = normalized.replace(',', '.');
        }
        const amount = Number(normalized);
        return Number.isFinite(amount) && amount >= 0 ? amount : fallback;
      };
      const quantity = toAmount(quantityValue, 1);
      const unitPrice = toAmount(unitPriceValue, 80);
      const totalHt = quantity * unitPrice;
      const vat = totalHt * 0.19;
      const fiscalStamp = 1;
      const netToPay = totalHt + vat + fiscalStamp;
      const formatAmount = (amount: number): string =>
        `${amount.toFixed(3)} DT`;
      const invoiceDate = new Date(document.created_at).toLocaleDateString('fr-FR');
      const columns = [margin, margin + 94, margin + 119, margin + 149, pageWidth - margin];

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(16);
      pdf.text('MediFlow AI - Clinique', margin, 20);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text('Adresse fictive : 10, avenue des Jasmins, Tunis', margin, 27);
      pdf.text('Matricule fiscal fictif : 0000000/X/X/000', margin, 32);
      pdf.setDrawColor(100);
      pdf.line(margin, 38, pageWidth - margin, 38);

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(15);
      pdf.text('FACTURE', pageWidth / 2, 50, { align: 'center' });

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(10);
      pdf.text(`Nom : ${lastName || 'Non renseigné'}`, margin, 64);
      pdf.text(`Prénom : ${firstName || 'Non renseigné'}`, margin, 70);
      pdf.text(`Date : ${invoiceDate}`, pageWidth - margin, 70, { align: 'right' });

      const tableY = 82;
      const headerHeight = 12;
      const rowHeight = 18;
      pdf.setFillColor(238, 242, 245);
      pdf.rect(margin, tableY, contentWidth, headerHeight, 'F');
      pdf.setDrawColor(130);
      pdf.rect(margin, tableY, contentWidth, headerHeight + rowHeight);
      for (const x of columns.slice(1, -1)) {
        pdf.line(x, tableY, x, tableY + headerHeight + rowHeight);
      }
      pdf.line(margin, tableY + headerHeight, pageWidth - margin, tableY + headerHeight);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(9);
      pdf.text('Désignation', margin + 3, tableY + 8);
      pdf.text('Quantité', (columns[1] + columns[2]) / 2, tableY + 8, { align: 'center' });
      pdf.text('Prix unitaire', (columns[2] + columns[3]) / 2, tableY + 8, { align: 'center' });
      pdf.text('Total', (columns[3] + columns[4]) / 2, tableY + 8, { align: 'center' });
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text(pdf.splitTextToSize(designation, columns[1] - margin - 6), margin + 3, tableY + 19);
      pdf.text(quantity.toFixed(2), (columns[1] + columns[2]) / 2, tableY + 19, {
        align: 'center',
      });
      pdf.text(formatAmount(unitPrice), (columns[2] + columns[3]) / 2, tableY + 19, {
        align: 'center',
      });
      pdf.text(formatAmount(totalHt), (columns[3] + columns[4]) / 2, tableY + 19, {
        align: 'center',
      });

      const totalsX = margin + contentWidth * 0.52;
      const totalsLabelX = totalsX + 4;
      const totalsValueX = pageWidth - margin - 4;
      let totalsY = tableY + headerHeight + rowHeight + 14;
      const writeTotal = (label: string, amount: number, bold = false): void => {
        pdf.setFont('helvetica', bold ? 'bold' : 'normal');
        pdf.setFontSize(bold ? 11 : 10);
        pdf.text(label, totalsLabelX, totalsY);
        pdf.text(formatAmount(amount), totalsValueX, totalsY, { align: 'right' });
        totalsY += 8;
      };
      pdf.setDrawColor(160);
      pdf.rect(totalsX, totalsY - 6, pageWidth - margin - totalsX, 39);
      writeTotal('Total HT', totalHt);
      writeTotal('TVA (19%)', vat);
      writeTotal('Timbre fiscal', fiscalStamp);
      writeTotal('Net à payer', netToPay, true);

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(8);
      pdf.text('Tarif indicatif fictif - Maquette non valable comme facture fiscale.', margin, pageHeight - 16);
      pdf.text('Document non signé électroniquement', margin, pageHeight - 8);
      pdf.text('Espace réservé au cachet', pageWidth - margin, pageHeight - 8, {
        align: 'right',
      });

      outputPdf(`${safeTitle || 'facture'}.pdf`);
      return;
    }

    if (
      (document.category_code ?? document.ai_suggested_category_code)?.toUpperCase() ===
      'CERTIFICAT'
    ) {
      const fields = document.extracted_fields;
      const normalizedFieldName = (name: string): string =>
        name
          .toLocaleLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '');
      const fieldValue = (pattern: RegExp): string | null =>
        fields.find((field) => pattern.test(normalizedFieldName(field.name)))?.value?.trim() ||
        null;
      const selectedPatient =
        [this.filterPatient(), this.createPatient()].find(
          (patient) => patient?.id === document.patient_id,
        ) ?? null;
      const cachedPatientLabel =
        this.patientNames()[document.patient_id]?.split(' - ')[0] ?? null;
      const extractedPatientName =
        [
          fieldValue(/^(nom|nom du patient|nom de famille|last name|surname)$/),
          fieldValue(/^(prenom|prenom du patient|first name|given name)$/),
        ]
          .filter(Boolean)
          .join(' ');
      const patientName =
        fieldValue(/^(nom complet|nom du patient|patient name|full name)$/) ??
        (extractedPatientName ||
          [selectedPatient?.lastName, selectedPatient?.firstName].filter(Boolean).join(' ') ||
          cachedPatientLabel ||
          'Non renseigné');
      const certificateDate = new Date(document.created_at).toLocaleDateString('fr-FR');

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text('République Tunisienne', pageWidth / 2, 13, { align: 'center' });
      pdf.text('Ministère de la Santé', pageWidth / 2, 18, { align: 'center' });
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(13);
      pdf.text('Dr. Hela Benali', pageWidth / 2, 29, { align: 'center' });
      pdf.setDrawColor(100);
      pdf.line(margin, 36, pageWidth - margin, 36);

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(16);
      pdf.text('CERTIFICAT MÉDICAL', pageWidth / 2, 52, { align: 'center' });

      let y = 72;
      const bodyBottom = pageHeight - 82;
      const addCertificatePage = (): void => {
        pdf.addPage();
        y = margin + 10;
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(11);
        pdf.text('CERTIFICAT MÉDICAL (suite)', pageWidth / 2, y, { align: 'center' });
        y += 12;
      };
      const writeCertificateParagraph = (text: string): void => {
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(12);
        const lines = pdf.splitTextToSize(text, contentWidth) as string[];
        for (const line of lines) {
          if (y + 6 > bodyBottom) addCertificatePage();
          pdf.text(line, margin, y);
          y += 6;
        }
        y += 3;
      };

      writeCertificateParagraph(
        `Je soussigné, Dr. Hela Benali, certifie avoir examiné ${patientName}.`,
      );
      if (document.raw_text.trim()) {
        writeCertificateParagraph(document.raw_text.trim());
      } else {
        writeCertificateParagraph('Motif et observations : non renseignés.');
      }

      if (y + 22 > bodyBottom) addCertificatePage();
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(11);
      pdf.text('Certificat établi pour faire valoir ce que de droit.', margin, y);
      y += 9;
      pdf.text(`Fait à Tunis, le ${certificateDate}`, margin, y);

      const signatureY = pageHeight - 58;
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.text('Signature du médecin', margin, signatureY + 4);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text('Dr. Hela Benali', margin, signatureY + 11);
      pdf.setDrawColor(100);
      pdf.line(margin, signatureY + 28, margin + 62, signatureY + 28);
      pdf.setFontSize(8);
      pdf.text('Signature à apposer', margin, signatureY + 33);
      const stampWidth = 54;
      const stampHeight = 34;
      const stampX = pageWidth - margin - stampWidth;
      pdf.rect(stampX, signatureY, stampWidth, stampHeight);
      pdf.text('Espace réservé au cachet', stampX + stampWidth / 2, signatureY + 19, {
        align: 'center',
      });

      const pageCount = pdf.getNumberOfPages();
      for (let page = 1; page <= pageCount; page += 1) {
        pdf.setPage(page);
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(8);
        pdf.text('Document non signé électroniquement', margin, pageHeight - 8);
        pdf.text(`${page}/${pageCount}`, pageWidth - margin, pageHeight - 8, {
          align: 'right',
        });
      }

      outputPdf(`${safeTitle || 'document'}.pdf`);
      return;
    }

    if (
      (document.category_code ?? document.ai_suggested_category_code)?.toUpperCase() ===
      'ORDONNANCE'
    ) {
      const fields = document.extracted_fields;
      const normalizedFieldName = (name: string): string =>
        name
          .toLocaleLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '');
      const fieldValue = (pattern: RegExp): string | null =>
        fields.find((field) => pattern.test(normalizedFieldName(field.name)))?.value?.trim() ||
        null;
      const selectedPatient =
        [this.filterPatient(), this.createPatient()].find(
          (patient) => patient?.id === document.patient_id,
        ) ?? null;
      const cachedPatientLabel =
        this.patientNames()[document.patient_id]?.split(' - ')[0] ?? null;
      const fullName = fieldValue(/nom complet|full name|patient name/);
      const lastName =
        fieldValue(/^(nom|nom du patient|nom de famille|last name|surname)$/) ??
        selectedPatient?.lastName ??
        fullName ??
        cachedPatientLabel;
      const firstName =
        fieldValue(/^(prenom|prenom du patient|first name|given name)$/) ??
        selectedPatient?.firstName;
      const birthDate = fieldValue(/naissance|birth date|date of birth/);
      const age = fieldValue(/(^|\s)age(\s|$)/);
      const patientDate = birthDate ?? age ?? 'Non renseigné';
      const consultationDate = new Date(document.created_at).toLocaleDateString('fr-FR');

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text('République Tunisienne', pageWidth / 2, 12, { align: 'center' });
      pdf.text('Ministère de la Santé', pageWidth / 2, 17, { align: 'center' });
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(14);
      pdf.text('Dr. Hela Benali', pageWidth / 2, 27, { align: 'center' });
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(10);
      pdf.text('Médecine générale', pageWidth / 2, 33, { align: 'center' });
      pdf.text('Avenue Habib Bourguiba, Tunis', pageWidth / 2, 38, { align: 'center' });
      pdf.setDrawColor(100);
      pdf.line(margin, 43, pageWidth - margin, 43);

      const patientBoxY = 48;
      pdf.setDrawColor(140);
      pdf.rect(margin, patientBoxY, contentWidth, 35);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.text('Informations du patient', margin + 4, patientBoxY + 7);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text(`Nom : ${lastName || 'Non renseigné'}`, margin + 4, patientBoxY + 16);
      pdf.text(`Prénom : ${firstName || 'Non renseigné'}`, margin + contentWidth / 2, patientBoxY + 16);
      pdf.text(`Date de naissance / âge : ${patientDate}`, margin + 4, patientBoxY + 27);
      pdf.text(`Date de consultation : ${consultationDate}`, margin + contentWidth / 2, patientBoxY + 27);

      let y = 96;
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(14);
      pdf.text('Prescription', margin, y);
      y += 9;

      const bodyBottom = pageHeight - 75;
      const addPrescriptionPage = (): void => {
        pdf.addPage();
        y = margin + 12;
        pdf.setFont('helvetica', 'bold');
        pdf.setFontSize(11);
        pdf.text('Prescription (suite)', margin, y);
        y += 8;
      };
      const writePrescriptionLine = (text: string): void => {
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(10);
        const lines = pdf.splitTextToSize(text, contentWidth - 6) as string[];
        for (const line of lines) {
          if (y + 5 > bodyBottom) addPrescriptionPage();
          pdf.text(line, margin + 3, y);
          y += 5.5;
        }
      };

      if (fields.length) {
        for (const field of fields) {
          writePrescriptionLine(
            `- ${field.name} : ${field.value?.trim() || 'Non renseigné'}`,
          );
        }
      } else {
        const prescriptionLines = document.raw_text
          .split(/\r?\n/)
          .map((line) => line.trim())
          .filter(Boolean);
        for (const line of prescriptionLines) writePrescriptionLine(`- ${line}`);
        if (!prescriptionLines.length)
          writePrescriptionLine('Aucune information de prescription disponible.');
      }

      const signatureY = Math.max(y + 10, pageHeight - 65);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(10);
      pdf.text('Signature du médecin', margin, signatureY + 5);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.text('Dr. Hela Benali', margin, signatureY + 12);
      pdf.setDrawColor(100);
      pdf.line(margin, signatureY + 29, margin + 62, signatureY + 29);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(8);
      pdf.text('Signature à apposer', margin, signatureY + 34);
      const stampWidth = 54;
      const stampHeight = 34;
      const stampX = pageWidth - margin - stampWidth;
      pdf.rect(stampX, signatureY, stampWidth, stampHeight);
      pdf.text('Espace réservé au cachet', stampX + stampWidth / 2, signatureY + 19, {
        align: 'center',
      });

      const pageCount = pdf.getNumberOfPages();
      for (let page = 1; page <= pageCount; page += 1) {
        pdf.setPage(page);
        pdf.setFont('helvetica', 'normal');
        pdf.setFontSize(8);
        pdf.text('Document non signé électroniquement', margin, pageHeight - 8);
        pdf.text(`${page}/${pageCount}`, pageWidth - margin, pageHeight - 8, {
          align: 'right',
        });
      }

      outputPdf(`${safeTitle || 'document'}.pdf`);
      return;
    }

    const lineHeight = 6;
    let y = margin;

    const write = (text: string, fontSize = 11, bold = false): void => {
      pdf.setFont('helvetica', bold ? 'bold' : 'normal');
      pdf.setFontSize(fontSize);
      for (const paragraph of text.split('\n')) {
        const lines = pdf.splitTextToSize(paragraph || ' ', contentWidth) as string[];
        for (const line of lines) {
          if (y + lineHeight > pageHeight - margin) {
            pdf.addPage();
            y = margin;
          }
          pdf.text(line, margin, y);
          y += lineHeight;
        }
      }
    };

    write(document.title, 18, true);
    y += 2;
    write(`Date : ${new Date(document.created_at).toLocaleString('fr-FR')}`);
    write(`Catégorie : ${this.categoryLabel(document.category_code ?? document.ai_suggested_category_code)}`);
    write(`Statut : ${this.statusLabel(document.status)}`);
    y += 4;
    write('Texte source', 13, true);
    write(document.raw_text);
    y += 4;
    write('Champs extraits', 13, true);
    if (document.extracted_fields.length) {
      for (const field of document.extracted_fields) {
        write(`${field.name} : ${field.value ?? 'Non renseigné'}`);
      }
    } else {
      write('Aucun champ extrait.');
    }
    y += 8;
    write('Signature du médecin', 13, true);
    write(
      document.status === 'VALIDATED' && document.validated_by_name
        ? `Médecin validateur : ${document.validated_by_name}`
        : 'Médecin validateur : non renseigné.',
    );
    write('Signature manuscrite ou électronique : non apposée.');
    write('Ce document PDF n’est pas signé électroniquement.');
    y += 8;
    pdf.setDrawColor(120);
    pdf.line(margin, y, margin + 70, y);

    const pageCount = pdf.getNumberOfPages();
    for (let page = 1; page <= pageCount; page += 1) {
      pdf.setPage(page);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(8);
      pdf.text(
        'Document non signé électroniquement',
        margin,
        pageHeight - 8,
      );
      pdf.text(
        `${page}/${pageCount}`,
        pageWidth - margin,
        pageHeight - 8,
        { align: 'right' },
      );
    }

    outputPdf(`${safeTitle || 'document'}.pdf`);
  }

  private normalizePatientLabel(value: string): string {
    return value.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  }

  private loadPatientNames(documents: DocumentListItem[]): void {
    const unknownPatientIds = [
      ...new Set(
        documents
          .map((document) => document.patient_id)
          .filter((id) => !this.patientNames()[id]),
      ),
    ];
    for (const patientId of unknownPatientIds) {
      this.api.patientOptions('', patientId).subscribe({
        next: ([patient]) => {
          if (!patient) return;
          this.patientNames.update((names) => ({
            ...names,
            [patient.id]: this.formatPatient(patient),
          }));
        },
        error: (error: unknown) => this.fail(error),
      });
    }
  }
}
