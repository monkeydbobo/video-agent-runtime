import { useRef } from "react";
import { Film, Loader2, Upload, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ACCENT_BTN_CLS, ACCENT_BUTTON_STYLE, GHOST_BTN_LG_CLS } from "@/components/ui/darkroom-tokens";

export interface WizardStep3MarketingReferenceValue {
  referenceVideoFile: File | null;
}

interface WizardStep3MarketingReferenceProps {
  value: WizardStep3MarketingReferenceValue;
  onChange: (next: WizardStep3MarketingReferenceValue) => void;
  onBack: () => void;
  onCreate: () => void;
  onCancel: () => void;
  creating: boolean;
}

const ACCEPTED_VIDEO_TYPES = ".mp4,.mov,.webm";

export function WizardStep3MarketingReference({
  value,
  onChange,
  onBack,
  onCreate,
  onCancel,
  creating,
}: WizardStep3MarketingReferenceProps) {
  const { t } = useTranslation(["common", "dashboard", "templates"]);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    if (file) onChange({ referenceVideoFile: file });
    e.target.value = "";
  };

  return (
    <div className="space-y-5">
      <div
        className="relative overflow-hidden rounded-2xl p-5"
        style={{
          border: "1px solid var(--color-hairline-soft)",
          background:
            "radial-gradient(420px 220px at 10% -10%, var(--color-accent-dim), transparent 60%), linear-gradient(180deg, oklch(0.22 0.012 265 / 0.55), oklch(0.18 0.010 265 / 0.45))",
          boxShadow: "inset 0 1px 0 oklch(1 0 0 / 0.04), 0 10px 30px -16px oklch(0 0 0 / 0.65)",
        }}
      >
        <input ref={inputRef} type="file" accept={ACCEPTED_VIDEO_TYPES} onChange={handleSelect} className="hidden" />
        <div className="flex items-start gap-4">
          <span
            aria-hidden
            className="grid h-12 w-12 shrink-0 place-items-center rounded-xl"
            style={{
              color: "var(--color-accent-2)",
              border: "1px solid var(--color-accent-soft)",
              background: "linear-gradient(135deg, var(--color-accent-dim), oklch(0.76 0.09 295 / 0.05))",
            }}
          >
            <Film className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-[15px] font-semibold text-text">{t("dashboard:viral_reference_step_title")}</h3>
            <p className="mt-1 text-[12px] leading-[1.65] text-text-3">
              {t("dashboard:viral_reference_step_desc")}
            </p>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={creating}
                className="focus-ring inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-medium transition-colors disabled:opacity-50"
                style={{
                  color: "var(--color-text-2)",
                  border: "1px solid var(--color-hairline)",
                  background: "oklch(0.22 0.011 265 / 0.55)",
                }}
              >
                <Upload className="h-3.5 w-3.5" />
                {value.referenceVideoFile ? t("dashboard:replace_reference_video") : t("dashboard:upload_reference_video")}
              </button>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-text-4">MP4 / MOV / WEBM</span>
            </div>
            {value.referenceVideoFile && (
              <div
                className="mt-4 flex items-center gap-2 rounded-lg px-3 py-2"
                style={{
                  border: "1px solid var(--color-accent-soft)",
                  background: "var(--color-accent-dim)",
                }}
              >
                <Film className="h-3.5 w-3.5 shrink-0 text-accent-2" />
                <span className="min-w-0 flex-1 truncate text-[12px] text-text-2" title={value.referenceVideoFile.name}>
                  {value.referenceVideoFile.name}
                </span>
                <button
                  type="button"
                  onClick={() => onChange({ referenceVideoFile: null })}
                  className="focus-ring grid h-6 w-6 place-items-center rounded-md text-text-4 hover:text-text"
                  aria-label={t("common:delete")}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="mt-7 flex items-center justify-between border-t border-hairline-soft pt-5">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-[7px] px-2.5 py-1.5 text-[12.5px] text-text-3 transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {t("common:cancel")}
        </button>
        <div className="flex gap-2">
          <button type="button" onClick={onBack} className={GHOST_BTN_LG_CLS}>
            <span aria-hidden>←</span>
            {t("templates:prev_step")}
          </button>
          <button type="button" onClick={onCreate} disabled={creating} className={ACCENT_BTN_CLS} style={ACCENT_BUTTON_STYLE}>
            {creating ? (
              <>
                <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden />
                {t("dashboard:creating")}
              </>
            ) : (
              <>●&nbsp;{t("dashboard:create_project")}</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
