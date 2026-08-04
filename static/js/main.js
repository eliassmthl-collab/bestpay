// BestPay Main JS

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
        var icon = btn.querySelector('i') || btn;
        icon.classList.add('copy-pop', 'copy-success');
        var orig = btn.innerHTML;
        btn.innerHTML = '<i class="fa fa-check"></i>';
        setTimeout(function () {
          btn.innerHTML = orig;
          icon.classList.remove('copy-pop', 'copy-success');
        }, 1800);
      });
    });
  });

  // ── Confirm modals via data-confirm attribute ───────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(this.getAttribute('data-confirm'))) e.preventDefault();
    });
  });

  // ── Live status polling ─────────────────────────────────────────────────────
  // Runs on every page for authenticated users. Polls /dashboard/status every
  // 8 seconds and updates every live element in place — no reload needed.
  if (notifDropdown) {
    startLivePolling();
  }

});

// ── Live Polling Core ────────────────────────────────────────────────────────

var _lastNotifId   = 0;
var _lastBalance   = null;
var _lastRefCount  = null;

function startLivePolling() {
  // Run once immediately, then every 8 seconds
  pollStatus();
  setInterval(pollStatus, 8000);
}

function pollStatus() {
  fetch('/dashboard/status', { credentials: 'same-origin' })
    .then(function (r) { if (r.ok) return r.json(); })
    .catch(function () { return null; })
    .then(function (data) {
      if (!data) return;
      updateBell(data);
      updateBalanceFields(data);
      updateReferralFields(data);
      updateProgressBars(data);
      updateTxnStatuses(data);
      updateWithdrawalStatuses(data);
    });
}

// ── Notification Bell ────────────────────────────────────────────────────────
function updateBell(data) {
  var notifDropdown = document.getElementById('notifDropdown');
  if (!notifDropdown) return;

  // Badge count
  var badge = notifDropdown.querySelector('.notif-badge');
  if (data.unread_count > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'badge bg-danger notif-badge';
      notifDropdown.appendChild(badge);
    }
    badge.textContent = data.unread_count;
  } else {
    if (badge) badge.remove();
  }

  // Dropdown items — skip refresh while the menu is open
  var dropEl = document.querySelector('.notif-dropdown');
  if (dropEl && dropEl.classList.contains('show')) return;

  var notifs     = data.notifications || [];
  var newestId   = notifs.length ? notifs[0].id : 0;
  var isFirstRun = _lastNotifId === 0;

  if (!isFirstRun && newestId > _lastNotifId) {
    // New notification arrived — refresh dropdown & toast
    rebuildNotifDropdown(notifs, dropEl);
    showNotifToast(notifs[0]);
  } else if (isFirstRun) {
    // Seed baseline; also tag existing items so remove works later
    rebuildNotifDropdown(notifs, dropEl);
  }

  if (newestId > 0) _lastNotifId = newestId;
}

function rebuildNotifDropdown(notifs, dropEl) {
  if (!dropEl) return;

  // Remove old items
  dropEl.querySelectorAll('li.notif-list-item').forEach(function (li) { li.remove(); });
  var placeholder = dropEl.querySelector('.notif-placeholder');
  if (placeholder) { var li = placeholder.closest('li'); if (li) li.remove(); }

  var divider    = dropEl.querySelector('li hr.dropdown-divider');
  var insertRef  = divider ? divider.closest('li') : null;

  if (notifs.length === 0) {
    var emptyLi = document.createElement('li');
    emptyLi.className = 'notif-list-item';
    emptyLi.innerHTML = '<span class="dropdown-item-text small text-muted py-3 text-center notif-placeholder">No notifications yet.</span>';
    dropEl.appendChild(emptyLi);
    return;
  }

  notifs.forEach(function (n) {
    var li = document.createElement('li');
    li.className = 'notif-list-item';
    li.innerHTML =
      '<a class="dropdown-item notif-item' + (n.is_read ? '' : ' unread') + '" href="' + escapeHtml(n.link) + '">' +
      '<p class="mb-0 small">' + escapeHtml(n.message) + '</p>' +
      '<span class="text-muted" style="font-size:11px">' + escapeHtml(n.created_at) + '</span>' +
      '</a>';
    if (insertRef && insertRef.nextSibling) {
      dropEl.insertBefore(li, insertRef.nextSibling);
      insertRef = li;
    } else {
      dropEl.appendChild(li);
    }
  });
}

// ── Balance Fields (data-live="balance") ────────────────────────────────────
function updateBalanceFields(data) {
  var formatted = '₦' + data.balance_fmt;
  document.querySelectorAll('[data-live="balance"]').forEach(function (el) {
    if (el.textContent.trim() !== formatted) {
      el.textContent = formatted;
      flashElement(el);
    }
  });
}

// ── Referral Count Fields ────────────────────────────────────────────────────
function updateReferralFields(data) {
  setText('[data-live="referral_count"]', data.referral_count, true);
  setText('[data-live="total_referred"]',  data.total_referred,  true);
  setText('[data-live="active_referrals"]',data.active_referrals,true);
}

// ── Progress Bars & Milestone Messages ──────────────────────────────────────
function updateProgressBars(data) {
  var rc = data.referral_count;

  // 10-referral bar
  var bar10 = document.querySelector('[data-live="progress_10"]');
  if (bar10) bar10.style.width = Math.min(rc / 10 * 100, 100) + '%';

  var msg10 = document.querySelector('[data-live="milestone_10_msg"]');
  if (msg10) {
    var newMsg10 = rc >= 10
      ? '🎉 Milestone reached! ₦10,000 credited.'
      : (10 - rc) + ' more referrals to earn ₦10,000';
    if (msg10.textContent.trim() !== newMsg10) msg10.textContent = newMsg10;
  }

  // Show/hide the 30-referral section
  var wrap30 = document.getElementById('progress30Wrap');
  if (wrap30) {
    wrap30.style.display = rc >= 10 ? '' : 'none';
  }

  // 30-referral bar
  var bar30 = document.querySelector('[data-live="progress_30"]');
  if (bar30) bar30.style.width = Math.min(rc / 30 * 100, 100) + '%';

  var msg30 = document.querySelector('[data-live="milestone_30_msg"]');
  if (msg30) {
    var newMsg30 = rc >= 30
      ? '🏆 Champion! ₦20,000 total earned.'
      : (30 - rc) + ' more for another ₦10,000';
    if (msg30.textContent.trim() !== newMsg30) msg30.textContent = newMsg30;
  }
}

// ── Recent Transactions Table (dashboard home) ───────────────────────────────
function updateTxnStatuses(data) {
  var tbody = document.getElementById('recentTxnsTbody');
  if (!tbody || !data.recent_txns) return;

  data.recent_txns.forEach(function (t) {
    var row = tbody.querySelector('tr[data-txn-id="' + t.id + '"]');
    if (!row) return; // new row — don't add dynamically (would need full re-render)

    var statusCell = row.querySelector('td:last-child span.badge-status');
    if (statusCell) {
      var newClass = 'badge-status badge-' + t.status;
      var newText  = capitalize(t.status);
      if (statusCell.className !== newClass || statusCell.textContent !== newText) {
        statusCell.className   = newClass;
        statusCell.textContent = newText;
        flashElement(statusCell);
      }
    }
  });
}

// ── Withdrawal History Table (withdraw page) ─────────────────────────────────
function updateWithdrawalStatuses(data) {
  var tbody = document.getElementById('withdrawHistoryTbody');
  if (!tbody || !data.recent_withdrawals) return;

  data.recent_withdrawals.forEach(function (w) {
    var row = tbody.querySelector('tr[data-withdrawal-id="' + w.id + '"]');
    if (!row) return;

    var statusCell = row.querySelector('td:last-child');
    if (!statusCell) return;

    var badge = statusCell.querySelector('span.badge-status');
    if (badge) {
      var newClass = 'badge-status badge-' + w.status;
      var newText  = capitalize(w.status);
      if (badge.className !== newClass || badge.textContent !== newText) {
        badge.className   = newClass;
        badge.textContent = newText;
        flashElement(badge);

        // Add / update rejection reason note
        var existing = statusCell.querySelector('small.text-muted');
        if (w.status === 'rejected' && w.rejection_reason) {
          if (!existing) {
            var note = document.createElement('small');
            note.className = 'text-muted';
            statusCell.appendChild(document.createElement('br'));
            statusCell.appendChild(note);
            existing = note;
          }
          existing.textContent = w.rejection_reason;
        } else if (existing) {
          var br = statusCell.querySelector('br');
          if (br) br.remove();
          existing.remove();
        }
      }
    }
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

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

/** Update text of every element matching selector. Flashes on change. */
function setText(selector, value, flash) {
  var v = String(value);
  document.querySelectorAll(selector).forEach(function (el) {
    if (el.textContent.trim() !== v) {
      el.textContent = v;
      if (flash) flashElement(el);
    }
  });
}

/** Briefly highlight an element to draw attention to a changed value. */
function flashElement(el) {
  el.style.transition = 'opacity 0.15s';
  el.style.opacity    = '0.3';
  setTimeout(function () { el.style.opacity = '1'; }, 180);
}

/** Slide-in toast at bottom-right for new notifications. */
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
