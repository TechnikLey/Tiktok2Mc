import { describe, it, expect, beforeEach, afterEach } from 'vitest';

/**
 * Shared regression tests for the hook and builtin schema editors. Both mirror
 * the plugin editor and keep raw-JSON parse errors in `collectErrors`.
 */
function registerEditorTests(label, getEditor, rawFieldId, foreignFieldId = rawFieldId) {
  describe(label, () => {
    let editor;
    let rawField;

    beforeEach(() => {
      editor = getEditor();
      editor.hookName = null;
      editor.displayName = null;
      editor.config = {};
      editor.schema = null;
      editor.original = {};
      editor.errors.clear();
      editor.collectErrors.clear();
      editor.searchQuery = '';
      editor.hasSchema = false;
      // The hook editor's legacy section is not part of index.html anymore;
      // give it a detached container so the shared tests can exercise it.
      editor.content = editor.content || document.createElement('div');
      editor.content.innerHTML = '';
      rawField = document.createElement('textarea');
      rawField.id = rawFieldId;
      editor.content.appendChild(rawField);
    });

    afterEach(() => {
      editor.content.innerHTML = '';
    });

    describe('collect', () => {
      it('clears stale parse errors when a JSON field leaves the DOM', () => {
        editor.hasSchema = true;
        editor.schema = { fields: [{ key: 'settings', type: 'json' }] };
        const field = document.createElement('textarea');
        field.setAttribute('data-path', 'settings');
        field.setAttribute('data-type', 'json');
        field.value = '{invalid}';
        editor.content.appendChild(field);

        editor.collect();
        expect(editor.collectErrors.has('settings')).toBe(true);
        expect(editor.validate()).toBe(false);

        // Removing the field (array item, search filter, advanced mode) must not
        // leave an invisible error that blocks saving.
        field.remove();
        editor.collect();
        expect(editor.collectErrors.size).toBe(0);
        expect(editor.validate()).toBe(true);
      });
    });

    describe('parseRawJson', () => {
      it('parses a JSON object', () => {
        rawField.value = '{"key": "value"}';
        editor.parseRawJson();
        expect(editor.config.key).toBe('value');
      });

      it('keeps the config on invalid JSON', () => {
        editor.config = { original: true };
        rawField.value = '{invalid}';
        editor.parseRawJson();
        expect(editor.config).toEqual({ original: true });
      });

      it('rejects JSON values that are not objects', () => {
        editor.config = { original: true };
        for (const raw of ['[]', '"text"', '42', 'null']) {
          rawField.value = raw;
          editor.parseRawJson();
          expect(editor.config).toEqual({ original: true });
        }
      });

      it('reads its own field instead of a same-named field elsewhere', () => {
        // The dashboard keeps every editor section in the DOM. A global id
        // lookup could therefore read another editor's raw JSON field.
        const foreign = document.createElement('textarea');
        foreign.id = foreignFieldId;
        foreign.value = '{"foreign": true}';
        document.body.insertBefore(foreign, document.body.firstChild);
        rawField.value = '{"own": true}';

        editor.parseRawJson();
        expect(editor.config).toEqual({ own: true });
        foreign.remove();
      });

      it('does nothing when the raw field is missing', () => {
        editor.content.innerHTML = '';
        editor.config = { original: true };
        expect(() => editor.parseRawJson()).not.toThrow();
        expect(editor.config).toEqual({ original: true });
      });
    });
  });
}

registerEditorTests('HookConfigEditor', () => hookEditor, 'hook-raw-json');
registerEditorTests(
  'BuiltinConfigEditor',
  () => builtinEditor,
  'builtin-raw-json',
  'hook-raw-json'
);
