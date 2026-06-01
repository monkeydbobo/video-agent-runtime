import { useId, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ACCENT_BTN_CLS, ACCENT_BUTTON_STYLE } from "@/components/ui/darkroom-tokens";
import { FieldLabel } from "@/components/ui/FieldLabel";
import type { GenerationMode } from "@/utils/generation-mode";

export interface WizardStep1Value {
  title: string;
  // 营销视频 Agent：内容模式固定 marketing、竖屏 9:16、storyboard，不在 UI 暴露。
  contentMode: "marketing";
  aspectRatio: "9:16" | "16:9";
  generationMode: GenerationMode;
}

export interface WizardStep1BasicsProps {
  value: WizardStep1Value;
  onChange: (next: WizardStep1Value) => void;
  onNext: () => void;
  onCancel: () => void;
}

export function WizardStep1Basics({
  value,
  onChange,
  onNext,
  onCancel,
}: WizardStep1BasicsProps) {
  const { t } = useTranslation(["common", "dashboard", "templates"]);
  const [titleError, setTitleError] = useState("");
  const reactId = useId();
  const titleId = `${reactId}-title`;
  const titleErrorId = `${reactId}-title-error`;

  const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTitleError("");
    onChange({ ...value, title: e.target.value });
  };

  const handleNext = () => {
    if (!value.title.trim()) {
      setTitleError(t("dashboard:project_title_required"));
      return;
    }
    onNext();
  };

  return (
    <div className="space-y-5">
      {/* Title */}
      <div>
        <FieldLabel htmlFor={titleId} required>
          {t("dashboard:project_title")}
        </FieldLabel>
        <div className="relative">
          <input
            id={titleId}
            type="text"
            value={value.title}
            onChange={handleTitleChange}
            placeholder={t("dashboard:rebirth_empress_example")}
            aria-required="true"
            aria-invalid={titleError ? "true" : undefined}
            aria-describedby={titleError ? titleErrorId : undefined}
            className="w-full rounded-[8px] border border-hairline bg-bg-grad-a/55 px-3 py-2.5 text-[14px] text-text placeholder:text-text-4 transition-colors focus:border-accent/55 focus:bg-bg-grad-a/85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          />
        </div>
        {titleError ? (
          <p
            id={titleErrorId}
            role="alert"
            aria-live="polite"
            className="mt-1.5 inline-flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-warm"
          >
            <AlertTriangle aria-hidden className="h-3 w-3" />
            {titleError}
          </p>
        ) : null}
        <p className="mt-1.5 text-[11.5px] text-text-4">{t("dashboard:project_id_auto_gen_hint")}</p>
      </div>

      {/* Content Mode — 营销视频固定，仅展示说明 */}
      <div>
        <FieldLabel>{t("dashboard:content_mode")}</FieldLabel>
        <div
          className="rounded-[8px] border border-accent/35 bg-accent-dim px-3 py-2.5 text-[13px] text-text"
        >
          {t("dashboard:marketing_video")}
        </div>
        <p className="mt-2 text-[11.5px] leading-[1.55] text-text-3">
          {t("dashboard:content_mode_marketing_desc")}
        </p>
      </div>

      {/* Footer */}
      <div className="mt-7 flex items-center justify-between border-t border-hairline-soft pt-5">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-[7px] px-2.5 py-1.5 text-[12.5px] text-text-3 transition-colors hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {t("common:cancel")}
        </button>
        <button
          type="button"
          onClick={handleNext}
          disabled={!value.title.trim()}
          className={ACCENT_BTN_CLS}
          style={ACCENT_BUTTON_STYLE}
        >
          {t("templates:next_step")}
          <span aria-hidden>→</span>
        </button>
      </div>
    </div>
  );
}
