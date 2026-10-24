import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  Observable,
  catchError,
  debounceTime,
  distinctUntilChanged,
  map,
  of,
  switchMap,
} from 'rxjs';
import { apiErrorMessage } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { ToastService } from '../../../shared/toast/toast.service';
import { ageFrom, ageLabel, formatBirthDate, todayIso } from '../birth-date';
import {
  BLOOD_TYPES,
  BloodType,
  CITIES,
  FieldError,
  GENDERS,
  GENDER_LABELS,
  Gender,
  Patient,
  PatientListItem,
  PatientPayload,
} from '../patient.model';
import { PatientService } from '../patient.service';
import {
  birthDate,
  email,
  firstError,
  maxLength,
  nationalId,
  phone,
  requiredText,
} from '../patient-validators';
import { HasUnsavedChanges } from '../unsaved-changes.guard';

function blank(value: string): string | null {
  return value.trim() || null;
}

/** Nested sections: trimmed values, and null when every field is empty. */
function section<K extends string>(values: Record<K, string>): Record<K, string | null> | null {
  const cleaned = Object.fromEntries(
    Object.entries<string>(values).map(([key, value]) => [key, blank(value)]),
  ) as Record<K, string | null>;
  return Object.values(cleaned).some(value => value !== null) ? cleaned : null;
}

/** Top-level keys whose value differs (a nested section is compared, and sent, as a whole). */
function changedFields(before: PatientPayload, after: PatientPayload): Partial<PatientPayload> {
  const changes: Record<string, unknown> = {};
  for (const key of Object.keys(after) as (keyof PatientPayload)[]) {
    if (JSON.stringify(before[key]) !== JSON.stringify(after[key])) changes[key] = after[key];
  }
  return changes as Partial<PatientPayload>;
}

@Component({
  selector: 'app-patient-form',
  imports: [ReactiveFormsModule, RouterLink, Icon],
  templateUrl: './patient-form.html',
  styleUrl: './patient-form.scss',
  host: { '(window:beforeunload)': 'onBeforeUnload($event)' },
})
export class PatientForm implements HasUnsavedChanges {
  private fb = inject(FormBuilder).nonNullable;
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private patients = inject(PatientService);
  private toasts = inject(ToastService);

  protected readonly genders = GENDERS;
  protected readonly genderLabels = GENDER_LABELS;
  protected readonly bloodTypes = BLOOD_TYPES;
  protected readonly cities = CITIES;
  protected readonly today = todayIso();
  protected readonly formatBirthDate = formatBirthDate;

  protected form = this.fb.group({
    firstName: ['', [requiredText, maxLength(80)]],
    lastName: ['', [requiredText, maxLength(80)]],
    dateOfBirth: ['', [requiredText, birthDate]],
    gender: ['' as Gender | '', requiredText],
    nationalId: ['', nationalId],
    bloodType: ['' as BloodType | ''],
    phone: ['', phone],
    email: ['', [email, maxLength(254)]],
    address: this.fb.group({
      street: ['', maxLength(200)],
      city: ['', maxLength(100)],
      postalCode: ['', maxLength(20)],
    }),
    insurance: this.fb.group({
      provider: ['', maxLength(100)],
      number: ['', maxLength(50)],
    }),
    emergencyContact: this.fb.group({
      name: ['', maxLength(200)],
      phone: ['', phone],
      relation: ['', maxLength(50)],
    }),
    administrativeNotes: ['', maxLength(5000)],
  });

  private readonly patientId = this.route.snapshot.paramMap.get('id');
  protected readonly editing = signal(this.patientId !== null);
  protected patient = signal<Patient | null>(null);
  /** Payload of the loaded patient, to send only what changed. */
  private original: PatientPayload | null = null;
  private saved = false;

  protected loading = signal(this.patientId !== null);
  protected loadError = signal<string | null>(null);
  protected submitting = signal(false);
  protected generalError = signal<string | null>(null);
  protected duplicates = signal<PatientListItem[]>([]);
  protected age = signal<string>('');
  protected notesLength = signal(0);
  protected title = computed(() => {
    const patient = this.patient();
    return patient ? `Modifier ${patient.firstName} ${patient.lastName}` : 'Nouveau patient';
  });

  constructor() {
    if (this.patientId !== null) this.load(this.patientId);
    else this.watchDuplicates();

    this.form.controls.dateOfBirth.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(value => this.age.set(ageLabel(ageFrom(value))));
    this.form.controls.administrativeNotes.valueChanges
      .pipe(takeUntilDestroyed())
      .subscribe(value => this.notesLength.set(value.length));
  }

  private load(id: string): void {
    this.patients.get(id).subscribe({
      next: patient => {
        this.patient.set(patient);
        this.form.setValue({
          firstName: patient.firstName,
          lastName: patient.lastName,
          dateOfBirth: patient.dateOfBirth,
          gender: patient.gender,
          nationalId: patient.nationalId ?? '',
          bloodType: patient.bloodType ?? '',
          phone: patient.phone ?? '',
          email: patient.email ?? '',
          address: {
            street: patient.address?.street ?? '',
            city: patient.address?.city ?? '',
            postalCode: patient.address?.postalCode ?? '',
          },
          insurance: {
            provider: patient.insurance?.provider ?? '',
            number: patient.insurance?.number ?? '',
          },
          emergencyContact: {
            name: patient.emergencyContact?.name ?? '',
            phone: patient.emergencyContact?.phone ?? '',
            relation: patient.emergencyContact?.relation ?? '',
          },
          administrativeNotes: patient.administrativeNotes ?? '',
        });
        this.original = this.payload();
        this.form.markAsPristine();
        this.loading.set(false);
      },
      error: err => {
        this.loadError.set(apiErrorMessage(err));
        this.loading.set(false);
      },
    });
  }

  /** Non-blocking warning when a patient with the same names and birth date exists. */
  private watchDuplicates(): void {
    const controls = this.form.controls;
    this.form.valueChanges
      .pipe(
        map(() => ({
          firstName: controls.firstName.value.trim(),
          lastName: controls.lastName.value.trim(),
          dateOfBirth: controls.dateOfBirth.value,
          complete:
            controls.firstName.valid && controls.lastName.valid && controls.dateOfBirth.valid,
        })),
        distinctUntilChanged((a, b) => JSON.stringify(a) === JSON.stringify(b)),
        debounceTime(400),
        switchMap(({ firstName, lastName, dateOfBirth, complete }) =>
          complete
            ? this.patients
                .findDuplicates(firstName, lastName, dateOfBirth)
                .pipe(catchError(() => of([])))
            : of([]),
        ),
        takeUntilDestroyed(),
      )
      .subscribe(duplicates => this.duplicates.set(duplicates));
  }

  private payload(): PatientPayload {
    const value = this.form.getRawValue();
    return {
      firstName: value.firstName.trim(),
      lastName: value.lastName.trim(),
      dateOfBirth: value.dateOfBirth,
      gender: value.gender as Gender,
      nationalId: blank(value.nationalId),
      phone: blank(value.phone),
      email: blank(value.email)?.toLowerCase() ?? null,
      address: section(value.address),
      bloodType: value.bloodType || null,
      insurance: section(value.insurance),
      emergencyContact: section(value.emergencyContact),
      administrativeNotes: blank(value.administrativeNotes),
    };
  }

  private changes(): Partial<PatientPayload> {
    return this.original ? changedFields(this.original, this.payload()) : {};
  }

  hasUnsavedChanges(): boolean {
    if (this.saved || this.loading() || this.loadError()) return false;
    return this.editing() ? Object.keys(this.changes()).length > 0 : this.form.dirty;
  }

  protected onBeforeUnload(event: BeforeUnloadEvent): void {
    if (this.hasUnsavedChanges()) event.preventDefault();
  }

  /**
   * Message to show under a field. When editing, a value loaded from the
   * database is only checked once the user changes it (older records may
   * predate a rule); the server's errors are always shown.
   */
  protected error(path: string): string | null {
    const errors = this.form.get(path)?.errors;
    if (!errors) return null;
    const server = errors['server'];
    if (typeof server === 'string') return server;
    const control = this.form.get(path) as AbstractControl;
    const visible = control.dirty || (control.touched && !this.editing());
    return visible ? firstError(errors) : null;
  }

  protected submit(): void {
    this.generalError.set(null);
    const patient = this.patient();
    let request: Observable<Patient>;

    if (patient && this.original) {
      const changes = this.changes();
      const keys = Object.keys(changes) as (keyof PatientPayload)[];
      const invalid = keys.filter(key => this.form.controls[key].invalid);
      if (invalid.length) {
        invalid.forEach(key => this.form.controls[key].markAsDirty());
        this.focusFirstError();
        return;
      }
      if (keys.length === 0) {
        this.leave(patient, 'Aucune modification à enregistrer.');
        return;
      }
      request = this.patients.update(patient.id, changes);
    } else {
      if (this.form.invalid) {
        this.form.markAllAsTouched();
        this.focusFirstError();
        return;
      }
      request = this.patients.create(this.payload());
    }

    this.submitting.set(true);
    request.subscribe({
      next: saved =>
        this.leave(saved, patient ? 'Dossier mis à jour.' : `Dossier ${saved.recordNumber} créé.`),
      error: err => {
        this.submitting.set(false);
        this.showServerErrors(err);
      },
    });
  }

  private leave(patient: Patient, message: string): void {
    this.saved = true;
    this.toasts.show(message);
    this.router.navigate(['/patients', patient.id]);
  }

  /** 409 (CIN already used) and 422 (field errors) are shown under the fields concerned. */
  private showServerErrors(err: unknown): void {
    if (err instanceof HttpErrorResponse) {
      if (err.status === 409 && err.error?.code === 'national_id_exists') {
        this.setServerError(this.form.controls.nationalId, err.error.detail);
        this.focusFirstError();
        return;
      }
      if (err.status === 422 && Array.isArray(err.error?.detail)) {
        let unmatched = false;
        for (const fieldError of err.error.detail as FieldError[]) {
          const path = fieldError.loc.slice(1).map(String); // drop "body"
          const control = path.length ? this.form.get(path) : null;
          if (control) this.setServerError(control, fieldError.msg);
          else unmatched = true;
        }
        this.generalError.set(
          unmatched
            ? 'Certaines informations saisies sont invalides.'
            : 'Corrigez les champs signalés.',
        );
        this.focusFirstError();
        return;
      }
    }
    this.generalError.set(apiErrorMessage(err));
  }

  /** Cleared by Angular as soon as the field's value changes. */
  private setServerError(control: AbstractControl, message: string): void {
    control.setErrors({ ...control.errors, server: message });
    control.markAsTouched();
  }

  private focusFirstError(): void {
    setTimeout(() => {
      const first = document.querySelector<HTMLElement>(
        '.patients-area [aria-invalid="true"], .patients-area .alert',
      );
      first?.focus?.();
      first?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }
}
