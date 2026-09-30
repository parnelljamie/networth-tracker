interface DomainErrorBody {
  error?: { code?: string; message?: string; field?: string | null }
}

/** Surfaces the backend's DomainError message (docs/04-api.md's `{"error": {code, message, field}}`). */
export function apiErrorMessage(err: unknown, fallback: string): string {
  const body = err as DomainErrorBody | undefined
  return body?.error?.message ?? fallback
}
