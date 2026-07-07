const Dashboard = (function() {
  const state = {
    offset: 0,
    limit: 50,
    total: 0,
    endpointFilter: '',
    statusFilter: '',
    ipFilter: '',
    searchQuery: '',
    sortField: '',
    sortDir: 'asc',
    autoRefresh: true,
    refreshTimer: null,
    statsTimer: null
  };

  function init() {
    var params = new URLSearchParams(window.location.search);
    var defaults = window._hermesDefaults || {};
    state.offset = parseInt(params.get('offset')) || 0;
    state.limit = parseInt(params.get('count')) || 50;
    state.endpointFilter = params.get('endpoint') || defaults.endpoint || '';
    state.statusFilter = params.get('status') || defaults.status || '';
    state.ipFilter = params.get('ip') || defaults.ip || '';
    state.searchQuery = params.get('search') || '';

    if (state.endpointFilter) document.getElementById('filter-endpoint').value = state.endpointFilter;
    if (state.statusFilter) document.getElementById('filter-status').value = state.statusFilter;
    if (state.ipFilter) document.getElementById('filter-ip').value = state.ipFilter;
    if (state.searchQuery) document.getElementById('filter-search').value = state.searchQuery;

    fetchStats();
    fetchLogs();
    startTimers();
    populateEndpointFilter();
  }

  function startTimers() {
    stopTimers();
    state.statsTimer = setInterval(fetchStats, 5000);
    state.refreshTimer = setInterval(function() {
      document.getElementById('auto-refresh-status').textContent = 'refreshing...';
      applyFilters(true);
    }, state.autoRefresh ? 10000 : 999999);
    setTimeout(function() {
      document.getElementById('auto-refresh-status').textContent = '';
    }, 2000);
  }

  function stopTimers() {
    clearInterval(state.statsTimer);
    clearInterval(state.refreshTimer);
  }

  function toggleAutoRefresh() {
    state.autoRefresh = document.getElementById('cb-autorefresh').checked;
    if (state.autoRefresh) startTimers(); else stopTimers();
  }

  function buildParams() {
    var p = 'count=' + state.limit + '&offset=' + state.offset;
    if (state.endpointFilter) p += '&endpoint=' + encodeURIComponent(state.endpointFilter);
    if (state.statusFilter) p += '&status=' + encodeURIComponent(state.statusFilter);
    if (state.ipFilter) p += '&ip=' + encodeURIComponent(state.ipFilter);
    if (state.searchQuery) p += '&search=' + encodeURIComponent(state.searchQuery);
    return p;
  }

  function applyFilters(silent) {
    state.endpointFilter = document.getElementById('filter-endpoint').value;
    state.statusFilter = document.getElementById('filter-status').value;
    state.ipFilter = document.getElementById('filter-ip').value;
    state.searchQuery = document.getElementById('filter-search').value;
    state.offset = 0;
    if (silent) { fetchLogs(); return; }
    window.location.search = '?' + buildParams();
  }

  function resetFilters() {
    document.getElementById('filter-endpoint').value = '';
    document.getElementById('filter-status').value = '';
    document.getElementById('filter-ip').value = '';
    document.getElementById('filter-search').value = '';
    state.endpointFilter = '';
    state.statusFilter = '';
    state.ipFilter = '';
    state.searchQuery = '';
    state.offset = 0;
    window.location.search = '';
  }

  function prevPage() {
    if (state.offset >= state.limit) {
      state.offset -= state.limit;
      window.location.search = '?' + buildParams();
    }
  }

  function nextPage() {
    if (state.offset + state.limit < state.total) {
      state.offset += state.limit;
      window.location.search = '?' + buildParams();
    }
  }

  async function fetchLogs() {
    try {
      var res = await fetch('/api/logs?' + buildParams());
      var data = await res.json();
      if (data.entries) renderLogs(data.entries);
      state.total = data.total;
      var start = state.offset + 1;
      var end = state.offset + (data.entries ? data.entries.length : 0);
      document.getElementById('page-info').textContent = 'Showing ' + start + '-' + end + ' of ' + state.total;
      document.getElementById('btn-prev').disabled = state.offset === 0;
      document.getElementById('btn-next').disabled = state.offset + state.limit >= state.total;
      document.getElementById('auto-refresh-status').textContent = 'updated ' + new Date().toLocaleTimeString();
    } catch(e) {}
  }

  async function fetchStats() {
    try {
      var res = await fetch('/api/stats');
      var data = await res.json();
      document.getElementById('stat-total').textContent = data.total || 0;
      document.getElementById('stat-success').textContent = data.success || 0;
      document.getElementById('stat-errors').textContent = data.errors || 0;
      document.getElementById('stat-avg').textContent = (data.avg_duration_ms || 0) + ' ms';
    } catch(e) {}
  }

  function renderLogs(entries) {
    var html = '';
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      var ts = (e.timestamp || '').substring(0, 19).replace('T', ' ');
      var cls = (e.response_status || 500) < 400 ? 'status-ok' : 'status-err';
      html += '<tr class="expand-row" onclick="Dashboard.toggleDetail(this,\'' + e.id + '\')">';
      html += '<td>' + ts + '</td>';
      html += '<td>' + (e.method || '?') + '</td>';
      html += '<td>' + (e.endpoint || '?') + '</td>';
      html += '<td>' + (e.source_ip || '?') + '</td>';
      html += '<td class="' + cls + '">' + (e.response_status || '?') + '</td>';
      html += '<td>' + (e.duration_ms || '?') + '</td>';
      html += '<td>' + (e.command_executed || '') + '</td>';
      html += '</tr>';
      html += '<tr class="detail-row" id="detail-' + e.id + '"><td colspan="7" class="detail-cell"><pre></pre></td></tr>';
    }
    document.getElementById('log-body').innerHTML = html;
    populateEndpointFilter();
  }

  function toggleDetail(tr, id) {
    var detail = document.getElementById('detail-' + id);
    if (!detail) return;
    if (detail.classList.contains('show')) {
      detail.classList.remove('show');
      tr.classList.remove('expanded');
    } else {
      detail.classList.add('show');
      tr.classList.add('expanded');
      var pre = detail.querySelector('pre');
      if (pre && !pre.textContent.trim()) {
        fetch('/api/logs?count=1&search=' + encodeURIComponent(id))
          .then(function(r) { return r.json(); })
          .then(function(d) {
            if (d.entries && d.entries[0]) pre.textContent = JSON.stringify(d.entries[0], null, 2);
          })
          .catch(function() { pre.textContent = 'Error loading details'; });
      }
    }
  }

  function sortBy(field) {
    if (state.sortField === field) {
      state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      state.sortField = field;
      state.sortDir = 'asc';
    }
    document.querySelectorAll('th').forEach(function(el) { el.classList.remove('sorted', 'desc'); });
    var th = document.getElementById('th-' + field.replace(/_/g, '-'));
    if (th) { th.classList.add('sorted'); if (state.sortDir === 'desc') th.classList.add('desc'); }
  }

  function populateEndpointFilter() {
    var eps = {};
    document.querySelectorAll('#log-body tr.expand-row td:nth-child(3)').forEach(function(td) {
      var v = td.textContent.trim();
      if (v && v !== '?') eps[v] = true;
    });
    var sel = document.getElementById('filter-endpoint');
    var current = state.endpointFilter;
    sel.innerHTML = '<option value="">All endpoints</option>';
    Object.keys(eps).sort().forEach(function(e) {
      var o = document.createElement('option');
      o.value = e;
      o.textContent = e;
      if (e === current) o.selected = true;
      sel.appendChild(o);
    });
  }

  async function clearOldLogs() {
    if (!confirm('Delete log entries older than 7 days?')) return;
    try {
      var res = await fetch('/api/clear-logs', { method: 'POST' });
      var data = await res.json();
      alert('Cleaned: ' + (data.removed || 0) + ' entries removed, ' + (data.kept || 0) + ' kept.');
      applyFilters(true);
    } catch(e) { alert('Failed: ' + e); }
  }

  function exportLogs(format) {
    window.open('/api/logs/export?format=' + format + '&' + buildParams(), '_blank');
  }

  return {
    init: init,
    fetchStats: fetchStats,
    fetchLogs: fetchLogs,
    renderLogs: renderLogs,
    toggleDetail: toggleDetail,
    applyFilters: applyFilters,
    resetFilters: resetFilters,
    sortBy: sortBy,
    prevPage: prevPage,
    nextPage: nextPage,
    toggleAutoRefresh: toggleAutoRefresh,
    clearOldLogs: clearOldLogs,
    exportLogs: exportLogs
  };
})();

document.addEventListener('DOMContentLoaded', function() { Dashboard.init(); });
