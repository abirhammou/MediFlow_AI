import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService, apiErrorMessage } from '../../core/auth/auth.service';
import { ConfirmService } from '../../shared/confirm-dialog/confirm.service';
import { Icon } from '../../shared/icon/icon';
import { ToastService } from '../../shared/toast/toast.service';
import {
  Appointment, AppointmentStatus, AppointmentsApi, ParseResult, STATUS_LABELS, Slot,
} from './appointments.api';

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
  imports: [Icon, FormsModule, DatePipe],
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
            <label class="f"><span>ID du patient</span>
              <input type="text" [(ngModel)]="patientId" placeholder="24 caractères (ObjectId)" /></label>
          }
          <label class="f"><span>Demande</span>
            <textarea rows="3" [(ngModel)]="message" maxlength="2000" placeholder="Ex. Rendez-vous demain après-midi pour un contrôle"></textarea></label>
          <button type="button" class="btn primary" [disabled]="searching() || !message.trim()" (click)="search()">
            ✨ {{ searching() ? 'Recherche…' : 'Trouver des créneaux' }}
          </button>

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

      <section class="card">
        <div class="head">
          <h2>{{ mode() === 'patient' ? 'Mes rendez-vous' : mode() === 'doctor' ? 'Mon agenda' : 'Rendez-vous' }}</h2>
          <select [(ngModel)]="statusFilter" (ngModelChange)="reload(1)">
            <option value="">Tous les statuts</option>
            @for (s of statuses; track s) { <option [value]="s">{{ label(s) }}</option> }
          </select>
        </div>

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
                    @if (mode() !== 'patient') { <td class="mono">{{ a.patient_id }}</td> }
                    @if (mode() !== 'doctor') { <td class="mono">{{ a.doctor_id }}</td> }
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
  readonly mode = input.required<ViewMode>();

  private readonly api = inject(AppointmentsApi);
  private readonly auth = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly confirm = inject(ConfirmService);

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

  statusFilter: AppointmentStatus | '' = '';
  message = '';
  patientId = '';

  readonly canBook = computed(() => this.mode() === 'patient' || this.mode() === 'secretary');
  readonly subtitle = computed(() => ({
    patient: 'Demandez un rendez-vous en une phrase et choisissez un créneau',
    secretary: 'Planifiez et suivez les rendez-vous de la clinique',
    admin: 'Supervision des rendez-vous de la clinique',
    doctor: 'Votre agenda et vos consultations',
  }[this.mode()]));

  ngOnInit(): void {
    this.reload(1);
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
    this.api.list({ status: this.statusFilter, page, page_size: this.SIZE }).subscribe({
      next: p => {
        this.items.set(p.items);
        this.total.set(p.total);
        this.page.set(p.page);
        this.loading.set(false);
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
    this.api.parseRequest(this.message.trim(), this.patientId.trim()).subscribe({
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
        this.message = '';
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
      },
      error: e => this.toast.show(apiErrorMessage(e), 'error'),
    });
  }
}
