import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService, ROLE_LABELS, Role } from '../../core/auth/auth.service';
import { BILLING_ROLES } from '../../features/billing/billing.model';
import { PATIENT_ROLES } from '../../features/patients/patient-permissions';
import { Icon } from '../icon/icon';

interface NavItem {
  label: string;
  route: string;
  icon: string;
  dot?: string;
  /** Only shown to these roles; visible to everyone when omitted. */
  roles?: readonly Role[];
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Tableau de bord',       route: '/dashboard',           icon: 'home'        },
  { label: 'Appointment Manager',   route: '/appointment-manager', icon: 'calendar',   dot: '#0284c7' },
  { label: 'Patients',              route: '/patients',            icon: 'users',      dot: '#d97706', roles: PATIENT_ROLES.read },
  { label: 'Facturation',           route: '/billing',             icon: 'bar-chart',  dot: '#0f766e', roles: BILLING_ROLES.manage },
  { label: 'ReportWriter',          route: '/report-writer',       icon: 'file-text',  dot: '#7c3aed' },
  { label: 'MedDoc',                route: '/med-doc',             icon: 'file-plus',  dot: '#16a34a' },
  { label: 'FollowUp',              route: '/follow-up',           icon: 'bell',       dot: '#d97706' },
  { label: 'ClinicFAQ',             route: '/clinic-faq',          icon: 'help-circle',dot: '#9333ea' },
];

@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Icon],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  protected auth = inject(AuthService);
  private router = inject(Router);

  sidebarOpen = signal(false);
  navItems = computed(() => {
    const role = this.auth.user()?.role;
    return NAV_ITEMS.filter(item => !item.roles || (role !== undefined && item.roles.includes(role)));
  });

  get user() { return this.auth.user(); }

  get initials(): string {
    const u = this.user;
    if (!u) return '?';
    return (u.first_name[0] ?? '') + (u.last_name[0] ?? '');
  }

  roleLabel(role: Role | string): string {
    return ROLE_LABELS[role as Role] ?? role;
  }

  currentTitle(): string {
    const item = NAV_ITEMS.find(n => this.router.url.startsWith(n.route));
    return item?.label ?? 'MediFlow AI';
  }

  logout() { this.auth.logout(); }

  toggle() { this.sidebarOpen.update(v => !v); }
  close()  { this.sidebarOpen.set(false); }
}
