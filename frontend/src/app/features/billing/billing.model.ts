import { Role } from '../../core/auth/auth.service';

/** Shapes of /api/billing (camelCase). Every amount is an integer in millimes (1 TND = 1000). */

export type InvoiceStatus = 'DRAFT' | 'ISSUED' | 'PARTIAL' | 'PAID' | 'CANCELLED';
export type PaymentMethod = 'CASH' | 'CARD' | 'TRANSFER' | 'CHEQUE';

/** Same matrix as BILLING_ROLES in backend/app/modules/billing/service.py. */
export const BILLING_ROLES = {
  manage: ['ADMIN', 'SECRETARY'],
  read: ['ADMIN', 'SECRETARY', 'PATIENT'],
} as const satisfies Record<string, readonly Role[]>;

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  DRAFT: 'Brouillon',
  ISSUED: 'À régler',
  PARTIAL: 'Partiellement réglée',
  PAID: 'Réglée',
  CANCELLED: 'Annulée',
};

export const PAYMENT_METHOD_LABELS: Record<PaymentMethod, string> = {
  CASH: 'Espèces',
  CARD: 'Carte bancaire',
  TRANSFER: 'Virement',
  CHEQUE: 'Chèque',
};

export interface InvoiceLine {
  label: string;
  quantity: number;
  unitPrice: number;
  amount: number;
}

export interface Payment {
  id: string;
  invoiceId: string;
  invoiceNumber: string | null;
  amount: number; // < 0 for a refund
  method: PaymentMethod;
  receiptNumber: string;
  refundOf: string | null;
  refundedAmount: number;
  refundable: number;
  note: string | null;
  createdByName: string | null;
  createdAt: string;
}

export interface Invoice {
  id: string;
  number: string;
  patientId: string;
  patientName: string | null;
  recordNumber: string | null;
  lines: InvoiceLine[];
  total: number;
  insuranceShare: number;
  patientShare: number;
  paidAmount: number;
  balance: number;
  status: InvoiceStatus;
  appointmentId: string | null;
  followupTaskId: string | null;
  note: string | null;
  issuedAt: string | null;
  cancelledAt: string | null;
  cancelReason: string | null;
  createdAt: string;
  updatedAt: string;
  payments: Payment[];
}

export interface InvoicePage {
  items: Invoice[];
  total: number;
  page: number;
  size: number;
}

export interface InvoiceDraft {
  patientId: string;
  lines: { label: string; quantity: number; unitPrice: number }[];
  insuranceShare: number;
  note: string | null;
}

export interface RevenueRow {
  period: string;
  payments: number;
  collected: number;
  refunded: number;
  net: number;
  byMethod: Partial<Record<PaymentMethod, number>>;
}

export interface RevenueReport {
  from: string;
  to: string;
  groupBy: 'day' | 'month';
  rows: RevenueRow[];
  collected: number;
  refunded: number;
  net: number;
}

export interface UnpaidReport {
  items: Invoice[];
  count: number;
  outstanding: number;
}

/** 45500 -> "45,500 TND" (same format as the backend PDFs). */
export function formatTnd(millimes: number): string {
  const sign = millimes < 0 ? '-' : '';
  const value = Math.abs(Math.round(millimes));
  const dinars = Math.floor(value / 1000)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${sign}${dinars},${String(value % 1000).padStart(3, '0')} TND`;
}

/** "45,5" / "45.500" / "45" -> 45500 millimes; null when not a valid amount. */
export function parseTnd(input: string): number | null {
  const text = input.replace(/\s|TND/gi, '').replace(',', '.');
  if (!/^\d+(\.\d{1,3})?$/.test(text)) return null;
  const [dinars, decimals = ''] = text.split('.');
  return Number(dinars) * 1000 + Number(decimals.padEnd(3, '0'));
}

/** Millimes as an editable "45,500" string. */
export function tndInput(millimes: number): string {
  return formatTnd(millimes).replace(' TND', '').replace(/ /g, '');
}
