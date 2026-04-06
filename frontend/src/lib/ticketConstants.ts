/**
 * Shared ticket domain constants used across multiple pages.
 * Keep business-logic values here so they stay in sync.
 */

/** Valid status transitions for each ticket state. */
export const TICKET_TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "cancelled"],
  in_progress: [
    "awaiting_client",
    "awaiting_technical",
    "resolved",
    "cancelled",
  ],
  awaiting_client: ["in_progress", "resolved", "cancelled"],
  awaiting_technical: ["in_progress", "resolved", "cancelled"],
  resolved: ["closed"],
  closed: [],
  cancelled: [],
};
