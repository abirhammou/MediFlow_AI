import { Component } from '@angular/core';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-report-writer',
  imports: [Icon],
  template: `
    <div class="module-page">
      <div class="module-header">
        <div class="module-icon" style="background:#ede9fe;color:#7c3aed">
          <app-icon name="file-text" [size]="24" />
        </div>
        <div>
          <h1>ReportWriter AI</h1>
          <p>Comptes rendus structurés</p>
        </div>
      </div>
      <div class="coming-soon">
        <app-icon name="file-text" [size]="40" />
        <h2>Module en cours de développement</h2>
        <p>La rédaction de comptes rendus sera disponible prochainement.</p>
      </div>
    </div>
  `,
  styleUrl: './report-writer.scss',
})
export class ReportWriter {}
