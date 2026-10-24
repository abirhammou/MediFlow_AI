import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService, ROLE_LABELS, Role } from '../../core/auth/auth.service';
import { Icon } from '../icon/icon';

interface NavItem {
  label: string;
  route: string;
  icon: string;
  dot?: string;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Tableau de bord',       route: '/dashboard',           icon: 'home'        },
  { label: 'Appointment Manager',   route: '/appointment-manager', icon: 'calendar',   dot: '#0284c7' },
  { label: 'Patient Records',       route: '/patient-records',     icon: 'users',      dot: '#d97706' },
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
  navItems = NAV_ITEMS;

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
