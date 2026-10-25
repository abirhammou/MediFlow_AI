import { HttpErrorResponse } from '@angular/common/http';
import { describe, expect, it } from 'vitest';
import { aiErrorMessage, citationParts } from '../history.model';

describe('citationParts', () => {
  it('turns [Sx] into source chips', () => {
    expect(citationParts('LDL à 1,65 g/l [S2][S3].')).toEqual([
      { text: 'LDL à 1,65 g/l ' },
      { text: 'S2', source: 'S2' },
      { text: 'S3', source: 'S3' },
      { text: '.' },
    ]);
  });

  it('keeps a text without citation as is', () => {
    expect(citationParts('Information non trouvée.')).toEqual([{ text: 'Information non trouvée.' }]);
  });
});

describe('aiErrorMessage', () => {
  it('explains the AI errors in French', () => {
    const error = (status: number) => new HttpErrorResponse({ status });
    expect(aiErrorMessage(error(503))).toContain('momentanément indisponible');
    expect(aiErrorMessage(error(429))).toContain('Limite');
    expect(aiErrorMessage(error(502))).toContain('inutilisable');
  });
});
