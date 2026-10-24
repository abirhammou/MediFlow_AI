import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/auth/auth.guard';

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
  { path: '**', redirectTo: '' },
];
