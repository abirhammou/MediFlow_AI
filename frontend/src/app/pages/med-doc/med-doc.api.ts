import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type DocumentStatus = 'DRAFT' | 'VALIDATED' | 'REJECTED' | 'ARCHIVED';

export interface ExtractedField {
  name: string;
  value: string | null;
  status: DocumentStatus;
  validated_by: string | null;
  validated_at: string | null;
}

export interface DocumentListItem {
  id: string;
  patient_id: string;
  title: string;
  category_code: string | null;
  ai_suggested_category_code: string | null;
  extracted_fields: ExtractedField[];
  status: DocumentStatus;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MedicalDocument extends DocumentListItem {
  raw_text: string;
  file_path: string | null;
  uploaded_by: string | null;
}

export interface DocumentPage {
  items: DocumentListItem[];
  total: number;
  page: number;
  size: number;
}

export interface DocumentCreate {
  patient_id: string;
  title: string;
  raw_text: string;
}

export interface DocumentUpdate {
  title?: string;
  raw_text?: string;
}

export interface ExtractedFieldProposal {
  name: string;
  value: string | null;
}

export interface DocumentExtraction {
  fields: ExtractedFieldProposal[];
  suggested_category_code: string | null;
  warnings: string[];
}

export interface DocumentReview {
  status: 'VALIDATED' | 'REJECTED';
  fields: ExtractedFieldProposal[];
  category_code: string | null;
  ai_suggested_category_code: string | null;
}

@Injectable({ providedIn: 'root' })
export class MedDocApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/documents';

  list(patientId = '', page = 1, size = 100): Observable<DocumentPage> {
    let params = new HttpParams().set('page', page).set('size', size);
    if (patientId.trim()) params = params.set('patient_id', patientId.trim());
    return this.http.get<DocumentPage>(`${this.base}/`, { params });
  }

  history(patientId: string, page = 1, size = 100): Observable<DocumentPage> {
    const params = new HttpParams().set('page', page).set('size', size);
    return this.http.get<DocumentPage>(`${this.base}/patients/${patientId}/history`, { params });
  }

  get(id: string): Observable<MedicalDocument> {
    return this.http.get<MedicalDocument>(`${this.base}/${id}`);
  }

  create(body: DocumentCreate): Observable<MedicalDocument> {
    return this.http.post<MedicalDocument>(this.base, body);
  }

  update(id: string, body: DocumentUpdate): Observable<MedicalDocument> {
    return this.http.patch<MedicalDocument>(`${this.base}/${id}`, body);
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  extract(id: string): Observable<DocumentExtraction> {
    return this.http.post<DocumentExtraction>(`${this.base}/${id}/extract`, {});
  }

  review(id: string, body: DocumentReview): Observable<MedicalDocument> {
    return this.http.post<MedicalDocument>(`${this.base}/${id}/review`, body);
  }
}
