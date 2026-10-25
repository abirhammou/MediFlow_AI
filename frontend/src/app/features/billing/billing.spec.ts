import { describe, expect, it } from 'vitest';
import { formatTnd, parseTnd, tndInput } from './billing.model';

describe('TND amounts (millimes)', () => {
  it('formats like the backend', () => {
    expect(formatTnd(45_500)).toBe('45,500 TND');
    expect(formatTnd(1_234_500)).toBe('1 234,500 TND');
    expect(formatTnd(7)).toBe('0,007 TND');
    expect(formatTnd(-13_500)).toBe('-13,500 TND');
  });

  it('parses what the secretary types', () => {
    expect(parseTnd('45,5')).toBe(45_500);
    expect(parseTnd('45.500')).toBe(45_500);
    expect(parseTnd(' 1 234,5 TND')).toBe(1_234_500);
    expect(parseTnd('45')).toBe(45_000);
    expect(parseTnd('45,5001')).toBeNull();
    expect(parseTnd('-3')).toBeNull();
    expect(parseTnd('abc')).toBeNull();
  });

  it('round-trips through the input format', () => {
    expect(parseTnd(tndInput(1_234_500))).toBe(1_234_500);
    expect(tndInput(31_500)).toBe('31,500');
  });
});
