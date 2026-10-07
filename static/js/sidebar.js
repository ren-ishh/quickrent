// ── ACTIVE NAV HIGHLIGHTER ─────────────────────────────────────
function setActiveNavItem() {
  const page = window.QR_PAGE || '';
  document.querySelectorAll('[data-page]').forEach(link => {
    if (link.getAttribute('data-page') === page) {
      link.classList.add('nav-active');
      link.classList.remove('nav-item');
    }
  });
}

// ── SIDEBAR SETUP ─────────────────────────────────────────────
// The navigation is a hidden drawer at every breakpoint and is opened
// explicitly from the header. This keeps the workspace focused on content.


// ── MOBILE SIDEBAR TOGGLE ──────────────────────────────────────
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobileOverlay');
  if (!sidebar || !overlay) return;

  const isOpen = !sidebar.classList.contains('-translate-x-full');

  if (isOpen) {
    // Close — slide back off screen
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
    // Re-enable body scroll
    document.body.style.overflow = '';
  } else {
    // Open — slide in
    sidebar.classList.remove('-translate-x-full');
    overlay.classList.remove('hidden');
    // Prevent body scroll while sidebar is open (Android fix)
    document.body.style.overflow = 'hidden';
  }
}

// ── AVATAR DROPDOWN ────────────────────────────────────────────
function toggleAvatarDropdown(e) {
  e.stopPropagation();
  const dropdown = document.getElementById('avatarDropdown');
  if (!dropdown) return;
  dropdown.classList.toggle('hidden');
}

// Close avatar dropdown when clicking anywhere else
document.addEventListener('click', function(e) {
  const dropdown = document.getElementById('avatarDropdown');
  if (dropdown && !dropdown.classList.contains('hidden')) {
    const btn = document.getElementById('avatarBtn');
    if (!dropdown.contains(e.target) && e.target !== btn) {
      dropdown.classList.add('hidden');
    }
  }
});

// ── CLOSE SIDEBAR WHEN NAV LINK TAPPED ON MOBILE ──────────────
// When a nav link is tapped on mobile, close the sidebar
// so the page transition feels smooth
document.addEventListener('click', function(e) {
  const link = e.target.closest('[data-page]');
  if (link) {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (sidebar && !sidebar.classList.contains('-translate-x-full')) {
      sidebar.classList.add('-translate-x-full');
      if (overlay) overlay.classList.add('hidden');
      document.body.style.overflow = '';
    }
  }
});

// ── HANDLE RESIZE ──────────────────────────────────────────────
// If user rotates phone or resizes window, reset sidebar state
window.addEventListener('resize', function() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobileOverlay');
  if (!sidebar) return;

  if (window.innerWidth >= 768) {
    // Keep the drawer closed after a breakpoint change.
    sidebar.classList.add('-translate-x-full');
    sidebar.style.width = '';
    if (overlay) overlay.classList.add('hidden');
    document.body.style.overflow = '';
  } else {
    // Mobile — keep the current drawer state and width.
    sidebar.style.width = '280px';
  }
});

// ── INIT ON LOAD ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function () {
  setActiveNavItem(); // Only highlight the active link, no more fetching!
});
