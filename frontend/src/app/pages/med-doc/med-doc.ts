import { Component } from '@angular/core';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-med-doc',
  imports: [Icon],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#dcfce7;color:#16a34a">
          <app-icon name="file-plus" [size]="24" />
        </div>
        <div>
          <h1>MedDoc AI</h1>
          <p>Documents et extraction de champs</p>
        </div>
      </div>
      <div class="coming-soon">
        <app-icon name="file-plus" [size]="40" />
        <h2>Module en cours de développement</h2>
        <p>La gestion documentaire sera disponible prochainement.</p>
      </div>
    </div>
  `,
  styleUrl: './med-doc.scss',
})
export class MedDoc {}
