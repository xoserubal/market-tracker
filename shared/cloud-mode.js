// Versión en la nube (CLOUD_MODE=1 en server.js): aviso de "solo lectura" en todas las pestañas.
// El servidor pone la cookie mt_cloud=1 al iniciar sesión; en tu PC no existe y este script no hace nada.
// El guardado automático de Portfolio (POST /api/portfolio) se responde aquí con un "ok" falso para que no
// salga un error en cada carga: el aviso fijo deja claro que en la nube nada se guarda. El resto de
// escrituras que haces a propósito (situaciones especiales, etiquetas…) sí devuelven el error del servidor.
(function () {
  if (typeof document === 'undefined' || !/(?:^|;\s*)mt_cloud=1/.test(document.cookie)) return;
  window.MT_CLOUD = true;
  const origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    if (method === 'POST' && /\/api\/portfolio(?:\?|$)/.test(url)) {
      return Promise.resolve(new Response(JSON.stringify({ ok: true, readOnly: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return origFetch(input, init);
  };
  function banner() {
    if (document.getElementById('mt-cloud-banner')) return;
    const b = document.createElement('div');
    b.id = 'mt-cloud-banner';
    b.textContent = 'Versión en la nube · solo lectura: los cambios no se guardan. Para editar, usa tu PC.';
    b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:2000;background:#37474f;color:#fff;' +
      'font:11px Arial,sans-serif;text-align:center;padding:4px 8px;opacity:.92;pointer-events:none';
    document.body.appendChild(b);
    document.body.style.paddingBottom = '22px';
  }
  if (document.body) banner(); else document.addEventListener('DOMContentLoaded', banner);
})();
