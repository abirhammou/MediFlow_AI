import { Component, computed, effect, inject, input, signal, untracked } from '@angular/core';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { formatDateTime } from '../birth-date';
import {
  ACCEPTED_FILES,
  FILE_CATEGORY_LABELS,
  FILE_TYPE_LABELS,
  FileCategory,
  FileType,
  MAX_UPLOAD_BYTES,
  PatientFile,
  TYPES_BY_CATEGORY,
  downloadName,
  formatSize,
  saveBlob,
} from '../patient-file.model';
import { PatientFilesService } from '../patient-files.service';
import { PatientPermissions } from '../patient-permissions';

type Filter = FileCategory | 'ALL';

/**
 * "Documents" card of the patient page. SECRETARY / ADMIN upload and delete; a DOCTOR
 * only reads MEDICAL files (the API never sends the ADMINISTRATIVE ones to doctors).
 */
@Component({
  selector: 'app-patient-files',
  imports: [Icon],
  templateUrl: './patient-files.html',
  styleUrl: './patient-files.scss',
})
export class PatientFilesCard {
  readonly patientId = input.required<string>();

  private files = inject(PatientFilesService);
  private confirm = inject(ConfirmService);
  private toasts = inject(ToastService);
  protected perms = inject(PatientPermissions);

  protected readonly categoryLabels = FILE_CATEGORY_LABELS;
  protected readonly typeLabels = FILE_TYPE_LABELS;
  protected readonly accepted = ACCEPTED_FILES;
  protected readonly formatDateTime = formatDateTime;
  protected readonly formatSize = formatSize;

  protected loading = signal(true);
  protected error = signal<string | null>(null);
  protected all = signal<PatientFile[]>([]);
  protected filter = signal<Filter>('ALL');
  protected busyId = signal<string | null>(null);
  protected visible = computed(() => {
    const filter = this.filter();
    return filter === 'ALL' ? this.all() : this.all().filter((f) => f.category === filter);
  });
  protected counts = computed(() => {
    const counts: Record<Filter, number> = { ALL: this.all().length, ADMINISTRATIVE: 0, MEDICAL: 0 };
    for (const file of this.all()) counts[file.category]++;
    return counts;
  });

  // Upload form
  protected formOpen = signal(false);
  protected uploading = signal(false);
  protected uploadError = signal<string | null>(null);
  protected selected = signal<File | null>(null);
  protected category = signal<FileCategory>('MEDICAL');
  protected type = signal<FileType>('SCAN');
  protected title = signal('');
  protected types = computed(() => TYPES_BY_CATEGORY[this.category()]);

  constructor() {
    effect(() => {
      const patientId = this.patientId();
      untracked(() => this.load(patientId));
    });
  }

  private load(patientId: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.files.list(patientId).subscribe({
      next: (files) => {
        this.all.set(files);
        this.loading.set(false);
      },
      error: (err) => {
        this.error.set(apiErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  protected canDelete(file: PatientFile): boolean {
    return this.perms.writableFileCategories().includes(file.category);
  }

  protected openForm(): void {
    const writable = this.perms.writableFileCategories();
    const category = writable.includes(this.category()) ? this.category() : writable[0];
    this.setCategory(category);
    this.selected.set(null);
    this.title.set('');
    this.uploadError.set(null);
    this.formOpen.set(true);
  }

  protected setCategory(category: FileCategory): void {
    this.category.set(category);
    this.type.set(TYPES_BY_CATEGORY[category][0]);
  }

  protected pick(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.uploadError.set(null);
    if (file && file.size > MAX_UPLOAD_BYTES) {
      this.uploadError.set('Le fichier dépasse 10 Mo.');
      this.selected.set(null);
      return;
    }
    this.selected.set(file);
    if (file && !this.title().trim()) this.title.set(file.name.replace(/\.[^.]+$/, ''));
  }

  protected upload(): void {
    const file = this.selected();
    const title = this.title().trim();
    if (!file || !title || this.uploading()) return;
    this.uploading.set(true);
    this.uploadError.set(null);
    this.files
      .upload(this.patientId(), { file, title, category: this.category(), type: this.type() })
      .subscribe({
        next: (created) => {
          this.uploading.set(false);
          this.formOpen.set(false);
          this.all.update((files) => [created, ...files]);
          this.toasts.show('Document ajouté.');
        },
        error: (err) => {
          this.uploading.set(false);
          this.uploadError.set(apiErrorMessage(err));
        },
      });
  }

  protected download(file: PatientFile): void {
    if (this.busyId()) return;
    this.busyId.set(file.id);
    this.files.download(this.patientId(), file.id).subscribe({
      next: (blob) => {
        this.busyId.set(null);
        saveBlob(blob, downloadName(file));
      },
      error: (err) => {
        this.busyId.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }

  protected async remove(file: PatientFile): Promise<void> {
    const confirmed = await this.confirm.ask({
      title: 'Retirer ce document ?',
      message: `« ${file.title} » ne sera plus visible dans le dossier. Le fichier est conservé pour l'historique.`,
      confirmLabel: 'Retirer',
      danger: true,
    });
    if (!confirmed) return;
    this.busyId.set(file.id);
    this.files.remove(this.patientId(), file.id).subscribe({
      next: () => {
        this.busyId.set(null);
        this.all.update((files) => files.filter((f) => f.id !== file.id));
        this.toasts.show('Document retiré.');
      },
      error: (err) => {
        this.busyId.set(null);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }
}
