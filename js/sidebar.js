function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobileOverlay');
  sidebar.classList.toggle('-translate-x-full');
  overlay.classList.toggle('hidden');
}

window.addEventListener('DOMContentLoaded', function () {
  if (window.innerWidth < 768) {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.add('fixed', 'top-0', 'left-0', 'h-full', '-translate-x-full');
  }
});