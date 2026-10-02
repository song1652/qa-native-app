// TC 스튜디오 — API 클라이언트 (agents/dashboard/routes_tc_library.py와 1:1)
(function (NS) {
  'use strict';

  const enc = encodeURIComponent;

  async function request(method, path, body) {
    const init = { method, headers: {} };
    if (body instanceof Blob) {
      init.body = body;
      init.headers['Content-Type'] = 'application/octet-stream';
    } else if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers['Content-Type'] = 'application/json';
    }
    const res = await fetch(path, init);
    const data = await res.json().catch(() => ({ ok: false, code: 'BAD_RESPONSE' }));
    if (!res.ok) {
      const err = new Error(data.error || res.statusText);
      err.status = res.status;
      err.code = data.code;
      err.data = data;
      throw err;
    }
    return data;
  }

  const S = (suite) => `/api/tc-library/${enc(suite)}`;
  const C = (suite, id) => `${S(suite)}/cases/${enc(id)}`;

  NS.api = {
    suites: () => request('GET', '/api/tc-library'),
    startBlank: () => request('POST', '/api/tc-library/starter'),
    deleteSuite: (suite) => request('DELETE', `${S(suite)}?confirm=${enc(suite)}`),
    trash: () => request('GET', '/api/tc-library/trash'),
    purgeTrash: (id, suite) => request('DELETE', `/api/tc-library/trash/${enc(id)}?confirm=${enc(suite)}`),
    restoreTrash: (id) => request('POST', `/api/tc-library/trash/${enc(id)}/restore`),
    addSheet: (suite, name) => request('POST', `${S(suite)}/sheets`, { name }),
    renameSheet: (suite, sheet, name) => request('POST', `${S(suite)}/sheets/rename`, { sheet, name }),
    addBranch: (suite, sheet, path) => request('POST', `${S(suite)}/branches`, { sheet, path }),
    tree: (suite) => request('GET', `${S(suite)}/tree`),
    list: (suite, query) => request('GET', `${S(suite)}?${new URLSearchParams(query)}`),
    getCase: (suite, id) => request('GET', C(suite, id)),
    patchCase: (suite, id, rev, changes) => request('PATCH', C(suite, id), { rev, ...changes }),
    createCase: (suite, fields) => request('POST', `${S(suite)}/cases`, fields),
    duplicate: (suite, id) => request('POST', `${C(suite, id)}/duplicate`),
    deleteCase: (suite, id, rev) => request('DELETE', `${C(suite, id)}?rev=${rev}`),
    restore: (suite, id) => request('POST', `${C(suite, id)}/restore`),
    history: (suite, id) => request('GET', `${C(suite, id)}/history`),
    revert: (suite, id, historyId, rev) =>
      request('POST', `${C(suite, id)}/revert`, { history_id: historyId, rev }),
    bulk: (suite, items, op, field, value) =>
      request('POST', `${S(suite)}/bulk`, { items, op, field, value }),
    move: (suite, items, sheet, path, feature) =>
      request('POST', `${S(suite)}/move`, { items, sheet, path, feature }),
    importPreview: (file, mapping) =>
      request('POST', `/api/tc-library/import/preview?filename=${enc(file.name)}${mapping ? `&mapping=${enc(JSON.stringify(mapping))}` : ''}`, file),
    importCommit: (payload) => request('POST', '/api/tc-library/import', payload),
    importPlan: (payload) => request('POST', '/api/tc-library/import/plan', payload),
    importRuns: () => request('GET', '/api/tc-library/import/runs'),
    importRun: (id) => request('GET', `/api/tc-library/import/runs/${enc(id)}`),
    rollbackImport: (id) => request('POST', `/api/tc-library/import/runs/${enc(id)}/rollback`),
    saveMappingProfile: (payload) => request('POST', '/api/tc-library/import/mapping-profiles', payload),
    updateMappingProfile: (id, payload) => request('PUT', `/api/tc-library/import/mapping-profiles/${enc(id)}`, payload),
    deleteMappingProfile: (id) => request('DELETE', `/api/tc-library/import/mapping-profiles/${enc(id)}`),
    mdImportRuns: () => request('GET', '/api/tc-library/import/md-runs'),
    mdImportRun: (id) => request('GET', `/api/tc-library/import/md-runs/${enc(id)}`),
    rollbackMdImport: (id) => request('POST', `/api/tc-library/import/md-runs/${enc(id)}/rollback`),
    exportXlsx: (suite, payload) => request('POST', `${S(suite)}/export/xlsx`, payload),
    downloadUrl: (exportId) => `/api/tc-library/exports/${enc(exportId)}/download`,
    // ── Phase 2: 소스·프로필·생성 작업·검토 ──
    newBundle: () => request('POST', '/api/tc-library/sources'),
    bundle: (bundleId) => request('GET', `/api/tc-library/sources/${enc(bundleId)}`),
    addSourceFile: (bundleId, file) =>
      request('POST', `/api/tc-library/sources/${enc(bundleId)}/file?filename=${enc(file.name)}`, file),
    addSourcePaste: (bundleId, text) => request('POST', `/api/tc-library/sources/${enc(bundleId)}/paste`, { text }),
    removeSource: (bundleId, sourceId) => request('DELETE', `/api/tc-library/sources/${enc(bundleId)}/${enc(sourceId)}`),
    excerpt: (bundleId, ref) => request('GET', `/api/tc-library/sources/${enc(bundleId)}/excerpt?ref=${enc(ref)}`),
    profiles: () => request('GET', '/api/tc-library/profiles'),
    styleFromXlsx: (file) => request('POST', '/api/tc-library/profiles/style-from-xlsx', file),
    saveProfile: (name, fields) => request('PUT', `/api/tc-library/profiles/${enc(name)}`, fields),
    startJob: (suite, payload) => request('POST', `${S(suite)}/jobs`, payload),
    job: (jobId) => request('GET', `/api/tc-library/jobs/${enc(jobId)}`),
    authoringContext: (suite) => request('GET', `${S(suite)}/authoring-context`),
    cancelJob: (jobId) => request('POST', `/api/tc-library/jobs/${enc(jobId)}/cancel`),
    coverage: (suite, sheet, path, profile) =>
      request('GET', `${S(suite)}/coverage?${new URLSearchParams({ sheet, path: path.join('/'), profile })}`),
    resolveDuplicate: (suite, id, payload) => request('POST', `${C(suite, id)}/resolve-duplicate`, payload),
    mappingProfiles: () => request('GET', '/api/tc-library/import/mapping-profiles'),
    // ── Phase 3: 원격 소스·자격증명·출처 변경 ──
    addSourceUrl: (bundleId, url) => request('POST', `/api/tc-library/sources/${enc(bundleId)}/url`, { url }),
    addSourceConfluence: (bundleId, url, children) =>
      request('POST', `/api/tc-library/sources/${enc(bundleId)}/confluence`, { url, children }),
    addSourceFigma: (bundleId, url) => request('POST', `/api/tc-library/sources/${enc(bundleId)}/figma`, { url }),
    credentials: () => request('GET', '/api/tc-library/credentials'),
    saveCredentials: (kind, fields) => request('PUT', `/api/tc-library/credentials/${enc(kind)}`, fields),
    sourceChanges: (suite) => request('GET', `${S(suite)}/source-changes`),
    scanSources: (suite) => request('POST', `${S(suite)}/source-changes/scan`),
    sourceDiff: (ref) => request('GET', `/api/tc-library/source-diff?ref=${enc(ref)}`),
    ackSource: (suite, id) => request('POST', `${C(suite, id)}/ack-source`),
    // ── Phase 4: md 내보내기 ──
    mdEligibility: (suite) => request('GET', `${S(suite)}/export/md/eligibility`),
    saveMdGroup: (suite, path, group, code) => request('PUT', `${S(suite)}/md-groups`, { path, group, code }),
    mdPreview: (suite) => request('POST', `${S(suite)}/export/md`),
    mdCommit: (suite, runId, skip, overwrite) => request('POST', `${S(suite)}/md-exports/${enc(runId)}/commit`, { skip, policy: overwrite ? 'overwrite' : 'skip-conflict' }),
    mdRollback: (suite, runId) => request('POST', `${S(suite)}/md-exports/${enc(runId)}/rollback`),
  };
})(window.TCS_NS = window.TCS_NS || {});
