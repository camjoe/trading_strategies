import { describe, expect, it, vi } from "vitest";

import { debounce } from "./timing";

describe("debounce", () => {
  it("coalesces rapid calls into a single invocation", () => {
    vi.useFakeTimers();
    const spy = vi.fn();
    const debounced = debounce(spy, 300);

    debounced();
    debounced();
    debounced();

    expect(spy).toHaveBeenCalledTimes(0);
    vi.advanceTimersByTime(299);
    expect(spy).toHaveBeenCalledTimes(0);
    vi.advanceTimersByTime(1);
    expect(spy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("passes through the latest arguments", () => {
    vi.useFakeTimers();
    const spy = vi.fn<(value: string) => void>();
    const debounced = debounce(spy, 100);

    debounced("first");
    debounced("latest");

    vi.advanceTimersByTime(100);
    expect(spy).toHaveBeenCalledWith("latest");
    expect(spy).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
