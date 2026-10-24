import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';
import { parseIsoDate, todayIso, yearsBefore } from './birth-date';

/**
 * Same rules as backend/app/modules/patients/schemas.py. Each error's value is
 * its French message, so templates just show `firstError(control)`.
 */

export const MAX_AGE_YEARS = 130;

function text(control: AbstractControl): string {
  return String(control.value ?? '').trim();
}

export const requiredText: ValidatorFn = control =>
  text(control) ? null : { required: 'Ce champ est obligatoire.' };

export function maxLength(limit: number): ValidatorFn {
  return control =>
    text(control).length > limit ? { maxlength: `${limit} caractères maximum.` } : null;
}

function pattern(regex: RegExp, key: string, message: string): ValidatorFn {
  return control => {
    const value = text(control);
    return value && !regex.test(value) ? { [key]: message } : null;
  };
}

export const nationalId = pattern(
  /^[0-9]{8}$/,
  'nationalId',
  'Le CIN doit contenir exactement 8 chiffres.',
);
export const phone = pattern(
  /^[0-9 +]{8,20}$/,
  'phone',
  'Téléphone invalide : 8 à 20 caractères (chiffres, espaces, +).',
);
export const email = pattern(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, 'email', 'Adresse email invalide.');

/** 'YYYY-MM-DD' strings compare like dates. */
export const birthDate: ValidatorFn = control => {
  const value = text(control);
  if (!value) return null;
  if (!parseIsoDate(value)) return { date: 'Date invalide.' };
  const today = todayIso();
  if (value > today) return { future: 'La date de naissance ne peut pas être dans le futur.' };
  if (value < yearsBefore(today, MAX_AGE_YEARS)) {
    return { tooOld: `La date de naissance ne peut pas remonter à plus de ${MAX_AGE_YEARS} ans.` };
  }
  return null;
};

export function firstError(errors: ValidationErrors | null): string | null {
  if (!errors) return null;
  const message = Object.values(errors)[0];
  return typeof message === 'string' ? message : 'Valeur invalide.';
}
