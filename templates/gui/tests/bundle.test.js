import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const BUNDLE_FILENAME = 'tiktok2mc-config-bundle.zip';

function makeZipArrayBuffer() {
  const bytes = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0x00]);
  return bytes.buffer;
}

describe('exportConfigBundle', () => {
  beforeEach(() => {
    URL.createObjectURL = () => 'blob:mock';
    URL.revokeObjectURL = () => {};
    HTMLAnchorElement.prototype.click = () => {};
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches the bundle and falls back to a browser download', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => makeZipArrayBuffer(),
      json: async () => ({}),
    }));
    globalThis.fetch = fetchSpy;
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.exportConfigBundle();

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/config-bundle',
      expect.objectContaining({ headers: expect.anything() })
    );
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('saved to'), 'success');
  });

  it('saves via pywebview when download_file_b64 is available', async () => {
    const savePath = 'C:/Users/Test/Downloads/' + BUNDLE_FILENAME;
    const dlSpy = vi.fn(async () => savePath);
    window.pywebview.api.download_file_b64 = dlSpy;
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => makeZipArrayBuffer(),
      json: async () => ({}),
    });
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.exportConfigBundle();

    expect(dlSpy).toHaveBeenCalledTimes(1);
    const [b64, filename] = dlSpy.mock.calls[0];
    expect(filename).toBe(BUNDLE_FILENAME);
    expect(b64.length).toBeGreaterThan(0);
    expect(atob(b64)).toContain('PK');
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining(savePath), 'success');

    delete window.pywebview.api.download_file_b64;
  });

  it('shows an error toast when the export fails', async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 500,
      statusText: 'Server Error',
      json: async () => ({ detail: 'boom' }),
    });
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    await window.exportConfigBundle();

    expect(toastSpy).toHaveBeenCalledWith(expect.any(String), 'error');
  });
});

describe('importConfigBundle', () => {
  beforeEach(() => {
    I18N.setLang('en');
    document.getElementById('confirm-dialog').classList.add('hidden');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uploads the selected bundle after confirmation', async () => {
    const fetchSpy = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ applied: ['config/config.yaml'], count: 1 }),
    }));
    globalThis.fetch = fetchSpy;
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    const input = document.getElementById('bundle-file-input');
    const file = new File(['zip-bytes'], BUNDLE_FILENAME, { type: 'application/zip' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    window.importConfigBundle();
    input.onchange();
    document.getElementById('btn-confirm-ok').click();
    await new Promise(r => setTimeout(r, 0));

    const call = fetchSpy.mock.calls[0];
    expect(call[0]).toBe('/api/v1/config-bundle/import');
    expect(call[1].method).toBe('POST');
    expect(call[1].body).toBeInstanceOf(FormData);
    expect(call[1].body.get('file').name).toBe(BUNDLE_FILENAME);
    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('1'), 'success');
  });

  it('does not upload when the user cancels', async () => {
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy;

    const input = document.getElementById('bundle-file-input');
    const file = new File(['zip-bytes'], BUNDLE_FILENAME, { type: 'application/zip' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    window.importConfigBundle();
    input.onchange();
    document.getElementById('btn-confirm-cancel').click();
    await new Promise(r => setTimeout(r, 0));

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('shows the server error message on a failed import', async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      json: async () => ({ detail: 'invalid actions' }),
    });
    const toastSpy = vi.spyOn(window, 'showToast').mockImplementation(() => {});

    const input = document.getElementById('bundle-file-input');
    const file = new File(['zip-bytes'], BUNDLE_FILENAME, { type: 'application/zip' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });

    window.importConfigBundle();
    input.onchange();
    document.getElementById('btn-confirm-ok').click();
    await new Promise(r => setTimeout(r, 0));

    expect(toastSpy).toHaveBeenCalledWith(expect.stringContaining('invalid actions'), 'error');
  });
});
