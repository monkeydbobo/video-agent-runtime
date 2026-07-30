/**
 * @author wanghaobo
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PrivateMediaImg } from "./PrivateMedia";

const refreshMediaUrl = vi.fn();

vi.mock("@/lib/mediaUrl", () => ({
  isPrivateMediaUrl: (url: string) => url.includes("/api/v1/files/"),
  refreshMediaUrl: (...args: unknown[]) => refreshMediaUrl(...args),
}));

describe("PrivateMediaImg", () => {
  beforeEach(() => {
    refreshMediaUrl.mockReset();
  });

  it("media_token 失效时续签后重试，不立刻回调 onError", async () => {
    refreshMediaUrl.mockResolvedValueOnce("/api/v1/files/demo/a.png?media_token=new");
    const onError = vi.fn();

    render(
      <PrivateMediaImg
        src="/api/v1/files/demo/a.png"
        alt="sheet"
        onError={onError}
      />,
    );

    fireEvent.error(screen.getByAltText("sheet"));

    await waitFor(() => {
      expect(refreshMediaUrl).toHaveBeenCalledWith("/api/v1/files/demo/a.png");
    });
    expect(onError).not.toHaveBeenCalled();
    expect(screen.getByAltText("sheet")).toHaveAttribute(
      "src",
      "/api/v1/files/demo/a.png?media_token=new",
    );
  });

  it("续签失败后才回调 onError", async () => {
    refreshMediaUrl.mockResolvedValue(null);
    const onError = vi.fn();

    render(
      <PrivateMediaImg
        src="/api/v1/files/demo/a.png"
        alt="sheet"
        onError={onError}
      />,
    );

    fireEvent.error(screen.getByAltText("sheet"));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledTimes(1);
    });
  });
});
