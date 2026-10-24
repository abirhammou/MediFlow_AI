import { HttpErrorResponse } from '@angular/common/http';
import {
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Observable, of, switchMap } from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { formatDateTime } from '../birth-date';
import { PatientPermissions } from '../patient-permissions';
import { PatientSummary, SUMMARY_STATUS_LABELS, summaryErrorMessage } from '../summary.model';
import { SummaryService } from '../summary.service';

type Tab = 'summary' | 'history';

/**
 * "Résumé administratif (IA)" card of the patient page.
 * DOCTOR / ADMIN generate drafts and see the history; only a DOCTOR edits,
 * validates or rejects a draft; SECRETARY only reads the validated summary.
 */
@Component({
  selector: 'app-patient-summary',
  imports: [Icon],
  templateUrl: './patient-summary.html',
  styleUrl: './patient-summary.scss',
})
export class PatientSummaryCard {
  readonly patientId = input.required<string>();

  private summaries = inject(SummaryService);
  private confirm = inject(ConfirmService);
  private toasts = inject(ToastService);
  protected perms = inject(PatientPermissions);

  protected readonly statusLabels = SUMMARY_STATUS_LABELS;
  protected readonly formatDateTime = formatDateTime;

  protected loading = signal(true);
  protected loadError = signal<string | null>(null);
  protected actionError = signal<string | null>(null);
  protected generating = signal(false);
  protected busy = signal(false);
  protected tab = signal<Tab>('summary');

  protected current = signal<PatientSummary | null>(null);
  protected history = signal<PatientSummary[]>([]);
  /** The latest generation, while it is still a DRAFT. */
  protected draft = computed(() => {
    const latest = this.history()[0];
    return latest?.status === 'DRAFT' ? latest : null;
  });
  protected draftText = signal('');
  protected dirty = computed(() => this.draftText().trim() !== (this.draft()?.content ?? ''));

  protected rejectComment = signal('');
  private rejectDialog = viewChild<ElementRef<HTMLDialogElement>>('rejectDialog');

  constructor() {
    // Reload when the page switches to another patient.
    effect(() => {
      const patientId = this.patientId();
      untracked(() => this.load(patientId));
    });
  }

  private load(patientId: string): void {
    this.loading.set(true);
    this.loadError.set(null);
    if (this.perms.canSeeSummaryHistory()) {
      this.summaries.list(patientId).subscribe({
        next: (history) => this.showHistory(history),
        error: (err) => this.failLoading(err),
      });
    } else {
      this.summaries.current(patientId).subscribe({
        next: (summary) => {
          this.current.set(summary);
          this.loading.set(false);
        },
        error: (err) => {
          if (err instanceof HttpErrorResponse && err.status === 404) {
            this.current.set(null);
            this.loading.set(false);
          } else this.failLoading(err);
        },
      });
    }
  }

  private showHistory(history: PatientSummary[]): void {
    this.history.set(history);
    this.current.set(history.find((summary) => summary.status === 'VALIDATED') ?? null);
    this.draftText.set(this.draft()?.content ?? '');
    this.loading.set(false);
  }

  private failLoading(error: unknown): void {
    this.loadError.set(apiErrorMessage(error));
    this.loading.set(false);
  }

  private reload(): void {
    this.summaries.list(this.patientId()).subscribe({
      next: (history) => this.showHistory(history),
      error: (err) => this.actionError.set(apiErrorMessage(err)),
    });
  }

  protected async generate(): Promise<void> {
    if (this.generating()) return;
    if (this.draft() && this.dirty()) {
      const confirmed = await this.confirm.ask({
        title: 'Régénérer le résumé ?',
        message: 'Vos modifications du brouillon actuel ne seront pas enregistrées.',
        confirmLabel: 'Régénérer',
      });
      if (!confirmed) return;
    }
    this.generating.set(true);
    this.actionError.set(null);
    this.summaries.generate(this.patientId()).subscribe({
      next: (summary) => {
        this.generating.set(false);
        this.tab.set('summary');
        this.showHistory([summary, ...this.history()]);
      },
      error: (err) => {
        this.generating.set(false);
        this.actionError.set(summaryErrorMessage(err));
      },
    });
  }

  /** PATCH the edited text first when it changed. */
  private saved(draft: PatientSummary): Observable<PatientSummary> {
    const text = this.draftText().trim();
    return this.dirty() ? this.summaries.update(this.patientId(), draft.id, text) : of(draft);
  }

  private run(action: Observable<PatientSummary>, success: string): void {
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

  protected save(draft: PatientSummary): void {
    if (!this.draftText().trim()) return;
    this.run(this.saved(draft), 'Brouillon enregistré.');
  }

  protected validate(draft: PatientSummary): void {
    if (!this.draftText().trim()) return;
    const id = this.patientId();
    this.run(
      this.saved(draft).pipe(switchMap((saved) => this.summaries.validate(id, saved.id))),
      'Résumé validé.',
    );
  }

  protected openReject(): void {
    this.rejectComment.set('');
    this.rejectDialog()?.nativeElement.showModal();
  }

  protected closeReject(): void {
    this.rejectDialog()?.nativeElement.close();
  }

  protected reject(draft: PatientSummary): void {
    const comment = this.rejectComment().trim();
    if (!comment) return;
    this.closeReject();
    this.run(this.summaries.reject(this.patientId(), draft.id, comment), 'Brouillon rejeté.');
  }
}
