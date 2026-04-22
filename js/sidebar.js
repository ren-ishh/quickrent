// ─────────────────────────────────────────────
// SIDEBAR LOADER
// This function fetches components/sidebar.html
// and injects it into <div id="sidebar-mount">
// on every page. This is called "dynamic includes"
// ─────────────────────────────────────────────
async function loadSidebar() {
  try {
    // fetch() loads any file like a browser would
    const res = await fetch('components/sidebar.html');
    const html = await res.text();

    // Find the mount point and inject the sidebar HTML
    document.getElementById('sidebar-mount').innerHTML = html;

    // After injecting, mark the correct nav item as active
    setActiveNavItem();

  } catch (e) {
    console.error('Sidebar failed to load:', e);
  }
}

// ─────────────────────────────────────────────
// ACTIVE NAV HIGHLIGHTER
// Each page sets window.QR_PAGE = "bookings" etc.
// This function reads that value and adds the
// nav-active class to the matching nav link
// ─────────────────────────────────────────────
function setActiveNavItem() {
  const page = window.QR_PAGE || '';
  const links = document.querySelectorAll('[data-page]');

  links.forEach(link => {
    if (link.getAttribute('data-page') === page) {
      link.classList.add('nav-active');
      link.classList.remove('nav-item');
    }
  });
}

// ─────────────────────────────────────────────
// MOBILE HAMBURGER TOGGLE
// ─────────────────────────────────────────────
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobileOverlay');
  if (!sidebar) return;
  sidebar.classList.toggle('-translate-x-full');
  overlay.classList.toggle('hidden');
}

// ─────────────────────────────────────────────
// RUN ON EVERY PAGE LOAD
// ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function () {
  loadSidebar();

  // On mobile, sidebar starts hidden off-screen
  if (window.innerWidth < 768) {
    setTimeout(() => {
      const sidebar = document.getElementById('sidebar');
      if (sidebar) sidebar.classList.add('fixed', 'top-0', 'left-0', 'h-full', '-translate-x-full');
    }, 50);
  }
});