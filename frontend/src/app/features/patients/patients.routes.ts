import { Routes } from '@angular/router';
import { PatientsLayout } from './patients-layout/patients-layout';

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
    ],
  },
];
