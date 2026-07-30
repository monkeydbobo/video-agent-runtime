/**
 * @author wanghaobo
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ImageFlipReveal } from "./ImageFlipReveal";

const refreshMediaUrl = vi.fn();

vi.mock("@/lib/mediaUrl", () => ({
  isPrivateMediaUrl: (url: string) => url.includes("/api/v1/files/"),
  refreshMediaUrl: (...args: unknown[]) => refreshMediaUrl(...args),
}));

describe("ImageFlipReveal", () => {
  beforeEach(() => {
    refreshMediaUrl.mockReset();
  });

  it("私有图片加载失败时先续签 media_token 再重试", async () => {
    refreshMediaUrl.mockResolvedValueOnce("/api/v1/files/demo/char.png?media_token=new");
    const onError = vi.fn();

    render(
      <ImageFlipReveal
        src="/api/v1/files/demo/char.png"
        alt="character"
        onError={onError}
      />,
    );

    fireEvent.error(screen.getByAltText("character"));

    await waitFor(() => {
      expect(refreshMediaUrl).toHaveBeenCalledWith("/api/v1/files/demo/char.png");
      expect(screen.getByAltText("character")).toHaveAttribute(
        "src",
        "/api/v1/files/demo/char.png?media_token=new",
      );
    });
    expect(onError).not.toHaveBeenCalled();
  });

  it("续签仍失败时才触发 onError（角色卡据此显示待生成）", async () => {
    refreshMediaUrl.mockResolvedValue(null);
    const onError = vi.fn();

    render(
      <ImageFlipReveal
        src="/api/v1/files/demo/char.png"
        alt="character"
        onError={onError}
        fallback={<span>pending</span>}
      />,
    );

    fireEvent.error(screen.getByAltText("character"));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
    });
  });
});
