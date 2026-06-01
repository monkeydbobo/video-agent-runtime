import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Stub URL object APIs not available in jsdom
globalThis.URL.createObjectURL ??= vi.fn(() => "blob:mock");
globalThis.URL.revokeObjectURL ??= vi.fn();
import "@/i18n";
import { CreateProjectModal } from "./CreateProjectModal";
import { API } from "@/api";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";

// Mock wouter navigation
const navigateMock = vi.fn();
vi.mock("wouter", () => ({
  useLocation: () => ["/app/projects", navigateMock],
}));

const mockSysConfig = {
  settings: {
    default_video_backend: "",
    default_image_backend: "",
    default_text_backend: "",
    text_backend_script: "",
    text_backend_overview: "",
    text_backend_style: "",
    video_generate_audio: false,
    anthropic_api_key: { is_set: false, masked: null },
    anthropic_base_url: "",
    anthropic_model: "",
    anthropic_default_haiku_model: "",
    anthropic_default_opus_model: "",
    anthropic_default_sonnet_model: "",
    claude_code_subagent_model: "",
    agent_session_cleanup_delay_seconds: 0,
    agent_max_concurrent_sessions: 0,
  },
  options: {
    video_backends: ["gemini-aistudio/veo-3"],
    image_backends: ["gemini-aistudio/nano-banana"],
    text_backends: ["gemini-aistudio/g25"],
    provider_names: { "gemini-aistudio": "Gemini AI Studio" },
  },
};

const mockProviders = {
  providers: [
    {
      id: "gemini-aistudio",
      display_name: "Gemini AI Studio",
      description: "",
      status: "ready" as const,
      media_types: ["video", "image", "text"],
      capabilities: [],
      configured_keys: [],
      missing_keys: [],
      models: {
        "veo-3": {
          display_name: "veo-3",
          media_type: "video",
          capabilities: [],
          default: false,
          supported_durations: [4, 6, 8],
          duration_resolution_constraints: {},
        },
      },
    },
  ],
};

describe("CreateProjectModal", () => {
  beforeEach(() => {
    navigateMock.mockClear();
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useProjectsStore.setState({ showCreateModal: true });
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(mockSysConfig as never);
    vi.spyOn(API, "getProviders").mockResolvedValue(mockProviders as never);
    vi.spyOn(API, "listCustomProviders").mockResolvedValue({ providers: [] });
    vi.spyOn(API, "createProject").mockResolvedValue({
      success: true,
      name: "demo-proj",
      project: {} as never,
    });
    vi.spyOn(API, "uploadStyleImage").mockResolvedValue({
      success: true,
      style_image: "",
      style_description: "",
      url: "",
    });
  });

  it("starts at step 1 and shows title input", () => {
    render(<CreateProjectModal />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // Next button disabled until title typed
    expect(screen.getByRole("button", { name: /下一步/ })).toBeDisabled();
  });

  it("advances from step 1 to step 2 after title entered and Next clicked", async () => {
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    // Step 2 shows loading or Back button
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /上一步/ })).toBeInTheDocument()
    );
  });

  it("advances from step 2 to step 3 without validation", async () => {
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ })); // to step 2
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled()
    );
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    // Step 3: Create button appears
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /创建项目/ })).toBeInTheDocument()
    );
  });

  it("submits createProject as marketing (no style template) when Create clicked on step 3", async () => {
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled()
    );
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /创建项目/ })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /创建项目/ }));
    await waitFor(() => expect(API.createProject).toHaveBeenCalled());
    expect(API.createProject).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "demo",
        content_mode: "marketing",
        aspect_ratio: "9:16",
        generation_mode: "storyboard",
        style_template_id: null,
        video_backend: null,
        image_provider_t2i: null,
        image_provider_i2i: null,
        default_duration: null,
      })
    );
    expect(navigateMock).toHaveBeenCalledWith("/app/projects/demo-proj");
  });

  it("goes back from step 2 to step 1 preserving title", async () => {
    render(<CreateProjectModal />);
    const titleInput = screen.getByRole("textbox");
    fireEvent.change(titleInput, { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /上一步/ })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /上一步/ }));
    // Back on step 1, title preserved
    expect(screen.getByRole("textbox")).toHaveValue("demo");
  });

  it("shows error toast and stays on step 3 when createProject fails", async () => {
    vi.spyOn(API, "createProject").mockRejectedValueOnce(new Error("boom"));
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /创建项目/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /创建项目/ }));
    await waitFor(() => expect(API.createProject).toHaveBeenCalled());
    // Not navigated away
    expect(navigateMock).not.toHaveBeenCalled();
    // Create button re-enabled after failure (creating=false)
    await waitFor(() => expect(screen.getByRole("button", { name: /创建项目/ })).toBeEnabled());
  });

  it("marketing step 3 shows the viral reference uploader (no style picker)", async () => {
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /创建项目/ })).toBeInTheDocument());

    // No style "自定义/Custom" tab in marketing flow
    expect(screen.queryByRole("button", { name: /自定义|Custom/ })).toBeNull();
    // Create without uploading reference video → style_template_id null, no style upload
    fireEvent.click(screen.getByRole("button", { name: /创建项目/ }));
    await waitFor(() => expect(API.createProject).toHaveBeenCalled());
    expect(API.createProject).toHaveBeenCalledWith(expect.objectContaining({ style_template_id: null }));
    expect(API.uploadStyleImage).not.toHaveBeenCalled();
  });

  it("marketing step 3 uploads selected product images to product_images on create", async () => {
    const uploadSpy = vi
      .spyOn(API, "uploadFile")
      .mockResolvedValue({ success: true, filename: "bottle.png", path: "product_images/bottle.png", url: "" } as never);
    render(<CreateProjectModal />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "demo" } });
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /下一步/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /下一步/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /创建项目/ })).toBeInTheDocument());

    const imageInput = document.querySelector('input[type="file"][multiple]') as HTMLInputElement;
    expect(imageInput).not.toBeNull();
    const file = new File(["x"], "bottle.png", { type: "image/png" });
    fireEvent.change(imageInput, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: /创建项目/ }));
    await waitFor(() => expect(API.createProject).toHaveBeenCalled());
    await waitFor(() =>
      expect(uploadSpy).toHaveBeenCalledWith("demo-proj", "product_images", expect.any(File)),
    );
  });
});
