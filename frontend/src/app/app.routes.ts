import { Routes } from '@angular/router';

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
    loadComponent: () => import('./pages/login/login').then(m => m.Login),
  },
  {
    path: 'signup',
    title: 'Créer un compte · MediFlow AI',
    loadComponent: () => import('./pages/signup/signup').then(m => m.Signup),
  },
  { path: '**', redirectTo: '' },
];
