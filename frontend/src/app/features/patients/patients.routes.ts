import { Routes } from '@angular/router';
import { roleGuard } from '../../core/auth/auth.guard';
import { PATIENT_ROLES } from './patient-permissions';
import { PatientsLayout } from './patients-layout/patients-layout';
import { unsavedChangesGuard } from './unsaved-changes.guard';

/** Mounted under /patients; the parent route already checks PATIENT_ROLES.read. */
export const PATIENT_ROUTES: Routes = [
  {
    path: '',
    component: PatientsLayout,
    children: [
      {
        path: '',
        title: 'Patients · MediFlow AI',
        loadComponent: () => import('./patient-list/patient-list').then(m => m.PatientList),
      },
      {
        path: 'new',
        title: 'Nouveau patient · MediFlow AI',
        canActivate: [roleGuard(PATIENT_ROLES.write)],
        canDeactivate: [unsavedChangesGuard],
        loadComponent: () => import('./patient-form/patient-form').then(m => m.PatientForm),
      },
      {
        path: ':id/edit',
        title: 'Modifier le dossier · MediFlow AI',
        canActivate: [roleGuard(PATIENT_ROLES.write)],
        canDeactivate: [unsavedChangesGuard],
        loadComponent: () => import('./patient-form/patient-form').then(m => m.PatientForm),
      },
    ],
  },
];
