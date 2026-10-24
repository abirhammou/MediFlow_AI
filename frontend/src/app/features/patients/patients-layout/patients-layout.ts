import { Component, ViewEncapsulation, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService, ROLE_LABELS } from '../../../core/auth/auth.service';
import { Icon } from '../../../shared/icon/icon';
import { Logo } from '../../../shared/logo/logo';
import { PatientPermissions } from '../patient-permissions';

/**
 * Top bar + outlet for every /patients page. Its stylesheet holds the styles of
 * the whole feature, scoped under `.patients-area` (no view encapsulation).
 */
@Component({
  selector: 'app-patients-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Logo, Icon],
  templateUrl: './patients-layout.html',
  styleUrl: './patients-layout.scss',
  encapsulation: ViewEncapsulation.None,
})
export class PatientsLayout {
  protected auth = inject(AuthService);
  protected perms = inject(PatientPermissions);
  protected roleLabels = ROLE_LABELS;
}
