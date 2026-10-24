import { Component, ViewEncapsulation, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { PatientPermissions } from '../patient-permissions';

/**
 * Sub-navigation + outlet for every /patients page, rendered inside the app shell.
 * Its stylesheet holds the styles of the whole feature, scoped under `.patients-area`
 * (no view encapsulation).
 */
@Component({
  selector: 'app-patients-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './patients-layout.html',
  styleUrl: './patients-layout.scss',
  encapsulation: ViewEncapsulation.None,
})
export class PatientsLayout {
  protected perms = inject(PatientPermissions);
}
