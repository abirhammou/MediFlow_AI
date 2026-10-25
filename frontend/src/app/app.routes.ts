import { Routes } from '@angular/router';
import { authGuard, guestGuard, roleGuard } from './core/auth/auth.guard';
import { PATIENT_ROLES } from './features/patients/patient-permissions';

export const routes: Routes = [
  // ── Public pages ──────────────────────────────────────────────────
  {
    path: '',
    pathMatch: 'full',
    title: 'MediFlow AI',
    loadComponent: () => import('./pages/landing/landing').then(m => m.Landing),
  },
  {
    path: 'login',
    title: 'Se connecter · MediFlow AI',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/login/login').then(m => m.Login),
  },
  {
    path: 'signup',
    title: 'Créer un compte · MediFlow AI',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/signup/signup').then(m => m.Signup),
  },

  // ── Authenticated shell (sidebar + topbar) ─────────────────────────
  {
    path: '',
    canActivate: [authGuard],
    loadComponent: () => import('./shared/shell/shell').then(m => m.Shell),
    children: [
      {
        path: 'dashboard',
        title: 'Tableau de bord · MediFlow AI',
        loadComponent: () => import('./pages/dashboard/dashboard').then(m => m.Dashboard),
      },
      {
        path: 'appointment-manager',
        title: 'Appointment Manager AI · MediFlow AI',
        loadComponent: () => import('./pages/appointment-manager/appointment-manager').then(m => m.AppointmentManager),
      },
      {
        path: 'patients',
        canActivate: [roleGuard(PATIENT_ROLES.read)],
        loadChildren: () => import('./features/patients/patients.routes').then(m => m.PATIENT_ROUTES),
      },
      {
        path: 'report-writer',
        title: 'ReportWriter AI · MediFlow AI',
        loadComponent: () => import('./pages/report-writer/report-writer').then(m => m.ReportWriter),
      },
      {
        path: 'med-doc',
        title: 'MedDoc AI · MediFlow AI',
        canActivate: [roleGuard(['DOCTOR', 'SECRETARY', 'ADMIN_STAFF', 'ADMIN', 'PATIENT'])],
        loadComponent: () => import('./pages/med-doc/med-doc').then(m => m.MedDoc),
      },
      {
        path: 'follow-up',
        title: 'FollowUp AI · MediFlow AI',
        loadComponent: () => import('./pages/follow-up/follow-up').then(m => m.FollowUp),
      },
      {
        path: 'clinic-faq',
        title: 'ClinicFAQ AI · MediFlow AI',
        loadComponent: () => import('./pages/clinic-faq/clinic-faq').then(m => m.ClinicFaq),
      },
    ],
  },

  { path: '**', redirectTo: '' },
];
