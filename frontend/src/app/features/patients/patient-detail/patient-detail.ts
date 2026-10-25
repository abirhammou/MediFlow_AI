import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { ConfirmService } from '../../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { ageLabel, formatBirthDate, formatDateTime } from '../birth-date';
import { PatientPermissions } from '../patient-permissions';
import { PatientAccountCard } from '../patient-account/patient-account';
import { PatientChat } from '../patient-chat/patient-chat';
import { PatientFilesCard } from '../patient-files/patient-files';
import { PatientHistoryCard } from '../patient-history/patient-history';
import { PatientInvoicesCard } from '../patient-invoices/patient-invoices';
import { PatientReportsCard } from '../patient-reports/patient-reports';
import { PatientSummaryCard } from '../patient-summary/patient-summary';
import { GENDER_LABELS, Patient } from '../patient.model';
import { PatientService } from '../patient.service';

@Component({
  selector: 'app-patient-detail',
  imports: [
    RouterLink,
    Icon,
    PatientSummaryCard,
    PatientHistoryCard,
    PatientReportsCard,
    PatientFilesCard,
    PatientInvoicesCard,
    PatientAccountCard,
    PatientChat,
  ],
  templateUrl: './patient-detail.html',
  styleUrl: './patient-detail.scss',
})
export class PatientDetail {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private patients = inject(PatientService);
  private confirm = inject(ConfirmService);
  private toasts = inject(ToastService);
  protected perms = inject(PatientPermissions);

  protected readonly genderLabels = GENDER_LABELS;
  protected readonly formatBirthDate = formatBirthDate;
  protected readonly formatDateTime = formatDateTime;
  protected readonly ageLabel = ageLabel;

  protected patient = signal<Patient | null>(null);
  protected error = signal<string | null>(null);
  protected deleting = signal(false);

  constructor() {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.patients.get(id).subscribe({
      next: patient => this.patient.set(patient),
      error: err => this.error.set(apiErrorMessage(err)),
    });
  }

  protected async remove(patient: Patient): Promise<void> {
    const confirmed = await this.confirm.ask({
      title: 'Supprimer ce dossier ?',
      message: `Le dossier ${patient.recordNumber} de ${patient.firstName} ${patient.lastName} sera retiré de la liste. Un administrateur pourra le restaurer.`,
      confirmLabel: 'Supprimer',
      danger: true,
    });
    if (!confirmed) return;
    this.deleting.set(true);
    this.patients.remove(patient.id).subscribe({
      next: () => {
        this.toasts.show(`Dossier ${patient.recordNumber} supprimé.`);
        this.router.navigate(['/patients']);
      },
      error: err => {
        this.deleting.set(false);
        this.toasts.show(apiErrorMessage(err), 'error');
      },
    });
  }
}
