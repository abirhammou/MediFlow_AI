import { Component, computed, inject, signal } from '@angular/core';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { ageLabel, formatDateTime } from '../birth-date';
import { DeletedPatientItem, GENDER_LABELS, Page } from '../patient.model';
import { PatientService } from '../patient.service';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-deleted-patients',
  imports: [Icon],
  templateUrl: './deleted-patients.html',
})
export class DeletedPatients {
  private patients = inject(PatientService);
  private toasts = inject(ToastService);

  protected readonly genderLabels = GENDER_LABELS;
  protected readonly formatDateTime = formatDateTime;
  protected readonly ageLabel = ageLabel;

  protected result = signal<Page<DeletedPatientItem> | null>(null);
  protected error = signal<string | null>(null);
  protected loading = signal(false);
  protected restoring = signal<string | null>(null);
  protected pageCount = computed(() => {
    const result = this.result();
    return result ? Math.max(1, Math.ceil(result.total / result.size)) : 1;
  });

  constructor() {
    this.load(1);
  }

  protected load(page: number): void {
    this.loading.set(true);
    this.error.set(null);
    this.patients.listDeleted(page, PAGE_SIZE).subscribe({
      next: result => {
        // Restoring the last row of a page: show the previous page instead of an empty one.
        if (result.items.length === 0 && page > 1) return this.load(page - 1);
        this.result.set(result);
        this.loading.set(false);
      },
      error: err => {
        this.error.set(apiErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  protected restore(patient: DeletedPatientItem): void {
    this.restoring.set(patient.id);
    this.patients.restore(patient.id).subscribe({
      next: () => {
        this.restoring.set(null);
        this.toasts.show(`Dossier ${patient.recordNumber} restauré.`);
        this.load(this.result()?.page ?? 1);
      },
      error: err => {
        this.restoring.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }
}
