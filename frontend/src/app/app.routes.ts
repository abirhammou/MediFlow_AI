import { Routes } from '@angular/router';
import { authGuard, guestGuard, passwordChangeGuard, roleGuard } from './core/auth/auth.guard';
import { BILLING_ROLES } from './features/billing/billing.model';
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

  {
    path: 'change-password',
    title: 'Changer de mot de passe · MediFlow AI',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/change-password/change-password').then(m => m.ChangePassword),
  },

  // ── Authenticated shell (sidebar + topbar) ─────────────────────────
  {
    path: '',
    canActivate: [authGuard, passwordChangeGuard],
    loadComponent: () => import('./shared/shell/shell').then(m => m.Shell),
    children: [
      // Patient portal (PATIENT only; every call is scoped to their own record by the API)
      {
        path: 'portal',
        canActivate: [roleGuard(['PATIENT'])],
        children: [
          {
            path: '',
            title: 'Mon dossier · MediFlow AI',
            loadComponent: () => import('./features/portal/portal-home').then(m => m.PortalHome),
          },
          {
            path: 'appointments',
            title: 'Mes rendez-vous · MediFlow AI',
            loadComponent: () => import('./features/portal/portal-appointments').then(m => m.PortalAppointments),
          },
          {
            path: 'follow-ups',
            title: 'Mon suivi · MediFlow AI',
            loadComponent: () => import('./features/portal/portal-follow-ups').then(m => m.PortalFollowUps),
          },
          {
            path: 'invoices',
            title: 'Mes factures · MediFlow AI',
            loadComponent: () => import('./features/portal/portal-invoices').then(m => m.PortalInvoices),
          },
        ],
      },
      {
        path: 'dashboard',
        title: 'Tableau de bord · MediFlow AI',
        loadComponent: () => import('./pages/dashboard/dashboard').then(m => m.Dashboard),
      },
         {
        path: 'appointment-manager',
        title: 'Appointment Manager AI · MediFlow AI',
        loadComponent: () => import('./pages/appointment-manager/appointment-view').then(m => m.AppointmentView),
      },  
      {
        path: 'patients',
        canActivate: [roleGuard(PATIENT_ROLES.read)],
        loadChildren: () => import('./features/patients/patients.routes').then(m => m.PATIENT_ROUTES),
      },
      {
        path: 'billing',
        title: 'Facturation · MediFlow AI',
        canActivate: [roleGuard(BILLING_ROLES.manage)],
        loadComponent: () => import('./features/billing/billing-page/billing-page').then(m => m.BillingPage),
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
