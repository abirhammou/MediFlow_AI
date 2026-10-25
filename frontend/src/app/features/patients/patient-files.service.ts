import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { FileCategory, FileUpload, PatientFile } from './patient-file.model';

function url(patientId: string, suffix = ''): string {
  return `/api/patients/${encodeURIComponent(patientId)}/files${suffix}`;
}

@Injectable({ providedIn: 'root' })
export class PatientFilesService {
  private http = inject(HttpClient);

  /** Newest first; the API only returns the categories the role may read. */
  list(patientId: string, category?: FileCategory): Observable<PatientFile[]> {
    const params = category ? new HttpParams().set('category', category) : undefined;
    return this.http.get<PatientFile[]>(url(patientId), { params });
  }

  upload(patientId: string, upload: FileUpload): Observable<PatientFile> {
    const form = new FormData();
    form.append('file', upload.file, upload.file.name);
    form.append('category', upload.category);
    form.append('type', upload.type);
    form.append('title', upload.title);
    return this.http.post<PatientFile>(url(patientId), form);
  }

  download(patientId: string, fileId: string): Observable<Blob> {
    return this.http.get(url(patientId, `/${encodeURIComponent(fileId)}/download`), {
      responseType: 'blob',
    });
  }

  /** Soft delete (SECRETARY, ADMIN). */
  remove(patientId: string, fileId: string): Observable<void> {
    return this.http.delete<void>(url(patientId, `/${encodeURIComponent(fileId)}`));
  }
}
