/**
 * Birth dates stay 'YYYY-MM-DD' strings from the API to <input type="date"> and back.
 * Never `new Date('YYYY-MM-DD')`: that is UTC midnight, and reading it back in
 * local time can land on the previous day.
 */

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export interface DateParts {
  year: number;
  month: number;
  day: number;
}

export function parseIsoDate(value: string | null | undefined): DateParts | null {
  const match = ISO_DATE.exec(value ?? '');
  if (!match) return null;
  const [year, month, day] = match.slice(1).map(Number);
  // Calendar check done entirely in UTC: no time zone involved.
  const check = new Date(Date.UTC(year, month - 1, day));
  const valid =
    check.getUTCFullYear() === year &&
    check.getUTCMonth() === month - 1 &&
    check.getUTCDate() === day;
  return valid ? { year, month, day } : null;
}

function pad(value: number, length = 2): string {
  return String(value).padStart(length, '0');
}

export function toIsoDate({ year, month, day }: DateParts): string {
  return `${pad(year, 4)}-${pad(month)}-${pad(day)}`;
}

/** Today on this computer (the clinic's), as 'YYYY-MM-DD'. */
export function todayIso(now: Date = new Date()): string {
  return toIsoDate({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() });
}

export function yearsBefore(iso: string, years: number): string {
  const parts = parseIsoDate(iso);
  if (!parts) return iso;
  const leapDay = parts.month === 2 && parts.day === 29;
  return toIsoDate({ year: parts.year - years, month: parts.month, day: leapDay ? 28 : parts.day });
}

/** 'YYYY-MM-DD' -> 'dd/mm/yyyy'. */
export function formatBirthDate(iso: string | null | undefined): string {
  const parts = parseIsoDate(iso);
  return parts ? `${pad(parts.day)}/${pad(parts.month)}/${pad(parts.year, 4)}` : '';
}

export function ageFrom(iso: string | null | undefined, today: string = todayIso()): number | null {
  const birth = parseIsoDate(iso);
  const now = parseIsoDate(today);
  if (!birth || !now) return null;
  const hadBirthday =
    now.month > birth.month || (now.month === birth.month && now.day >= birth.day);
  return now.year - birth.year - (hadBirthday ? 0 : 1);
}

export function ageLabel(age: number | null): string {
  if (age === null) return '';
  return age < 2 ? `${age} an` : `${age} ans`;
}

const DATE_TIME = new Intl.DateTimeFormat('fr-FR', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Africa/Tunis',
});

/** API timestamps (createdAt, deletedAt…) are full ISO date-times, safe to parse. */
export function formatDateTime(value: string | null | undefined): string {
  return value ? DATE_TIME.format(new Date(value)) : '';
}
