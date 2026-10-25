import { Component, computed, inject } from '@angular/core';
import { AuthService } from '../../core/auth/auth.service';
import { PendingAppointments } from '../../features/appointments/pending-appointments';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-appointment-manager',
  imports: [Icon, PendingAppointments],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#e0f2fe;color:#0284c7">
          <app-icon name="calendar" [size]="24" />
        </div>
        <div>
          <h1>Appointment Manager AI</h1>
          <p>Rendez-vous et disponibilités</p>
        </div>
      </div>
      @if (canConfirm()) {
        <!-- Requests booked from the patient portal (/api/appointments). -->
        <app-pending-appointments />
      }
      <div class="coming-soon">
        <app-icon name="calendar" [size]="40" />
        <h2>Module en cours de développement</h2>
        <p>La gestion des rendez-vous sera disponible prochainement.</p>
      </div>
    </div>
  `,
  styleUrl: './appointment-manager.scss',
})
export class AppointmentManager {
  private auth = inject(AuthService);
  protected canConfirm = computed(() => ['SECRETARY', 'ADMIN'].includes(this.auth.user()?.role ?? ''));
}
