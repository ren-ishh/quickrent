// Apply saved theme before paint
(function () {
  const saved = localStorage.getItem('qr-theme') || 'light';
  document.documentElement.classList.remove('light', 'dark');
  document.documentElement.classList.add(saved);
})();

function toggleTheme() {
  const html   = document.documentElement;
  const isDark = html.classList.contains('dark');
  html.classList.remove('light', 'dark');
  html.classList.add(isDark ? 'light' : 'dark');
  localStorage.setItem('qr-theme', isDark ? 'light' : 'dark');

  const sun  = document.getElementById('iconSun');
  const moon = document.getElementById('iconMoon');
  if (sun)  sun.classList.toggle('hidden', isDark);
  if (moon) moon.classList.toggle('hidden', !isDark);
}

window.addEventListener('DOMContentLoaded', function () {
  const isDark = document.documentElement.classList.contains('dark');
  const sun    = document.getElementById('iconSun');
  const moon   = document.getElementById('iconMoon');
  if (sun)  sun.classList.toggle('hidden', !isDark);
  if (moon) moon.classList.toggle('hidden', isDark);
});