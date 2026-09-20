import { describe, expect, it } from "vitest";
import { extractSharedUrl } from "./share";

describe("share target URLs", () => {
  it("accepts a dedicated URL and removes its fragment", () => {
    expect(
      extractSharedUrl(
        new URLSearchParams({ url: "https://example.com/a?b=1#section" }),
      ),
    ).toBe("https://example.com/a?b=1");
  });
  it("finds the link in Android shared text", () => {
    expect(
      extractSharedUrl(
        new URLSearchParams({
          title: "文章",
          text: "推荐阅读 https://example.com/article，来自浏览器",
        }),
      ),
    ).toBe("https://example.com/article");
  });
  it("rejects non-web shares and credentials", () => {
    expect(
      extractSharedUrl(
        new URLSearchParams({ url: "javascript:alert(1)", text: "普通文字" }),
      ),
    ).toBeNull();
    expect(
      extractSharedUrl(
        new URLSearchParams({ url: "https://user:secret@example.com" }),
      ),
    ).toBeNull();
  });
});
