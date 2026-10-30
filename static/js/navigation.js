/* Warm same-origin GET pages on intent so server-rendered routes are ready
   sooner when people move between rental screens. */
(function () {
  if (!('relList' in document.createElement('link')) ||
      !document.createElement('link').relList.supports('prefetch')) return;

  const warmed = new Set();
  function warm(anchor) {
    if (!anchor || anchor.target || anchor.hasAttribute('download')) return;
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin || url.pathname === location.pathname ||
        url.pathname === '/logout' || url.pathname === '/customer/logout' ||
        url.pathname.startsWith('/api/')) return;
    const key = url.href;
    if (warmed.has(key) || warmed.size >= 6) return;
    warmed.add(key);
    const hint = document.createElement('link');
    hint.rel = 'prefetch';
    hint.as = 'document';
    hint.href = key;
    document.head.appendChild(hint);
  }

  document.addEventListener('pointerover', function (event) {
    if (event.pointerType === 'touch') return;
    warm(event.target.closest('a[href]'));
  }, { passive: true });
  document.addEventListener('pointerdown', function (event) {
    warm(event.target.closest('a[href]'));
  }, { passive: true });
  document.addEventListener('focusin', function (event) {
    warm(event.target.closest('a[href]'));
  });
  document.addEventListener('touchstart', function (event) {
    warm(event.target.closest('a[href]'));
  }, { passive: true });

  /* Warm the main customer destinations after the first paint. This makes
     bottom-bar navigation feel immediate without competing with rendering. */
  window.addEventListener('load', function () {
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (connection && (connection.saveData || /2g/.test(connection.effectiveType || ''))) return;
    const warmMainRoutes = function () {
      document.querySelectorAll('.bottom-nav a[href]').forEach(warm);
    };
    if ('requestIdleCallback' in window) requestIdleCallback(warmMainRoutes, { timeout: 1400 });
    else window.setTimeout(warmMainRoutes, 900);
  }, { once: true });
})();
