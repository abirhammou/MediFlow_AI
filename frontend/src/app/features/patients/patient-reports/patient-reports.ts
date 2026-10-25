import { Component, ElementRef, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ReportListItem, ReportOut, ReportStatus, ReportsApi } from '../../../pages/report-writer/reports.api';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { formatDateTime } from '../birth-date';
import { PatientHistoryCard } from '../patient-history/patient-history';
import { PatientPermissions } from '../patient-permissions';

/** The patient file shows at most this many reports (newest first). */
const PAGE_SIZE = 50;

export const REPORT_STATUS_LABELS: Record<ReportStatus, string> = {
  DRAFT: 'Brouillon',
  FINAL: 'Finalisé',
  ARCHIVED: 'Archivé',
};

/** `structured_content` is stored as "## Title\nBody" blocks (reports/service.py render()). */
export function reportSections(content: string | null): { title: string; body: string }[] {
  if (!content) return [];
  return content
    .split(/^## /m)
    .filter((part) => part.trim())
    .map((part) => {
      const [title, ...rest] = part.split('\n');
      return { title: title.trim(), body: rest.join('\n').trim() };
    });
}

/**
 * "Comptes rendus" card of the patient page: every non-archived report of the patient,
 * whoever wrote it. A DOCTOR reads them all but only edits or finalizes their own DRAFTs
 * (in ReportWriter); SECRETARY only gets the FINAL ones, without raw notes (server side).
 */
@Component({
  selector: 'app-patient-reports',
  imports: [Icon, RouterLink, PatientHistoryCard],
  templateUrl: './patient-reports.html',
  styleUrl: './patient-reports.scss',
})
export class PatientReportsCard {
  readonly patientId = input.required<string>();

  private api = inject(ReportsApi);
  private toasts = inject(ToastService);
  protected perms = inject(PatientPermissions);

  protected readonly statusLabels = REPORT_STATUS_LABELS;
  protected readonly formatDateTime = formatDateTime;

  protected loading = signal(true);
  protected error = signal<string | null>(null);
  protected reports = signal<ReportListItem[]>([]);
  protected total = signal(0);
  protected exporting = signal<string | null>(null);

  protected opened = signal<ReportOut | null>(null);
  protected sections = computed(() => reportSections(this.opened()?.structured_content ?? null));
  private viewer = viewChild<ElementRef<HTMLDialogElement>>('viewer');

  constructor() {
    effect(() => {
      const patientId = this.patientId();
      untracked(() => this.load(patientId));
    });
  }

  private load(patientId: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list({ patient_id: patientId, page: 1, size: PAGE_SIZE }).subscribe({
      next: (page) => {
        this.reports.set(page.items);
        this.total.set(page.total);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(apiErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  protected open(report: ReportListItem): void {
    this.api.get(report.id).subscribe({
      next: (full) => {
        this.opened.set(full);
        this.viewer()?.nativeElement.showModal();
      },
      error: (err) => this.toasts.show(apiErrorMessage(err), 'error'),
    });
  }

  protected close(): void {
    this.viewer()?.nativeElement.close();
    this.opened.set(null);
  }

  protected downloadPdf(report: Pick<ReportListItem, 'id' | 'title'>): void {
    if (this.exporting()) return;
    this.exporting.set(report.id);
    this.api.downloadPdf(report.id, report.title).subscribe({
      next: () => this.exporting.set(null),
      error: (err) => {
        this.exporting.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }
}
