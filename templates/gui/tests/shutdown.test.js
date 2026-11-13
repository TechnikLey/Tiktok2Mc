import { describe, it, expect, vi, afterEach } from 'vitest';

/** Replace the pywebview bridge with a minimal fake for one test. */
function _fakeBridge(requestResult) {
  globalThis.pywebview = {
    api: {
      request_shutdown: vi.fn(async () => requestResult),
      close_app: vi.fn(async () => 'closing'),
    },
  };
  return globalThis.pywebview.api;
}

describe('_closeWindowForShutdown', () => {
  afterEach(() => {
    delete globalThis.pywebview;
    vi.restoreAllMocks();
  });

  it('requests the signed API shutdown before closing the window', async () => {
    const api = _fakeBridge('requested');
    const closeSpy = vi.spyOn(window, 'close').mockImplementation(() => {});

    await window._closeWindowForShutdown();

    expect(api.request_shutdown).toHaveBeenCalledTimes(1);
    expect(closeSpy).toHaveBeenCalledTimes(1);
    expect(api.close_app).toHaveBeenCalledTimes(1);
  });

  it('keeps the window open and shows an error when the API rejects', async () => {
    const api = _fakeBridge('error:no_secret');
    const closeSpy = vi.spyOn(window, 'close').mockImplementation(() => {});
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});
    document.getElementById('shutdown-overlay').classList.remove('hidden');

    await window._closeWindowForShutdown();

    expect(closeSpy).not.toHaveBeenCalled();
    expect(api.close_app).not.toHaveBeenCalled();
    expect(document.getElementById('shutdown-overlay').classList.contains('hidden')).toBe(true);
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('Could not stop'), 'error');
  });

  it('falls back to closing the window without a pywebview bridge', async () => {
    const closeSpy = vi.spyOn(window, 'close').mockImplementation(() => {});

    await window._closeWindowForShutdown();

    expect(closeSpy).toHaveBeenCalledTimes(1);
  });
});
