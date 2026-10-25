import { describe, expect, it } from 'vitest';
import { canEditReport } from '../patient-permissions';
import { reportSections } from './patient-reports';

describe('canEditReport', () => {
  it('lets only the author doctor edit a draft', () => {
    expect(canEditReport('DOCTOR', { is_mine: true, status: 'DRAFT' })).toBe(true);
  });

  it("keeps a colleague's or a finalized report read-only", () => {
    expect(canEditReport('DOCTOR', { is_mine: false, status: 'DRAFT' })).toBe(false);
    expect(canEditReport('DOCTOR', { is_mine: true, status: 'FINAL' })).toBe(false);
    expect(canEditReport('ADMIN', { is_mine: false, status: 'DRAFT' })).toBe(false);
    expect(canEditReport('SECRETARY', { is_mine: false, status: 'FINAL' })).toBe(false);
    expect(canEditReport(undefined, { is_mine: true, status: 'DRAFT' })).toBe(false);
  });
});

describe('reportSections', () => {
  it('splits the stored "## Title" blocks', () => {
    const content = '## Motif de consultation\nToux.\n\n## Conclusion\nNon précisé dans les notes.';
    expect(reportSections(content)).toEqual([
      { title: 'Motif de consultation', body: 'Toux.' },
      { title: 'Conclusion', body: 'Non précisé dans les notes.' },
    ]);
    expect(reportSections(null)).toEqual([]);
  });
});
