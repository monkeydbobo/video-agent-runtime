import { UserRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/stores/auth-store";

/**
 * Compact signed-in identity chip for the projects lobby TopBar.
 * Hidden when auth is bypassed / username not yet resolved.
 */
export function CurrentUserBadge() {
  const { t } = useTranslation("common");
  const username = useAuthStore((state) => state.username);

  if (!username) return null;

  const label = t("signed_in_as", { username });

  return (
    <span
      className="inline-flex max-w-[10.5rem] items-center gap-1.5 rounded-[7px] border border-hairline bg-bg-grad-a/50 px-2.5 py-1.5 text-[12px] text-text-2"
      title={label}
      aria-label={label}
      data-testid="current-user-badge"
    >
      <UserRound className="h-3.5 w-3.5 shrink-0 text-text-3" aria-hidden />
      <span className="truncate font-medium tracking-[-0.01em] text-text">{username}</span>
    </span>
  );
}
