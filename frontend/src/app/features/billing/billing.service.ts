import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Invoice,
  InvoiceDraft,
  InvoicePage,
  InvoiceStatus,
  PaymentMethod,
  RevenueReport,
  UnpaidReport,
} from './billing.model';

const BASE = '/api/billing';

export interface InvoiceQuery {
  patientId?: string;
  status?: InvoiceStatus | '';
  number?: string;
  page: number;
  size: number;
}

@Injectable({ providedIn: 'root' })
export class BillingService {
  private http = inject(HttpClient);

  list(query: InvoiceQuery): Observable<InvoicePage> {
    let params = new HttpParams().set('page', query.page).set('size', query.size);
    if (query.patientId) params = params.set('patientId', query.patientId);
    if (query.status) params = params.set('status', query.status);
    if (query.number?.trim()) params = params.set('number', query.number.trim());
    return this.http.get<InvoicePage>(`${BASE}/invoices`, { params });
  }

  get(id: string): Observable<Invoice> {
    return this.http.get<Invoice>(`${BASE}/invoices/${encodeURIComponent(id)}`);
  }

  create(draft: InvoiceDraft): Observable<Invoice> {
    return this.http.post<Invoice>(`${BASE}/invoices`, draft);
  }

  update(id: string, draft: Omit<InvoiceDraft, 'patientId'>): Observable<Invoice> {
    return this.http.patch<Invoice>(`${BASE}/invoices/${encodeURIComponent(id)}`, draft);
  }

  issue(id: string): Observable<Invoice> {
    return this.http.post<Invoice>(`${BASE}/invoices/${encodeURIComponent(id)}/issue`, null);
  }

  cancel(id: string, reason: string): Observable<Invoice> {
    return this.http.post<Invoice>(`${BASE}/invoices/${encodeURIComponent(id)}/cancel`, { reason });
  }

  pay(id: string, amount: number, method: PaymentMethod, note: string | null): Observable<Invoice> {
    return this.http.post<Invoice>(`${BASE}/invoices/${encodeURIComponent(id)}/payments`, {
      amount,
      method,
      note,
    });
  }

  refund(paymentId: string, amount: number | null, note: string | null): Observable<Invoice> {
    return this.http.post<Invoice>(`${BASE}/payments/${encodeURIComponent(paymentId)}/refund`, {
      amount,
      note,
    });
  }

  invoicePdf(id: string): Observable<Blob> {
    return this.http.get(`${BASE}/invoices/${encodeURIComponent(id)}/pdf`, { responseType: 'blob' });
  }

  receiptPdf(paymentId: string): Observable<Blob> {
    return this.http.get(`${BASE}/payments/${encodeURIComponent(paymentId)}/pdf`, { responseType: 'blob' });
  }

  revenue(from: string, to: string, groupBy: 'day' | 'month'): Observable<RevenueReport> {
    const params = new HttpParams().set('from', from).set('to', to).set('groupBy', groupBy);
    return this.http.get<RevenueReport>(`${BASE}/reports/revenue`, { params });
  }

  unpaid(): Observable<UnpaidReport> {
    return this.http.get<UnpaidReport>(`${BASE}/reports/unpaid`);
  }
}
