// ── SIDEBAR LOADER ─────────────────────────────────────────────
async function loadSidebar() {
  try {
    const res  = await fetch('/components/sidebar');
    const html = await res.text();
    document.getElementById('sidebar-mount').innerHTML = html;
    setActiveNavItem();
  } catch (e) {
    console.error('Sidebar failed to load:', e);
  }
}

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

// ── MOBILE SIDEBAR TOGGLE ──────────────────────────────────────
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobileOverlay');
  if (!sidebar || !overlay) return;

  const isOpen = !sidebar.classList.contains('-translate-x-full');

  if (isOpen) {
    // Close
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
  } else {
    // Open
    sidebar.classList.remove('-translate-x-full');
    overlay.classList.remove('hidden');
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
  const btn      = document.getElementById('avatarBtn');
  if (dropdown && !dropdown.classList.contains('hidden')) {
    if (!dropdown.contains(e.target) && e.target !== btn) {
      dropdown.classList.add('hidden');
    }
  }
});

// ── INIT ON LOAD ───────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', function () {
  loadSidebar();

  // On mobile — sidebar starts hidden
  if (window.innerWidth < 768) {
    setTimeout(() => {
      const sidebar = document.getElementById('sidebar');
      if (sidebar) {
        sidebar.classList.add(
          'fixed', 'top-0', 'left-0', 'h-full', '-translate-x-full'
        );
      }
    }, 50);
  }
});