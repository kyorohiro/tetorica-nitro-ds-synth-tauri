// SPDX-License-Identifier: BSD-3-Clause
(() => {
  'use strict';

  const packagedOrigin = (location.protocol === 'tauri:' && location.hostname === 'localhost') ||
    (['http:', 'https:'].includes(location.protocol) && location.hostname === 'tauri.localhost');
  if (window.top !== window || !packagedOrigin || typeof window.__TAURI_INTERNALS__?.invoke !== 'function') return;

  const invoke = (command, args) => window.__TAURI_INTERNALS__.invoke(command, args ?? {});
  const status = message => {
    const field = document.getElementById('status');
    if (field) field.textContent = message;
  };

  async function saveExport(blob, filename) {
    if (blob.size > 128 * 1024 * 1024) throw new Error('Export exceeds 128 MiB');
    const header = new TextEncoder().encode(JSON.stringify({ filename }));
    if (header.byteLength > 4096) throw new Error('Export header exceeds 4096 bytes');
    const bytes = new Uint8Array(await blob.arrayBuffer());
    const packet = new Uint8Array(4 + header.byteLength + bytes.byteLength);
    new DataView(packet.buffer).setUint32(0, header.byteLength, true);
    packet.set(header, 4);
    packet.set(bytes, 4 + header.byteLength);
    return invoke('save_export_binary', packet.buffer);
  }

  const exports = new Map();
  const createURL = URL.createObjectURL.bind(URL), revokeURL = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = data => {
    const url = createURL(data);
    if (data instanceof Blob) exports.set(url, data);
    return url;
  };
  URL.revokeObjectURL = url => {
    exports.delete(url);
    return revokeURL(url);
  };
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const blob = exports.get(this.href), filename = this.download;
    if (!filename || !blob) return click.call(this);
    // The Synth revokes its object URL immediately after clicking the anchor.
    void saveExport(blob, filename)
      .then(path => status(path ? `Saved ${path}` : 'Save cancelled.'))
      .catch(error => status(`Could not save: ${error}`));
  };

  function make(tag, value) {
    const element = document.createElement(tag);
    element.textContent = value;
    return element;
  }

  function confirmReload() {
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      dialog.className = 'nds-file-dialog';
      dialog.setAttribute('aria-label', 'Reload Synth');
      const form = document.createElement('form');
      form.method = 'dialog';
      const cancel = make('button', 'Cancel'), reload = make('button', 'Reload');
      cancel.value = 'cancel';
      reload.value = 'reload';
      form.append(make('p', 'Reload Synth? This stops playback and clears the current instrument. Save a preset to keep it.'), cancel, reload);
      dialog.append(form);
      dialog.addEventListener('close', () => {
        dialog.remove();
        resolve(dialog.returnValue === 'reload');
      }, { once: true });
      document.body.append(dialog);
      dialog.showModal();
      cancel.focus();
    });
  }

  function mountControls() {
    const menu = document.querySelector('.toolbar .menu');
    const panel = menu?.querySelector('.menu-panel');
    if (!panel) return;

    const pin = make('button', 'Pin');
    pin.id = 'synthPinButton';
    pin.type = 'button';
    pin.hidden = true;
    const reload = make('button', 'Reload');
    reload.id = 'synthReloadButton';
    reload.type = 'button';
    const desktop = document.createElement('section');
    desktop.className = 'menu-section';
    desktop.setAttribute('aria-label', 'Desktop');
    desktop.append(make('strong', 'Desktop'), reload);
    panel.append(desktop);
    menu.after(pin);

    let pinned = false;
    function updatePin(value) {
      pinned = value === true;
      pin.setAttribute('aria-pressed', String(pinned));
      pin.title = pinned ? 'Unpin window' : 'Pin window on top';
      pin.textContent = pinned ? 'Pinned' : 'Pin';
      pin.hidden = false;
    }
    void invoke('window_pin_state').then(updatePin)
      .catch(error => status(`Could not read window pin state: ${error}`));
    pin.addEventListener('pointerdown', event => event.preventDefault());
    pin.addEventListener('click', async () => {
      pin.disabled = true;
      try { updatePin(await invoke('set_window_pin', { pinned: !pinned })); }
      catch (error) { status(`Could not pin window: ${error}`); }
      finally { pin.disabled = false; }
    });

    reload.addEventListener('click', async () => {
      menu.open = false;
      if (!await confirmReload()) return;
      try { await invoke('reload_window'); }
      catch (error) { status(`Could not reload: ${error}`); }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mountControls, { once: true });
  else mountControls();
})();
