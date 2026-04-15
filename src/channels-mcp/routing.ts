export const HUMAN_RECIPIENT = "suren";
export const LEGACY_HUMAN_RECIPIENT = "human";

export const RESERVED_NAMES: ReadonlySet<string> = new Set([
  HUMAN_RECIPIENT,
  LEGACY_HUMAN_RECIPIENT,
]);

export const HUMAN_SENDER_TYPE = HUMAN_RECIPIENT;
export const AGENT_SENDER_TYPE = "agent";
export const SYSTEM_SENDER_TYPE = "system";

export const DEPRECATED_HUMAN_WARNING =
  `to="${LEGACY_HUMAN_RECIPIENT}" is deprecated — use to="${HUMAN_RECIPIENT}"`;

export function canonicalRecipient(
  recipient: string
): { canonical: string; warning: string | null } {
  if (recipient === LEGACY_HUMAN_RECIPIENT) {
    return { canonical: HUMAN_RECIPIENT, warning: DEPRECATED_HUMAN_WARNING };
  }
  return { canonical: recipient, warning: null };
}

export function isHumanRecipient(recipient: string): boolean {
  return recipient === HUMAN_RECIPIENT || recipient === LEGACY_HUMAN_RECIPIENT;
}
