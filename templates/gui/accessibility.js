/* ─── ModalFocus: ARIA + focus management for modal overlays ───
   Observes the .wizard-overlay / .editor-overlay visibility (hidden class)
   and on each open: marks the overlay as role=dialog + aria-modal, labels it
   from its first heading, moves focus to the first focusable control and
   traps Tab inside it. On close the focus returns to the triggering element.
   Must be loaded after the DOM (i.e. at the end of <body>). */
const ModalFocus = (() => {
  const OVERLAY_SELECTOR = '.wizard-overlay, .editor-overlay';
  const FOCUSABLE_SELECTOR =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  let _trigger = null;

  function _isVisible(el) {
    return !el.classList.contains('hidden');
  }

  function _focusable(overlay) {
    return Array.from(overlay.querySelectorAll(FOCUSABLE_SELECTOR))
      .filter(n => !n.closest('.hidden'));
  }

  function _ensureLabel(overlay) {
    const heading = overlay.querySelector('h1, h2, h3');
    if (!heading) return;
    if (!heading.id) heading.id = 'modal-title-' + Math.random().toString(36).slice(2, 8);
    overlay.setAttribute('aria-labelledby', heading.id);
  }

  function _onOpen(overlay) {
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    _ensureLabel(overlay);
    if (_trigger == null && document.activeElement && document.activeElement !== document.body) {
      _trigger = document.activeElement;
    }
    const items = _focusable(overlay);
    if (items.length) items[0].focus();
  }

  function _onClose() {
    if (_trigger && _trigger.isConnected && typeof _trigger.focus === 'function') {
      _trigger.focus();
    }
    _trigger = null;
  }

  function _trapTab(e) {
    if (e.key !== 'Tab') return;
    const open = Array.from(document.querySelectorAll(OVERLAY_SELECTOR)).filter(_isVisible);
    const overlay = open[open.length - 1];
    if (!overlay) return;
    const items = _focusable(overlay);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey) {
      if (active === first || !overlay.contains(active)) {
        e.preventDefault();
        last.focus();
      }
    } else if (active === last || !overlay.contains(active)) {
      e.preventDefault();
      first.focus();
    }
  }

  const _observer = new MutationObserver(mutations => {
    for (const m of mutations) {
      if (m.type !== 'attributes' || m.attributeName !== 'class') continue;
      if (_isVisible(m.target)) _onOpen(m.target);
      else _onClose();
    }
  });

  function install() {
    document.querySelectorAll(OVERLAY_SELECTOR).forEach(overlay => {
      _observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });
    });
    document.addEventListener('keydown', _trapTab, true);
  }

  return { install };
})();

ModalFocus.install();
