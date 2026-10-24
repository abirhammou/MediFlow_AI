import { Routes } from '@angular/router';
import { authGuard, guestGuard, roleGuard } from './core/auth/auth.guard';
import { PATIENT_ROLES } from './features/patients/patient-permissions';

export const routes: Routes = [
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
    path: 'dashboard',
    title: 'Tableau de bord · MediFlow AI',
    canActivate: [authGuard],
    loadComponent: () => import('./pages/dashboard/dashboard').then(m => m.Dashboard),
  },
  {
    path: 'patients',
    canActivate: [authGuard, roleGuard(PATIENT_ROLES.read)],
    loadChildren: () => import('./features/patients/patients.routes').then(m => m.PATIENT_ROUTES),
  },
  { path: '**', redirectTo: '' },
];
