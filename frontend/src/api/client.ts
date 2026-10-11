import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type User = Schemas["UserRead"];
export type Role = User["role"];

export const api = createClient<paths>({
  baseUrl: "",
  // Required by the backend on every unsafe request (CSRF protection).
  headers: { "X-Requested-With": "runpad" },
});

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string };

function messageFrom(error: unknown): string {
  if (error && typeof error === "object" && "detail" in error) {
    const { detail } = error as { detail: unknown };
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return (detail as ValidationIssue[])
        .map((issue) => {
          const field = issue.loc?.filter((part) => part !== "body").join(".");
          return field ? `${field}: ${issue.msg}` : (issue.msg ?? "Invalid value");
        })
        .join("; ");
    }
  }
  return "Something went wrong";
}

/** Return the response data, or throw an ApiError with the server's message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (!result.response.ok) {
    throw new ApiError(result.response.status, messageFrom(result.error));
  }
  return result.data as T;
}
