/** Shapes of the /api/patients/{id}/files JSON (camelCase). */

export type FileCategory = 'ADMINISTRATIVE' | 'MEDICAL';
export type FileType =
  | 'INSURANCE'
  | 'ACCOUNT'
  | 'INVOICE'
  | 'BILL'
  | 'SCAN'
  | 'LAB_RESULT'
  | 'IMAGING'
  | 'OTHER';
export type ExtractionStatus = 'DONE' | 'EMPTY' | 'FAILED' | 'UNAVAILABLE';

export const FILE_CATEGORY_LABELS: Record<FileCategory, string> = {
  ADMINISTRATIVE: 'Administratif',
  MEDICAL: 'Médical',
};

export const FILE_TYPE_LABELS: Record<FileType, string> = {
  INSURANCE: 'Assurance',
  ACCOUNT: 'Compte',
  INVOICE: 'Facture',
  BILL: 'Note de frais',
  SCAN: 'Scan',
  LAB_RESULT: 'Résultat de laboratoire',
  IMAGING: 'Imagerie',
  OTHER: 'Autre',
};

/** Types offered first in the upload form, per category (any type stays allowed). */
export const TYPES_BY_CATEGORY: Record<FileCategory, FileType[]> = {
  ADMINISTRATIVE: ['INSURANCE', 'ACCOUNT', 'INVOICE', 'BILL', 'OTHER'],
  MEDICAL: ['SCAN', 'LAB_RESULT', 'IMAGING', 'OTHER'],
};

/** Same limits as the backend (storage.py): PDF, PNG, JPEG, 10 MB. */
export const ACCEPTED_FILES = 'application/pdf,image/png,image/jpeg';
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export interface PatientFile {
  id: string;
  patientId: string;
  category: FileCategory;
  type: FileType;
  title: string;
  originalName: string;
  mime: 'application/pdf' | 'image/png' | 'image/jpeg';
  size: number;
  sha256: string;
  extractionStatus: ExtractionStatus | null;
  hasText: boolean;
  uploadedBy: string | null;
  uploadedByName: string | null;
  createdAt: string;
}

export interface FileUpload {
  file: File;
  category: FileCategory;
  type: FileType;
  title: string;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} Mo`;
}

/** Saves a blob fetched through HttpClient (the token stays in the Authorization header). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

const EXTENSIONS: Record<PatientFile['mime'], string> = {
  'application/pdf': '.pdf',
  'image/png': '.png',
  'image/jpeg': '.jpg',
};

export function downloadName(file: Pick<PatientFile, 'title' | 'mime'>): string {
  const slug =
    file.title
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/gi, '-')
      .replace(/^-|-$/g, '')
      .toLowerCase() || 'document';
  return slug + EXTENSIONS[file.mime];
}
