/** Shapes of the /api/patients JSON (camelCase). Dates of birth are 'YYYY-MM-DD' strings. */

export type Gender = 'MALE' | 'FEMALE' | 'OTHER';
export const GENDERS: readonly Gender[] = ['MALE', 'FEMALE', 'OTHER'];
export const GENDER_LABELS: Record<Gender, string> = {
  MALE: 'Homme',
  FEMALE: 'Femme',
  OTHER: 'Autre',
};

export const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'] as const;
export type BloodType = (typeof BLOOD_TYPES)[number];

/** Suggestions for the city fields (any city is accepted). */
export const CITIES = [
  'Tunis',
  'Ariana',
  'Ben Arous',
  'La Manouba',
  'Bizerte',
  'Nabeul',
  'Sousse',
  'Monastir',
  'Mahdia',
  'Sfax',
  'Kairouan',
  'Gabès',
  'Médenine',
  'Gafsa',
  'Kasserine',
  'Béja',
  'Jendouba',
];

export interface Address {
  street: string | null;
  city: string | null;
  postalCode: string | null;
}

export interface Insurance {
  provider: string | null;
  number: string | null;
}

export interface EmergencyContact {
  name: string | null;
  phone: string | null;
  relation: string | null;
}

/** Fields a client may write (POST body; a PATCH sends a subset). */
export interface PatientPayload {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  gender: Gender;
  nationalId: string | null;
  phone: string | null;
  email: string | null;
  address: Address | null;
  bloodType: BloodType | null;
  insurance: Insurance | null;
  emergencyContact: EmergencyContact | null;
  administrativeNotes: string | null;
}

export interface Patient extends PatientPayload {
  id: string;
  recordNumber: string;
  age: number;
  currentSummaryId: string | null;
  createdBy: string | null;
  updatedBy: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PatientListItem {
  id: string;
  recordNumber: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  age: number;
  gender: Gender;
  phone: string | null;
  city: string | null;
}

export interface DeletedPatientItem extends PatientListItem {
  deletedAt: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export type SortKey = 'lastName' | 'createdAt' | 'recordNumber' | 'dateOfBirth';
export const SORT_KEYS: readonly SortKey[] = [
  'lastName',
  'createdAt',
  'recordNumber',
  'dateOfBirth',
];
/** `-key` sorts descending. */
export type Sort = SortKey | `-${SortKey}`;

export interface PatientQuery {
  q?: string;
  gender?: Gender;
  bloodType?: BloodType;
  city?: string;
  page?: number;
  size?: number;
  sort?: Sort;
}

/** One entry of a 422 `detail` list. */
export interface FieldError {
  loc: (string | number)[];
  msg: string;
}
