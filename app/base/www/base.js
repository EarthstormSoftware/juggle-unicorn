// The Earthstorm devices' pages: the API, tabs, the status line, and the settings forms (fields named
// "section.key", filled from GET /api/config and saved to POST /api/config with only what changed).
var Base = (function () {
  var el = function (id) { return document.getElementById(id); };

  function api(path, body) {
    var options = { cache: 'no-store' };
    if (body !== undefined) {
      options.method = 'POST';
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
        return data;
      });
    });
  }

  function duration(s) {
    if (s == null) return 'unknown';
    var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    return d ? d + ' d ' + h + ' h' : h ? h + ' h ' + m + ' min' : m + ' min ' + (s % 60) + ' s';
  }

  function say(id, text, good) {
    var m = el(id);
    if (!m) return;
    m.textContent = text;
    m.className = good ? 'msg good' : 'msg';
  }

  // Tabs: the radios (name="t") and their labels; the chosen one is remembered for the next visit
  function tabs() {
    var radios = document.querySelectorAll('input[name=t]');
    function show() {
      radios.forEach(function (r) {
        var label = document.querySelector('nav label[for=' + r.id + ']');
        var pane = el(r.dataset.pane);
        label.classList.toggle('on', r.checked);
        label.classList.toggle('focus', r.checked && r === document.activeElement && r.matches(':focus-visible'));
        if (pane) pane.classList.toggle('on', r.checked);
      });
    }
    radios.forEach(function (r) {
      r.addEventListener('change', function () {
        try { localStorage.setItem('tab', r.id); } catch (e) {}
        show();
      });
      r.addEventListener('focus', show);
      r.addEventListener('blur', show);
    });
    try {
      var saved = localStorage.getItem('tab');
      if (saved && el(saved)) el(saved).checked = true;
    } catch (e) {}
    show();
  }

  // The settings forms
  var loaded = {};

  function fieldValue(f) {
    if (f.type === 'checkbox') return f.checked;
    if (f.type === 'number' || f.dataset.number !== undefined) return f.value === '' ? null : Number(f.value);
    return f.value;
  }

  function fill(config) {
    loaded = config;
    document.querySelectorAll('form.settings [name]').forEach(function (f) {
      var parts = f.name.split('.'), value = (config[parts[0]] || {})[parts[1]];
      if (f.type === 'password') { f.value = ''; return; }
      if (value === undefined) return;
      if (f.type === 'checkbox') f.checked = !!value; else f.value = value;
    });
    document.querySelectorAll('[data-password-set]').forEach(function (n) {
      var parts = n.dataset.passwordSet.split('.');
      n.hidden = !(config[parts[0]] || {})[parts[1] + '_set'];
    });
  }

  function changes(form) {
    var updates = {}, count = 0;
    form.querySelectorAll('[name]').forEach(function (f) {
      if (f.disabled) return;
      var parts = f.name.split('.'), value = fieldValue(f), before = (loaded[parts[0]] || {})[parts[1]];
      if (f.type === 'password' ? value === '' : value === before) return;
      (updates[parts[0]] = updates[parts[0]] || {})[parts[1]] = value;
      count++;
    });
    return count ? updates : null;
  }

  function loadSettings() {
    return api('/api/config').then(fill);
  }

  // Each form.settings saves its own changes; msgId shows the result
  function settingsForms() {
    document.querySelectorAll('form.settings').forEach(function (form) {
      form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        var msg = form.querySelector('.msg'), updates = changes(form);
        if (!updates) { msg.textContent = 'Nothing has changed'; msg.className = 'msg'; return; }
        api('/api/config', updates).then(function (r) {
          msg.textContent = r.restart_required ? 'Saved: restarting to apply it' : 'Saved';
          msg.className = 'msg good';
          if (r.restart_required) waitForRestart(msg); else loadSettings();
        }).catch(function (e) {
          msg.textContent = 'Not saved: ' + e.message;
          msg.className = 'msg';
        });
      });
    });
    document.querySelectorAll('[data-clear-password]').forEach(function (b) {
      b.addEventListener('click', function () {
        var parts = b.dataset.clearPassword.split('.'), body = {};
        body[parts[0]] = {}; body[parts[0]][parts[1]] = null;
        api('/api/config', body).then(loadSettings);
      });
    });
  }

  function waitForRestart(msg) {
    var tries = 0;
    setTimeout(function poll() {
      api('/api/info').then(function () { location.reload(); }).catch(function () {
        if (++tries < 60) setTimeout(poll, 2000); else if (msg) msg.textContent = "It hasn't come back: reload the page later";
      });
    }, 3000);
  }

  // Restart and reset buttons (data-restart, data-reset with data-confirm)
  function actions() {
    document.querySelectorAll('[data-restart]').forEach(function (b) {
      b.addEventListener('click', function () {
        var msg = el(b.dataset.msg);
        api('/api/restart', {}).then(function () { say(b.dataset.msg, 'Restarting', true); waitForRestart(msg); });
      });
    });
    document.querySelectorAll('[data-reset]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (!confirm(b.dataset.confirm)) return;
        var msg = el(b.dataset.msg);
        api('/api/reset', { confirm: true }).then(function () { say(b.dataset.msg, 'Reset: restarting', true); waitForRestart(msg); })
          .catch(function (e) { say(b.dataset.msg, 'Not reset: ' + e.message); });
      });
    });
  }

  // The header: name, state badge and health chips, from /api/info every few seconds; onInfo(info) for the rest
  function status(onInfo, every) {
    function refresh() {
      api('/api/info').then(function (i) {
        el('name').textContent = i.name;
        document.title = i.name + ' - ' + i.product;
        el('alert').hidden = true;
        var chips = [i.product + ' ' + i.version, 'up ' + duration(i.app_uptime_s != null ? i.app_uptime_s : i.uptime_s)];
        if (i.temperature_c != null) chips.push(i.temperature_c + ' °C');
        if (i.os && i.os.version) chips.push('ApplPi OS ' + i.os.version + (i.os.slot ? ', slot ' + i.os.slot : ''));
        if (i.mqtt && i.mqtt.enabled) {
          chips.push(i.mqtt.connected ? ['MQTT connected', 'ok'] : ['MQTT not connected', 'bad']);
          if (!i.mqtt.connected && i.mqtt.error) {
            el('alert').textContent = 'MQTT: ' + i.mqtt.error;
            el('alert').hidden = false;
          }
        }
        el('health').innerHTML = '';
        chips.forEach(function (c) {
          var s = document.createElement('span');
          s.className = typeof c === 'string' ? 'chip' : 'chip ' + c[1];
          s.textContent = typeof c === 'string' ? c : c[0];
          el('health').appendChild(s);
        });
        if (onInfo) onInfo(i);
      }).catch(function () {
        el('alert').textContent = "The device isn't answering. It may be restarting; this page keeps trying.";
        el('alert').hidden = false;
      });
    }
    refresh();
    return setInterval(refresh, every || 5000);
  }

  function start(onInfo) {
    tabs();
    settingsForms();
    actions();
    loadSettings();
    return status(onInfo);
  }

  return { el: el, api: api, duration: duration, say: say, start: start, loadSettings: loadSettings, status: status };
})();
