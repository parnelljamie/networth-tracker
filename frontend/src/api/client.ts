import createClient from "openapi-fetch"
import type { paths } from "./schema"

// Routes are declared with a literal /api/ prefix in FastAPI (see backend/app/main.py),
// so the OpenAPI schema's path keys already include it — no separate baseUrl prefix needed.
export const apiClient = createClient<paths>({ baseUrl: "" })
