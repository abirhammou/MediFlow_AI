import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { Observable, of, switchMap } from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { formatDateTime } from '../birth-date';
import { HistoryScope, HistorySummary, SOURCE_KIND_LABELS, aiErrorMessage } from '../history.model';
import { HistoryService } from '../history.service';
import { PatientPermissions } from '../patient-permissions';
import { SUMMARY_STATUS_LABELS } from '../summary.model';

/**
 * "Synthèse médicale (IA)": the whole history (TIMELINE) or one report (REPORT).
 * DOCTOR / ADMIN generate and read; only a DOCTOR edits, validates or rejects.
 * The AI only reads the reports and the MEDICAL files, never the administrative ones.
 */
@Component({
  selector: 'app-patient-history',
  imports: [Icon],
  templateUrl: './patient-history.html',
  styleUrl: './patient-history.scss',
})
export class PatientHistoryCard {
  readonly patientId = input.required<string>();
  readonly scope = input<HistoryScope>('TIMELINE');
  readonly reportId = input<string | null>(null);
  /** Inside the report viewer: no card frame, smaller title. */
  readonly compact = input(false);

  private history = inject(HistoryService);
  private confirm = inject(ConfirmService);
  private toasts = inject(ToastService);
  protected perms = inject(PatientPermissions);

  protected readonly statusLabels = SUMMARY_STATUS_LABELS;
  protected readonly kindLabels = SOURCE_KIND_LABELS;
  protected readonly formatDateTime = formatDateTime;

  protected loading = signal(true);
  protected loadError = signal<string | null>(null);
  protected actionError = signal<string | null>(null);
  protected generating = signal(false);
  protected busy = signal(false);
  protected versions = signal<HistorySummary[]>([]);
  protected draft = computed(() => {
    const latest = this.versions()[0];
    return latest?.status === 'DRAFT' ? latest : null;
  });
  protected current = computed(() => this.versions().find((s) => s.status === 'VALIDATED') ?? null);
  protected draftText = signal('');
  protected dirty = computed(() => this.draftText().trim() !== (this.draft()?.content ?? ''));
  protected title = computed(() =>
    this.scope() === 'REPORT' ? 'Résumé IA du compte rendu' : 'Synthèse médicale (IA)',
  );

  protected rejectComment = signal('');
  private rejectDialog = viewChild<ElementRef<HTMLDialogElement>>('rejectDialog');

  constructor() {
    effect(() => {
      const key = [this.patientId(), this.scope(), this.reportId()] as const;
      untracked(() => this.load(...key));
    });
  }

  private load(patientId: string, scope: HistoryScope, reportId: string | null): void {
    this.loading.set(true);
    this.loadError.set(null);
    this.history.list(patientId, scope, reportId).subscribe({
      next: (versions) => this.show(versions),
      error: (err) => {
        this.loadError.set(apiErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  private show(versions: HistorySummary[]): void {
    this.versions.set(versions);
    this.draftText.set(this.draft()?.content ?? '');
    this.loading.set(false);
  }

  private reload(): void {
    this.history.list(this.patientId(), this.scope(), this.reportId()).subscribe({
      next: (versions) => this.show(versions),
      error: (err) => this.actionError.set(apiErrorMessage(err)),
    });
  }

  protected async generate(): Promise<void> {
    if (this.generating()) return;
    if (this.draft() && this.dirty()) {
      const confirmed = await this.confirm.ask({
        title: 'Régénérer la synthèse ?',
        message: 'Vos modifications du brouillon actuel ne seront pas enregistrées.',
        confirmLabel: 'Régénérer',
      });
      if (!confirmed) return;
    }
    this.generating.set(true);
    this.actionError.set(null);
    this.history.generate(this.patientId(), this.scope(), this.reportId()).subscribe({
      next: (summary) => {
        this.generating.set(false);
        this.show([summary, ...this.versions()]);
      },
      error: (err) => {
        this.generating.set(false);
        this.actionError.set(aiErrorMessage(err));
      },
    });
  }

  private saved(draft: HistorySummary): Observable<HistorySummary> {
    return this.dirty() ? this.history.update(this.patientId(), draft.id, this.draftText().trim()) : of(draft);
  }

  private run(action: Observable<HistorySummary>, success: string): void {
    this.busy.set(true);
    this.actionError.set(null);
    action.subscribe({
      next: () => {
        this.busy.set(false);
        this.toasts.show(success);
        this.reload();
      },
      error: (err) => {
        this.busy.set(false);
        this.actionError.set(apiErrorMessage(err));
        if (err instanceof HttpErrorResponse && err.status === 409) this.reload();
      },
    });
  }

  protected save(draft: HistorySummary): void {
    if (this.draftText().trim()) this.run(this.saved(draft), 'Brouillon enregistré.');
  }

  protected validate(draft: HistorySummary): void {
    if (!this.draftText().trim()) return;
    const id = this.patientId();
    this.run(
      this.saved(draft).pipe(switchMap((saved) => this.history.validate(id, saved.id))),
      'Synthèse validée.',
    );
  }

  protected openReject(): void {
    this.rejectComment.set('');
    this.rejectDialog()?.nativeElement.showModal();
  }

  protected closeReject(): void {
    this.rejectDialog()?.nativeElement.close();
  }

  protected reject(draft: HistorySummary): void {
    const comment = this.rejectComment().trim();
    if (!comment) return;
    this.closeReject();
    this.run(this.history.reject(this.patientId(), draft.id, comment), 'Brouillon rejeté.');
  }
}
