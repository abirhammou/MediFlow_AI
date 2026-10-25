import { describe, expect, it } from 'vitest';
import { downloadName, formatSize } from '../patient-file.model';
import { fileCategoriesFor } from '../patient-permissions';

describe('fileCategoriesFor', () => {
  it('never gives administrative files to doctors', () => {
    expect(fileCategoriesFor('DOCTOR', 'read')).toEqual(['MEDICAL']);
    expect(fileCategoriesFor('DOCTOR', 'write')).toEqual([]);
  });

  it('lets the secretary and the admin manage both categories', () => {
    for (const role of ['SECRETARY', 'ADMIN'] as const) {
      expect(fileCategoriesFor(role, 'read')).toEqual(['ADMINISTRATIVE', 'MEDICAL']);
      expect(fileCategoriesFor(role, 'write')).toEqual(['ADMINISTRATIVE', 'MEDICAL']);
    }
  });

  it('gives the patient read-only access', () => {
    expect(fileCategoriesFor('PATIENT', 'read')).toEqual(['ADMINISTRATIVE', 'MEDICAL']);
    expect(fileCategoriesFor('PATIENT', 'write')).toEqual([]);
    expect(fileCategoriesFor(undefined, 'read')).toEqual([]);
  });
});

describe('file helpers', () => {
  it('formats sizes in French units', () => {
    expect(formatSize(512)).toBe('512 o');
    expect(formatSize(20 * 1024)).toBe('20 Ko');
    expect(formatSize(1.5 * 1024 * 1024)).toBe('1,5 Mo');
  });

  it('builds a safe download name from the title', () => {
    expect(downloadName({ title: 'Échographie / cœur', mime: 'image/jpeg' })).toBe('echographie-c-ur.jpg');
  });
});
