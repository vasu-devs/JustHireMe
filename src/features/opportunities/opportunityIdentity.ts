import type { OpportunityApplicationIdentity } from "../../api";

export function hasRequiredApplicationIdentity(identity: OpportunityApplicationIdentity): boolean {
  return Boolean(identity.email.trim() && identity.phone.trim());
}
