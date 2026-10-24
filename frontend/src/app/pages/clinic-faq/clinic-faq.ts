import { Component } from '@angular/core';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-clinic-faq',
  imports: [Icon],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#f3e8ff;color:#9333ea">
          <app-icon name="help-circle" [size]="24" />
        </div>
        <div>
          <h1>ClinicFAQ AI</h1>
          <p>Réponses aux questions courantes</p>
        </div>
      </div>
      <div class="coming-soon">
        <app-icon name="help-circle" [size]="40" />
        <h2>Module en cours de développement</h2>
        <p>La FAQ intelligente sera disponible prochainement.</p>
      </div>
    </div>
  `,
  styleUrl: './clinic-faq.scss',
})
export class ClinicFaq {}
