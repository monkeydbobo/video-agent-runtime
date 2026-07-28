import { LogOut } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation } from "wouter";
import { useAuthStore } from "@/stores/auth-store";

type LogoutButtonVariant = "labeled" | "header";

interface LogoutButtonProps {
  variant?: LogoutButtonVariant;
}

const VARIANT_CLASSES: Record<LogoutButtonVariant, string> = {
  labeled:
    "inline-flex items-center gap-1.5 rounded-[7px] border border-hairline bg-bg-grad-a/50 px-3 py-1.5 text-[12px] text-text-2 transition-colors hover:border-warm/45 hover:bg-warm/10 hover:text-warm-bright focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
  header:
    "inline-flex h-[30px] items-center gap-1.5 rounded-md border border-hairline-soft px-2 text-[11.5px] text-text-3 transition-colors hover:border-warm/45 hover:bg-warm/10 hover:text-warm-bright focus-ring",
};

export function LogoutButton({ variant = "labeled" }: LogoutButtonProps) {
  const { t } = useTranslation("common");
  const logout = useAuthStore((state) => state.logout);
  const [, setLocation] = useLocation();
  const label = t("logout");

  const handleLogout = () => {
    logout();
    setLocation("~/login");
  };

  return (
    <button
      type="button"
      onClick={handleLogout}
      className={VARIANT_CLASSES[variant]}
      title={label}
      aria-label={label}
    >
      <LogOut className="h-3.5 w-3.5" aria-hidden />
      <span className={variant === "header" ? "hidden xl:inline" : undefined}>{label}</span>
    </button>
  );
}
