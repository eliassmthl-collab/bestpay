// BestPay Main JS — WebSocket Edition

document.addEventListener('DOMContentLoaded', function () {

  // ── Auto-dismiss flash alerts after 5 seconds ──────────────────────────────
  setTimeout(function () {
    document.querySelectorAll('.flash-container .alert').forEach(function (el) {
      bootstrap.Alert.getOrCreateInstance(el).close();
    });
  }, 5000);

  // ── Mark notifications as read when dropdown opens ─────────────────────────
  var notifDropdown = document.getElementById('notifDropdown');
  if (notifDropdown) {
    notifDropdown.addEventListener('show.bs.dropdown', function () {
      fetch('/dashboard/notifications/mark-read', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrf_token') }
      });
      var badge = notifDropdown.querySelector('.notif-badge');
      if (badge) badge.remove();
    });
  }

  // ── Copy referral code / link buttons ──────────────────────────────────────
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var text = this.getAttribute('data-copy');
      navigator.clipboard.writeText(text).then(function () {
        var orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa fa-check"></i>';
        setTimeout(function () { btn.innerHTML = orig; }, 1800);
      });
    });
  });

  // ── Confirm modals via data-confirm attribute ───────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(this.getAttribute('data-confirm'))) e.preventDefault();
    });
  });

  // ── SocketIO Real-Time Connection ───────────────────────────────────────────
  // Only connect for authenticated users (notifDropdown is present on auth pages)
  if (notifDropdown && typeof io !== 'undefined') {
    initSocketIO();
  }

});

// ── SocketIO Core ────────────────────────────────────────────────────────────

var _socket = null;

function initSocketIO() {
  _socket = io({
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 10,
  });

  _socket.on('connect', function () {
    _socket.emit('join');
  });

  _socket.on('disconnect', function () {
    // Silently reconnects via reconnection config above
  });

  // ── Incoming event handlers ──────────────────────────────────────────────

  // New notification pushed by server
  _socket.on('new_notification', function (data) {
    incrementBellBadge();
    prependNotifDropdownItem(data);
    showNotifToast(data);
  });

  // Balance updated (credit, withdrawal refund, admin edit)
  _socket.on('balance_update', function (data) {
    updateBalanceFields(data);
  });

  // Account approved
  _socket.on('account_approved', function (data) {
    // Fire a DOM event so the activate page can react
    document.dispatchEvent(new CustomEvent('bestpay:account_approved', { detail: data }));
    // Redirect to dashboard if on activate page
    if (window.location.pathname.indexOf('/activate') !== -1) {
      setTimeout(function () { window.location.href = '/dashboard'; }, 2500);
    }
  });

  // Withdrawal status changed
  _socket.on('withdrawal_update', function (data) {
    updateWithdrawalRow(data);
    if (data.balance_fmt) {
      updateBalanceFields(data);
    }
  });

  // Admin room: new payment submitted
  _socket.on('new_notification', function (data) {
    // Also flash admin bell badge if on admin pages
    var adminBell = document.getElementById('adminNotifBell');
    if (adminBell) incrementAdminBell(adminBell);
  });
}

// ── Bell Badge ───────────────────────────────────────────────────────────────

function incrementBellBadge() {
  var notifDropdown = document.getElementById('notifDropdown');
  if (!notifDropdown) return;
  var badge = notifDropdown.querySelector('.notif-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'badge bg-danger notif-badge';
    notifDropdown.appendChild(badge);
    badge.textContent = '1';
  } else {
    var count = parseInt(badge.textContent || '0', 10);
    badge.textContent = count + 1;
  }
}

function incrementAdminBell(bellEl) {
  var badge = bellEl.querySelector('.notif-badge');
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'badge bg-danger notif-badge';
    bellEl.appendChild(badge);
    badge.textContent = '1';
  } else {
    var count = parseInt(badge.textContent || '0', 10);
    badge.textContent = count + 1;
  }
}

// ── Notification Dropdown ─────────────────────────────────────────────────────

function prependNotifDropdownItem(n) {
  var dropEl = document.querySelector('.notif-dropdown');
  if (!dropEl) return;

  // Remove "no notifications" placeholder if present
  var placeholder = dropEl.querySelector('.notif-placeholder');
  if (placeholder) {
    var li = placeholder.closest('li');
    if (li) li.remove();
  }

  var divider = dropEl.querySelector('li hr.dropdown-divider');
  var insertAfter = divider ? divider.closest('li') : null;

  var li = document.createElement('li');
  li.className = 'notif-list-item';
  li.innerHTML =
    '<a class="dropdown-item notif-item unread" href="' + escapeHtml(n.link) + '">' +
    '<p class="mb-0 small">' + escapeHtml(n.message) + '</p>' +
    '<span class="text-muted" style="font-size:11px">' + escapeHtml(n.created_at || '') + '</span>' +
    '</a>';

  if (insertAfter && insertAfter.nextSibling) {
    dropEl.insertBefore(li, insertAfter.nextSibling);
  } else {
    dropEl.appendChild(li);
  }

  // Keep at most 5 items
  var items = dropEl.querySelectorAll('li.notif-list-item');
  if (items.length > 5) {
    items[items.length - 1].remove();
  }
}

// ── Balance Fields ────────────────────────────────────────────────────────────

function updateBalanceFields(data) {
  if (!data.balance_fmt) return;
  var formatted = '₦' + data.balance_fmt;
  document.querySelectorAll('[data-live="balance"]').forEach(function (el) {
    if (el.textContent.trim() !== formatted) {
      el.textContent = formatted;
      flashElement(el);
    }
  });
}

// ── Withdrawal Row ────────────────────────────────────────────────────────────

function updateWithdrawalRow(data) {
  var tbody = document.getElementById('withdrawHistoryTbody');
  if (!tbody) return;
  var row = tbody.querySelector('tr[data-withdrawal-id="' + data.withdrawal_id + '"]');
  if (!row) return;

  var badge = row.querySelector('span.badge-status');
  if (badge) {
    badge.className = 'badge-status badge-' + data.status;
    badge.textContent = capitalize(data.status);
    flashElement(badge);

    var statusCell = badge.closest('td');
    if (statusCell) {
      var existing = statusCell.querySelector('small.text-muted');
      if (data.status === 'rejected' && data.rejection_reason) {
        if (!existing) {
          statusCell.appendChild(document.createElement('br'));
          existing = document.createElement('small');
          existing.className = 'text-muted';
          statusCell.appendChild(existing);
        }
        existing.textContent = data.rejection_reason;
      } else if (existing) {
        var br = statusCell.querySelector('br');
        if (br) br.remove();
        existing.remove();
      }
    }
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showNotifToast(notif) {
  var container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.cssText = 'position:fixed;bottom:1.25rem;right:1.25rem;z-index:9999;display:flex;flex-direction:column;gap:0.5rem';
    document.body.appendChild(container);
  }

  var toast = document.createElement('div');
  toast.className = 'toast show align-items-center text-white border-0 shadow';
  toast.style.cssText = 'background:var(--dark-card,#1e1e2e);min-width:280px;max-width:340px;border-left:3px solid var(--gold,#e2b714)!important;border-radius:0.75rem;';
  toast.setAttribute('role', 'alert');
  toast.innerHTML =
    '<div class="d-flex">' +
    '<div class="toast-body py-3 px-3" style="cursor:pointer">' +
    '<div class="d-flex align-items-start gap-2">' +
    '<i class="fa fa-bell text-warning mt-1 flex-shrink-0"></i>' +
    '<div><div class="fw-600 small mb-1">New Notification</div>' +
    '<div class="small text-white-75">' + escapeHtml(notif.message) + '</div></div>' +
    '</div></div>' +
    '<button type="button" class="btn-close btn-close-white me-2 m-auto" aria-label="Close"></button>' +
    '</div>';

  toast.querySelector('.btn-close').addEventListener('click', function () { toast.remove(); });
  toast.querySelector('.toast-body').addEventListener('click', function () {
    window.location.href = notif.link || '/dashboard/notifications';
  });

  container.appendChild(toast);
  setTimeout(function () {
    toast.style.transition = 'opacity 0.4s';
    toast.style.opacity = '0';
    setTimeout(function () { toast.remove(); }, 400);
  }, 7000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getCookie(name) {
  var v = '; ' + document.cookie;
  var p = v.split('; ' + name + '=');
  if (p.length === 2) return p.pop().split(';').shift();
  return '';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

function flashElement(el) {
  el.style.transition = 'opacity 0.15s';
  el.style.opacity = '0.3';
  setTimeout(function () { el.style.opacity = '1'; }, 180);
}
