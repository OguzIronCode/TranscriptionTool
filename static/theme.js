// Tema sistemi — FOUC'u önlemek için <head>'de ilk yüklenir
(function () {
  var saved = localStorage.getItem('theme');
  var system = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', saved || 'dark');
})();

function initTheme() {
  var btn = document.getElementById('theme-btn');
  if (!btn) return;
  btn.addEventListener('click', function () {
    var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  });
}
