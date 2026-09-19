/* Debounce JupyterLab kernel-restart commands and show a short status banner. */
(() => {
  const doc = document;
  if (doc.__examKernelGuardCleanup) doc.__examKernelGuardCleanup();
  const selectors = [
    'button[aria-label*="Restart the kernel"]',
    'button[title*="Restart the kernel"]'
  ].join(',');
  let locked = false;
  let unlockTimer = null;
  let hideTimer = null;

  function banner(text, visible=true) {
    let el = doc.getElementById('exam-kernel-status');
    if (!el) {
      el = doc.createElement('div');
      el.id = 'exam-kernel-status';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.style.cssText = 'position:fixed;right:18px;bottom:18px;z-index:100001;max-width:360px;padding:9px 14px;border-radius:7px;background:#102039;color:#fff;box-shadow:0 4px 16px #172b4740;font:13px system-ui;transition:opacity .2s';
      doc.body.appendChild(el);
    }
    clearTimeout(hideTimer);
    el.textContent = text;
    el.style.opacity = visible ? '1' : '0';
    if (visible) hideTimer = setTimeout(() => { el.style.opacity = '0'; }, 3500);
  }

  function onClick(event) {
    if (locked) {
      event.preventDefault();
      event.stopImmediatePropagation();
      banner('内核正在重启，请等待就绪后再操作。');
      return;
    }
    locked = true;
    banner('内核正在重启，界面会自动重新加载…');
    clearTimeout(unlockTimer);
    unlockTimer = setTimeout(() => {
      locked = false;
      banner('内核已就绪，可以继续练习。');
    }, 10000);
  }

  function bind() {
    doc.querySelectorAll(selectors).forEach(button => {
      if (button.dataset.examRestartGuard === '1') return;
      button.dataset.examRestartGuard = '1';
      button.addEventListener('click', onClick, true);
    });
  }

  const observer = new MutationObserver(bind);
  observer.observe(doc.documentElement, {childList:true, subtree:true});
  bind();
  doc.__examKernelGuardCleanup = () => {
    observer.disconnect();
    clearTimeout(unlockTimer);
    clearTimeout(hideTimer);
    doc.getElementById('exam-kernel-status')?.remove();
    doc.querySelectorAll('[data-exam-restart-guard="1"]').forEach(button => {
      button.removeAttribute('data-exam-restart-guard');
    });
  };
})();
