// Read saved theme on every page load
(function () {
  const saved = localStorage.getItem('qr-theme') || 'light';
  document.documentElement.classList.remove('light', 'dark');
  document.documentElement.classList.add(saved);
})();

function toggleTheme() {
  const html = document.documentElement;
  const isDark = html.classList.contains('dark');

  // Swap class on <html>
  html.classList.remove('light', 'dark');
  html.classList.add(isDark ? 'light' : 'dark');

  // Save preference
  localStorage.setItem('qr-theme', isDark ? 'light' : 'dark');

  // Swap icon
  document.getElementById('iconSun').classList.toggle('hidden', isDark);
  document.getElementById('iconMoon').classList.toggle('hidden', !isDark);
}

// Set correct icon on load
window.addEventListener('DOMContentLoaded', function () {
  const isDark = document.documentElement.classList.contains('dark');
  document.getElementById('iconSun').classList.toggle('hidden', !isDark);
  document.getElementById('iconMoon').classList.toggle('hidden', isDark);
});