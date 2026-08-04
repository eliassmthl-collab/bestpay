// BestPay Main JS

// Auto-dismiss flash alerts after 5 seconds
document.addEventListener('DOMContentLoaded', function () {
  setTimeout(function () {
    document.querySelectorAll('.flash-container .alert').forEach(function (el) {
      var bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    });
  }, 5000);

  // Mark notifications as read when dropdown opens
  var notifDropdown = document.getElementById('notifDropdown');
  if (notifDropdown) {
    notifDropdown.addEventListener('show.bs.dropdown', function () {
      fetch('/dashboard/notifications/mark-read', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrf_token') }
      });
      // Hide badge
      var badge = notifDropdown.querySelector('.notif-badge');
      if (badge) badge.remove();
    });
  }

  // Copy referral code / link buttons
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

  // Confirm modals via data-confirm attribute
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(this.getAttribute('data-confirm'))) {
        e.preventDefault();
      }
    });
  });
});

// Get CSRF cookie
function getCookie(name) {
  var value = '; ' + document.cookie;
  var parts = value.split('; ' + name + '=');
  if (parts.length === 2) return parts.pop().split(';').shift();
  return '';
}
