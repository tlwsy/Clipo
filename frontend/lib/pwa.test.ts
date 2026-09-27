// SPDX-License-Identifier: AGPL-3.0-or-later
import { afterEach, describe, expect, it, vi } from "vitest";
import { refreshApplication, watchServiceWorkerUpdates } from "./pwa";

class Worker extends EventTarget {
  state: ServiceWorkerState = "installing";
  postMessage = vi.fn();
  change(state: ServiceWorkerState) {
    this.state = state;
    this.dispatchEvent(new Event("statechange"));
  }
}

function setup(controlled = true) {
  const previous = new Worker();
  previous.state = "activated";
  const container = Object.assign(new EventTarget(), {
    controller: controlled ? previous : null,
  });
  const registration = Object.assign(new EventTarget(), {
    installing: null as Worker | null,
    waiting: null as Worker | null,
  });
  const onUpdate = vi.fn();
  const workers = container as unknown as ServiceWorkerContainer;
  const registered = registration as unknown as ServiceWorkerRegistration;
  return { container, registration, workers, registered, onUpdate };
}

afterEach(() => vi.useRealTimers());

describe("PWA update detection", () => {
  it("does not announce the first installation or its initial controller change", () => {
    const { container, registration, workers, registered, onUpdate } =
      setup(false);
    const dispose = watchServiceWorkerUpdates(registered, workers, onUpdate);
    const worker = new Worker();
    registration.installing = worker;
    registration.dispatchEvent(new Event("updatefound"));
    registration.waiting = worker;
    worker.change("installed");
    registration.waiting = null;
    worker.change("activating");
    container.controller = worker;
    container.dispatchEvent(new Event("controllerchange"));
    worker.change("activated");
    expect(onUpdate.mock.calls.every(([available]) => !available)).toBe(true);

    // A later update in the same session must still be detected.
    registration.waiting = new Worker();
    registration.waiting.state = "installed";
    registration.dispatchEvent(new Event("updatefound"));
    expect(onUpdate).toHaveBeenLastCalledWith(true);
    dispose();
  });

  it("watches an installation already underway when registration resolves", () => {
    const { registration, workers, registered, onUpdate } = setup();
    const worker = new Worker();
    registration.installing = worker;
    const dispose = watchServiceWorkerUpdates(registered, workers, onUpdate);
    expect(onUpdate).toHaveBeenLastCalledWith(false);
    registration.waiting = worker;
    worker.change("installed");
    expect(onUpdate).toHaveBeenLastCalledWith(true);
    registration.waiting = null;
    worker.change("redundant");
    expect(onUpdate).toHaveBeenLastCalledWith(false);
    dispose();
  });

  it("keeps a reload available when another window activates the update", () => {
    const { container, registration, workers, registered, onUpdate } = setup();
    const worker = new Worker();
    worker.state = "installed";
    registration.waiting = worker;
    const dispose = watchServiceWorkerUpdates(registered, workers, onUpdate);
    expect(onUpdate).toHaveBeenLastCalledWith(true);
    registration.waiting = null;
    worker.change("activating");
    container.controller = worker;
    container.dispatchEvent(new Event("controllerchange"));
    worker.change("activated");
    expect(onUpdate).toHaveBeenLastCalledWith(true);
    dispose();
    onUpdate.mockClear();
    worker.change("redundant");
    container.dispatchEvent(new Event("controllerchange"));
    registration.dispatchEvent(new Event("updatefound"));
    expect(onUpdate).not.toHaveBeenCalled();
  });
});

describe("PWA refresh", () => {
  it.each(["activated", "redundant", null] as const)(
    "reloads immediately with a stale or missing waiting worker (%s)",
    (state) => {
      const { registration, workers, registered } = setup();
      if (state) {
        registration.waiting = new Worker();
        registration.waiting.state = state;
      }
      const reload = vi.fn();
      refreshApplication(registered, workers, reload);
      expect(reload).toHaveBeenCalledOnce();
      if (registration.waiting)
        expect(registration.waiting.postMessage).not.toHaveBeenCalled();
    },
  );

  it.each(["controllerchange", "statechange"])(
    "activates a waiting update and reloads once on %s",
    (event) => {
      vi.useFakeTimers();
      const { container, registration, workers, registered } = setup();
      const worker = new Worker();
      worker.state = "installed";
      registration.waiting = worker;
      const reload = vi.fn();
      refreshApplication(registered, workers, reload);
      expect(worker.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
      expect(reload).not.toHaveBeenCalled();
      if (event === "statechange") worker.change("activated");
      container.dispatchEvent(new Event("controllerchange"));
      worker.change("activated");
      vi.runAllTimers();
      expect(reload).toHaveBeenCalledOnce();
    },
  );

  it("reloads within five seconds even when the worker never responds", () => {
    vi.useFakeTimers();
    const { container, registration, workers, registered } = setup();
    registration.waiting = new Worker();
    registration.waiting.state = "installed";
    const reload = vi.fn();
    refreshApplication(registered, workers, reload);
    vi.advanceTimersByTime(4999);
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    container.dispatchEvent(new Event("controllerchange"));
    expect(reload).toHaveBeenCalledOnce();
  });

  it("reloads if posting the activation message fails", () => {
    vi.useFakeTimers();
    const { registration, workers, registered } = setup();
    registration.waiting = new Worker();
    registration.waiting.state = "installed";
    registration.waiting.postMessage.mockImplementation(() => {
      throw new Error("worker unavailable");
    });
    const reload = vi.fn();
    refreshApplication(registered, workers, reload);
    vi.runAllTimers();
    expect(reload).toHaveBeenCalledOnce();
  });

  it("cancels listeners and the fallback timer when the page unmounts", () => {
    vi.useFakeTimers();
    const { container, registration, workers, registered } = setup();
    registration.waiting = new Worker();
    registration.waiting.state = "installed";
    const reload = vi.fn();
    const dispose = refreshApplication(registered, workers, reload);
    dispose();
    container.dispatchEvent(new Event("controllerchange"));
    registration.waiting.change("activated");
    vi.runAllTimers();
    expect(reload).not.toHaveBeenCalled();
  });
});
