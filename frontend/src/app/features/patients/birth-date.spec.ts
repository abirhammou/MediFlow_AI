import { ageFrom, formatBirthDate, parseIsoDate, todayIso, yearsBefore } from './birth-date';

describe('birth-date', () => {
  it('parses real calendar dates only', () => {
    expect(parseIsoDate('1990-01-01')).toEqual({ year: 1990, month: 1, day: 1 });
    expect(parseIsoDate('2024-02-29')).not.toBeNull();
    expect(parseIsoDate('2023-02-29')).toBeNull();
    expect(parseIsoDate('1990-13-01')).toBeNull();
    expect(parseIsoDate('01/01/1990')).toBeNull();
    expect(parseIsoDate('')).toBeNull();
  });

  it('formats without any time zone shift', () => {
    expect(formatBirthDate('1990-01-01')).toBe('01/01/1990');
    expect(formatBirthDate('2000-12-31')).toBe('31/12/2000');
    expect(formatBirthDate(null)).toBe('');
  });

  it('computes the age around the birthday', () => {
    expect(ageFrom('1990-06-15', '2026-06-14')).toBe(35);
    expect(ageFrom('1990-06-15', '2026-06-15')).toBe(36);
    expect(ageFrom('2026-01-01', '2026-10-24')).toBe(0);
    expect(ageFrom('bad', '2026-10-24')).toBeNull();
  });

  it('uses the local calendar day for today', () => {
    // 23:30 local time stays the same day, whatever the UTC date is.
    expect(todayIso(new Date(2026, 9, 24, 23, 30))).toBe('2026-10-24');
    expect(todayIso(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01');
  });

  it('goes back whole years, 29 February included', () => {
    expect(yearsBefore('2026-10-24', 130)).toBe('1896-10-24');
    expect(yearsBefore('2028-02-29', 1)).toBe('2027-02-28');
  });
});
