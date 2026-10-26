import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { AuthService, apiErrorMessage } from '../../core/auth/auth.service';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../shared/icon/icon';
import { ToastService } from '../../shared/toast/toast.service';
import {
  Appointment, AppointmentStatus, AppointmentsApi, ParseResult, STATUS_LABELS, Slot,
} from './appointments.api';
import { VoiceButton } from './voice-button';

import { PatientPicker } from './patient-picker';
import { AppointmentStats, StatsData } from './appointment-stats';

const CLINIC_TZ = 'Africa/Tunis';
const DAY_MS = 24 * 3600 * 1000;

/** Jour (YYYY-MM-DD) d'une date, à l'heure de la clinique. */
function clinicDay(date: Date): string {
  return date.toLocaleDateString('en-CA', { timeZone: CLINIC_TZ });
}

export type ViewMode = 'patient' | 'secretary' | 'admin' | 'doctor';

/**
 * Une seule vue, adaptée au rôle :
 *  - patient   : demande en langage libre, réservation, ses rendez-vous, annulation
 *  - secretary : idem pour un patient donné + liste complète, statuts, annulation
 *  - admin     : supervision (liste, statuts, annulation)
 *  - doctor    : son agenda, changement de statut
 */
@Component({
  selector: 'app-appointment-view',
    imports: [Icon, FormsModule, DatePipe, AppointmentStats, PatientPicker, VoiceButton],
  styleUrl: './appointment-manager.scss',
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#ede9fe;color:#7c3aed"><app-icon name="calendar" [size]="24" /></div>
        <div>
          <h1>Appointment Manager AI</h1>
          <p>{{ subtitle() }}</p>
        </div>
      </div>

      @if (canBook()) {
        <section class="card">
          <h2>Demander un rendez-vous</h2>
          <p class="muted">Écrivez votre demande comme vous la diriez : « Je voudrais voir un cardiologue mardi matin ».</p>
          @if (mode() === 'secretary') {
            <div class="f"><span>Patient</span>
              <app-patient-picker [allowCreate]="true" (picked)="onPatientPicked($event)" /></div>
          }
          <label class="f"><span>Demande</span>
            <textarea rows="3" [ngModel]="message()" (ngModelChange)="message.set($event)" maxlength="2000" placeholder="Ex. Rendez-vous demain après-midi pour un contrôle"></textarea></label>
          <div class="actions-row">
            <button type="button" class="btn primary" [disabled]="searching() || !message().trim()" (click)="search()">
              ✨ {{ searching() ? 'Recherche…' : 'Trouver des créneaux' }}
            </button>
            <app-voice-button (text)="message.set($event)" />
          </div>

          @if (result(); as r) {
            <p class="muted top">
              Compris : {{ r.parsed.preferred_date ?? 'date libre' }}
              @if (r.parsed.day_part) { · {{ r.parsed.day_part }} }
              @if (r.parsed.specialty) { · {{ r.parsed.specialty }} }
              @if (r.parsed.reason) { · {{ r.parsed.reason }} }
            </p>
            @if (r.available_slots.length) {
              <div class="slots">
                @for (s of r.available_slots; track s.doctor_id + s.start_at) {
                  <button type="button" class="slot" [disabled]="booking()" (click)="book(r, s)">
                    <strong>{{ s.start_at | date: 'EEE d MMM, HH:mm' }}</strong>
                    <small>{{ s.doctor_name }}</small>
                  </button>
                }
              </div>
            } @else {
              <p class="muted top">Aucun créneau libre trouvé pour cette demande. Essayez une autre date.</p>
            }
          }
        </section>
      }

      @if (mode() === 'admin') {
        <app-appointment-stats [stats]="stats()" />
      }

      <section class="card">
        <div class="head">
          <h2>{{ mode() === 'patient' ? 'Mes rendez-vous' : mode() === 'doctor' ? 'Mon agenda' : 'Rendez-vous' }}</h2>
          <select [(ngModel)]="statusFilter" (ngModelChange)="reload(1)">
            <option value="">Tous les statuts</option>
            @for (s of statuses; track s) { <option [value]="s">{{ label(s) }}</option> }
          </select>
        </div>

        @if (mode() === 'admin') {
          <div class="filters">
            <label><span>Médecin</span>
              <select [(ngModel)]="doctorFilter" (ngModelChange)="reload(1)">
                <option value="">Tous les médecins</option>
                @for (d of doctors(); track d.id) { <option [value]="d.id">{{ d.name }}</option> }
              </select>
            </label>
            <label class="wide"><span>Patient</span>
              <app-patient-picker #filterPicker (picked)="onPatientFilter($event)" />
            </label>
            <label><span>Du</span><input type="date" [(ngModel)]="dateFrom" (ngModelChange)="reload(1)" /></label>
            <label><span>Au</span><input type="date" [(ngModel)]="dateTo" (ngModelChange)="reload(1)" /></label>
            @if (hasFilters()) {
              <button type="button" class="btn sm reset" (click)="resetFilters(filterPicker)">Réinitialiser</button>
            }
          </div>
        }

        @if (error()) { <div class="alert error">{{ error() }}</div> }

        @if (loading()) {
          <p class="muted">Chargement…</p>
        } @else if (!items().length) {
          <p class="muted">Aucun rendez-vous.</p>
        } @else {
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>Date</th>
                @if (mode() !== 'patient') { <th>Patient</th> }
                @if (mode() !== 'doctor') { <th>Médecin</th> }
                <th>Motif</th><th>Statut</th><th></th>
              </tr></thead>
              <tbody>
                @for (a of items(); track a.id) {
                  <tr>
                    <td>{{ a.start_at | date: 'dd/MM/yyyy HH:mm' }}</td>
                    @if (mode() !== 'patient') { <td>{{ directory.patientName(a.patient_id) }}</td> }

                    @if (mode() !== 'doctor') { <td>{{ directory.doctorName(a.doctor_id) }}</td> }

                    @if (mode() !== 'doctor')  { <td>{{ directory.doctorName(a.doctor_id) }}</td> }

                    <td>{{ a.reason || '—' }}</td>
                    <td><span class="badge" [attr.data-status]="a.status">{{ label(a.status) }}</span></td>
                    <td class="right">
                      @if (mode() === 'doctor' && a.status === 'PENDING') {
                        <button type="button" class="btn sm" (click)="setStatus(a, 'CONFIRMED')">Confirmer</button>
                      }
                      @if ((mode() === 'doctor' || mode() === 'secretary') && a.status === 'CONFIRMED') {
                        <button type="button" class="btn sm" (click)="setStatus(a, 'COMPLETED')">Terminé</button>
                        <button type="button" class="btn sm" (click)="setStatus(a, 'NO_SHOW')">Absent</button>
                      }
                      @if (mode() === 'secretary' && a.status === 'PENDING') {
                        <button type="button" class="btn sm" (click)="setStatus(a, 'CONFIRMED')">Confirmer</button>
                      }
                      @if (canCancel(a)) {
                        <button type="button" class="btn sm danger" (click)="cancel(a)">Annuler</button>
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="pager">
            <span class="muted">{{ total() }} rendez-vous</span>
            <span>
              <button type="button" class="btn sm" [disabled]="page() <= 1" (click)="reload(page() - 1)">‹</button>
              Page {{ page() }}
              <button type="button" class="btn sm" [disabled]="page() * SIZE >= total()" (click)="reload(page() + 1)">›</button>
            </span>
          </div>
        }
      </section>
    </div>
  `,
})
export class AppointmentView implements OnInit {
  private readonly api       = inject(AppointmentsApi);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly confirm = inject(ConfirmService);
  private readonly cdr = inject(ChangeDetectorRef);

  // On initialise le mode à 'patient' par défaut, puis on le met à jour dans ngOnInit
  readonly mode = signal<ViewMode>('patient');

  readonly SIZE = 10;
  readonly statuses: AppointmentStatus[] = ['PENDING', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW'];

  readonly items = signal<Appointment[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly searching = signal(false);
  readonly booking = signal(false);
  readonly result = signal<ParseResult | null>(null);
  readonly stats = signal<StatsData | null>(null);
  readonly doctors = signal<DoctorOption[]>([]);

  statusFilter: AppointmentStatus | '' = '';
  doctorFilter = '';
  patientFilter = '';
  dateFrom = '';
  dateTo = '';
  readonly message = signal('');
  patientId = '';

  readonly canBook = computed(() => this.mode() === 'patient' || this.mode() === 'secretary');
  readonly subtitle = computed(() => ({
    patient: 'Demandez un rendez-vous en une phrase et choisissez un créneau',
    secretary: 'Planifiez et suivez les rendez-vous de la clinique',
    admin: 'Supervision des rendez-vous de la clinique',
    doctor: 'Votre agenda et vos consultations',
  }[this.mode()]));

  ngOnInit(): void {
    // Récupérer le rôle de l'utilisateur connecté et le mettre à jour
    const userRole = this.auth.user()?.role?.toLowerCase();
    if (userRole && ['patient', 'secretary', 'admin', 'doctor'].includes(userRole)) {
      this.mode.set(userRole as ViewMode);
      this.cdr.detectChanges(); // Force la mise à jour de la vue
    }
       this.directory.loadDoctors().subscribe(doctors => this.doctors.set(doctors));
    if (this.mode() === 'admin') {
      this.refreshStats();
    }
    // Charger les médecins pour afficher leurs noms
    this.directory.loadDoctors().subscribe();
    this.reload(1);
  }

  hasFilters(): boolean {
    return !!(this.doctorFilter || this.patientFilter || this.dateFrom || this.dateTo);
  }

  resetFilters(picker: PatientPicker): void {
    this.doctorFilter = '';
    this.patientFilter = '';
    this.dateFrom = '';
    this.dateTo = '';
    picker.clear(); // émet « aucun patient » et recharge la liste
  }

  onPatientFilter(patient: PatientOption | null): void {
    this.patientFilter = patient?.id ?? '';
    this.reload(1);
  }

  onPatientPicked(patient: PatientOption | null): void {
    this.patientId = patient?.id ?? '';
    this.result.set(null);
    if (this.mode() === 'secretary') {
      // Le tableau n'affiche que les rendez-vous du patient choisi
      this.patientFilter = this.patientId;
      this.reload(1);
    }
  }

  /** Chiffres par statut + rendez-vous des 14 jours autour d'aujourd'hui. */
  private refreshStats(): void {
    const today = clinicDay(new Date());
    const base = new Date(`${today}T00:00:00+01:00`).getTime();
    const from = new Date(base - 6 * DAY_MS);
    const to = new Date(base + 8 * DAY_MS);
    forkJoin({ counts: this.api.counts(), items: this.api.window(from.toISOString(), to.toISOString()) }).subscribe({
      next: ({ counts, items }) => {
        const perDay = Array.from({ length: 14 }, (_, i) => {
          const date = new Date(from.getTime() + i * DAY_MS);
          const day = clinicDay(date);
          const count = items.filter(a => a.status !== 'CANCELLED' && clinicDay(new Date(a.start_at)) === day).length;
          return { day, label: day.slice(8), count, today: day === today };
        });
        this.stats.set({ counts, perDay });
      },
      error: () => this.stats.set(null),
    });
  }

  label(s: AppointmentStatus): string {
    return STATUS_LABELS[s];
  }

  canCancel(a: Appointment): boolean {
    return a.status === 'PENDING' || a.status === 'CONFIRMED';
  }

  reload(page: number): void {
    this.loading.set(true);
    this.error.set('');
    this.api.list({
      status: this.statusFilter,
      patient_id: this.patientFilter,
      doctor_id: this.doctorFilter,
      date_from: this.dateFrom ? new Date(`${this.dateFrom}T00:00:00+01:00`).toISOString() : undefined,
      date_to: this.dateTo ? new Date(new Date(`${this.dateTo}T00:00:00+01:00`).getTime() + DAY_MS).toISOString() : undefined,
      page,
      page_size: this.SIZE,
    }).subscribe({
      next: p => {
        this.items.set(p.items);
        if (this.mode() !== 'patient') this.directory.resolvePatients(p.items.map(a => a.patient_id));
        this.total.set(p.total);
        this.page.set(p.page);
        this.loading.set(false);
        // Résoudre les noms des patients et médecins
        this.directory.resolvePatients(p.items.map(a => a.patient_id));
      },
      error: e => {
        this.error.set(apiErrorMessage(e));
        this.loading.set(false);
      },
    });
  }

  search(): void {
    if (this.mode() === 'secretary' && !this.patientId.trim()) {
      this.toast.show('Indiquez l’ID du patient.', 'error');
      return;
    }
    this.searching.set(true);
    this.result.set(null);
    this.api.parseRequest(this.message().trim(), this.patientId.trim()).subscribe({
      next: r => {
        this.result.set(r);
        this.searching.set(false);
      },
      error: e => {
        this.toast.show(apiErrorMessage(e), 'error');
        this.searching.set(false);
      },
    });
  }

  book(r: ParseResult, slot: Slot): void {
    const patient = this.mode() === 'patient' ? (this.auth.user()?.patient_id ?? '') : this.patientId.trim();
    if (!patient) {
      this.toast.show('Aucun dossier patient associé à ce compte.', 'error');
      return;
    }
    this.booking.set(true);
    this.api.create({
      patient_id: patient,
      doctor_id: slot.doctor_id,
      start_at: slot.start_at,
      end_at: slot.end_at,
      reason: r.parsed.reason,
      request_id: r.request_id,
    }).subscribe({
      next: () => {
        this.toast.show('Rendez-vous créé.');
        this.booking.set(false);
        this.result.set(null);
        this.message.set('');
        this.reload(1);
      },
      error: e => {
        this.toast.show(apiErrorMessage(e), 'error');
        this.booking.set(false);
        this.search(); // le créneau a pu être pris entre-temps : on rafraîchit la liste
      },
    });
  }

  setStatus(a: Appointment, status: AppointmentStatus): void {
    this.api.update(a.id, { status }).subscribe({
      next: () => {
        this.toast.show('Statut mis à jour.');
        this.reload(this.page());
        if (this.mode() === 'admin') this.refreshStats();
      },
      error: e => this.toast.show(apiErrorMessage(e), 'error'),
    });
  }

  async cancel(a: Appointment): Promise<void> {
    const ok = await this.confirm.ask({
      title: 'Annuler le rendez-vous',
      message: 'Voulez-vous vraiment annuler ce rendez-vous ?',
      confirmLabel: 'Annuler le rendez-vous',
      cancelLabel: 'Retour',
      danger: true,
    });
    if (!ok) return;
    this.api.cancel(a.id, null).subscribe({
      next: () => {
        this.toast.show('Rendez-vous annulé.');
        this.reload(this.page());
        if (this.mode() === 'admin') this.refreshStats();
      },
      error: e => this.toast.show(apiErrorMessage(e), 'error'),
    });
  }
}