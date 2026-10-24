import { Component } from '@angular/core';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-patient-records',
  imports: [Icon],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#fef3c7;color:#d97706">
          <app-icon name="users" [size]="24" />
        </div>
        <div>
          <h1>Patient Records AI</h1>
          <p>Dossiers administratifs des patients</p>
        </div>
      </div>
      <div class="coming-soon">
        <app-icon name="users" [size]="40" />
        <h2>Module en cours de développement</h2>
        <p>La gestion des dossiers patients sera disponible prochainement.</p>
      </div>
    </div>
  `,
  styleUrl: './patient-records.scss',
})
export class PatientRecords {}
