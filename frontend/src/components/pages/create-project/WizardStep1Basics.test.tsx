import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import "@/i18n"; // ensure i18n resources loaded
import { WizardStep1Basics } from "./WizardStep1Basics";

const baseValue = {
  title: "",
  contentMode: "marketing" as const,
  aspectRatio: "9:16" as const,
  generationMode: "storyboard" as const,
};

describe("WizardStep1Basics (marketing-only)", () => {
  it("disables Next button when title is empty", () => {
    render(
      <WizardStep1Basics value={baseValue} onChange={() => {}} onNext={() => {}} onCancel={() => {}} />,
    );
    expect(screen.getByRole("button", { name: /下一步/ })).toBeDisabled();
  });

  it("enables Next button when title has content", () => {
    render(
      <WizardStep1Basics
        value={{ ...baseValue, title: "demo" }}
        onChange={() => {}}
        onNext={() => {}}
        onCancel={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled();
  });

  it("calls onNext when Next is clicked with valid title", () => {
    const onNext = vi.fn();
    render(
      <WizardStep1Basics
        value={{ ...baseValue, title: "demo" }}
        onChange={() => {}}
        onNext={onNext}
        onCancel={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("emits onChange when title input changes", () => {
    const onChange = vi.fn();
    render(
      <WizardStep1Basics value={baseValue} onChange={onChange} onNext={() => {}} onCancel={() => {}} />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hello" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ title: "hello" }));
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(
      <WizardStep1Basics value={baseValue} onChange={() => {}} onNext={() => {}} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /取消|Cancel/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("marks title input as aria-required", () => {
    render(
      <WizardStep1Basics value={baseValue} onChange={() => {}} onNext={() => {}} onCancel={() => {}} />,
    );
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-required", "true");
  });

  it("shows the locked marketing content mode", () => {
    render(
      <WizardStep1Basics value={baseValue} onChange={() => {}} onNext={() => {}} onCancel={() => {}} />,
    );
    expect(screen.getAllByText(/营销视频|Marketing/i).length).toBeGreaterThanOrEqual(1);
  });
});
