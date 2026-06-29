export function numOrUndefined(value: FormDataEntryValue | null): number | undefined {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function intOrUndefined(value: FormDataEntryValue | null): number | undefined {
  const parsed = numOrUndefined(value);
  if (parsed === undefined) return undefined;
  return Math.trunc(parsed);
}

export function strOrUndefined(value: FormDataEntryValue | null): string | undefined {
  const raw = typeof value === "string" ? value.trim() : "";
  return raw || undefined;
}
