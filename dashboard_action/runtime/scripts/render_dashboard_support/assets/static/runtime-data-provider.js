    function createDashboardDataProvider(input) {
      const isLazy = !!(input && input.summary && (input.loadRepoChunk || input.chunks));
      const isEncrypted = !!(input && input.loadRepoChunk);
      const source = isLazy ? input.summary : (input || {});
      const loadedChunks = {};
      const pendingChunks = {};
      function chunkFor(repoName) {
        return loadedChunks[repoName] || null;
      }
      function chunkIdFor(repoName) {
        return source.repo_chunks?.[repoName] || null;
      }
      function validateRepoChunk(repoName, chunk) {
        if (!chunk || typeof chunk !== 'object') {
          throw dashboardChunkError('schema', 'Dashboard chunk was not an object.', {
            repoName,
            chunkId: chunkIdFor(repoName) || '',
            mode: isEncrypted ? 'encrypted' : 'plaintext',
            summaryDecrypted: isEncrypted
          });
        }
        if (chunk.repo !== repoName) {
          throw dashboardChunkError('schema', 'Dashboard chunk did not match requested repo.', {
            repoName,
            chunkId: chunkIdFor(repoName) || '',
            mode: isEncrypted ? 'encrypted' : 'plaintext',
            summaryDecrypted: isEncrypted
          });
        }
        ['repo_series', 'repo_weekday', 'repo_referrers', 'repo_paths', 'growth'].forEach((field) => {
          if (!(field in chunk)) {
            throw dashboardChunkError('schema', 'Dashboard chunk was missing required field: ' + field + '.', {
              repoName,
              chunkId: chunkIdFor(repoName) || '',
              mode: isEncrypted ? 'encrypted' : 'plaintext',
              summaryDecrypted: isEncrypted,
              missingField: field
            });
          }
        });
        return chunk;
      }
      function parsePlainChunk(repoName) {
        const chunkId = chunkIdFor(repoName);
        if (!chunkId || !input.chunks?.[chunkId]) {
          throw dashboardChunkError('missing', 'Dashboard chunk was missing.', {
            repoName,
            chunkId: chunkId || '',
            mode: 'plaintext',
            summaryDecrypted: false
          });
        }
        const rawChunk = input.chunks[chunkId];
        let chunk;
        try {
          chunk = typeof rawChunk === 'string' ? JSON.parse(rawChunk) : rawChunk;
        } catch (error) {
          throw dashboardChunkError('parse', error.message || 'Dashboard chunk was not valid JSON.', {
            repoName,
            chunkId,
            mode: 'plaintext',
            summaryDecrypted: false,
            originalName: error.name || '',
            originalMessage: error.message || String(error)
          });
        }
        return validateRepoChunk(repoName, chunk);
      }
      function loadChunk(repoName) {
        if (input.loadRepoChunk) {
          return input.loadRepoChunk(repoName).then((chunk) => validateRepoChunk(repoName, chunk));
        }
        return Promise.resolve(parsePlainChunk(repoName));
      }
      return {
        getPayload: function() { return source; },
        isLazy: function() { return isLazy; },
        isEncrypted: function() { return isEncrypted; },
        getMeta: function() { return source.meta || {}; },
        getRepos: function() { return source.repos || []; },
        getRepoChunkId: function(repoName) { return chunkIdFor(repoName); },
        getRepoSummary: function(repoName) {
          return (source.repos || []).find((repo) => repo.name === repoName) || {};
        },
        getRepoSeries: function(repoName) {
          return chunkFor(repoName)?.repo_series || source.repo_series?.[repoName] || {};
        },
        getRepoWeekday: function(repoName) {
          return chunkFor(repoName)?.repo_weekday || source.repo_weekday?.[repoName] || {};
        },
        getRepoGrowth: function(repoName) {
          const chunkGrowth = chunkFor(repoName)?.growth || {};
          const row = chunkGrowth.per_repo || source.growth?.per_repo?.[repoName] || {};
          if (!row.series && chunkGrowth.series) {
            return Object.assign({}, row, { series: chunkGrowth.series });
          }
          return row;
        },
        getRepoReferrers: function(repoName) {
          return chunkFor(repoName)?.repo_referrers || source.repo_referrers?.[repoName] || [];
        },
        getRepoPaths: function(repoName) {
          return chunkFor(repoName)?.repo_paths || source.repo_paths?.[repoName] || [];
        },
        getReferrersByRepo: function() {
          if (!isLazy) return source.repo_referrers || {};
          return Object.fromEntries(
            Object.keys(loadedChunks).map((repoName) => [
              repoName,
              loadedChunks[repoName].repo_referrers || []
            ])
          );
        },
        getPathsByRepo: function() {
          if (!isLazy) return source.repo_paths || {};
          return Object.fromEntries(
            Object.keys(loadedChunks).map((repoName) => [
              repoName,
              loadedChunks[repoName].repo_paths || []
            ])
          );
        },
        isRepoLoaded: function(repoName) {
          return !isLazy || !!loadedChunks[repoName];
        },
        loadRepo: function(repoName) {
          if (!isLazy || !repoName || loadedChunks[repoName]) {
            return Promise.resolve(loadedChunks[repoName] || null);
          }
          if (!pendingChunks[repoName]) {
            pendingChunks[repoName] = loadChunk(repoName).then((chunk) => {
              loadedChunks[repoName] = chunk;
              delete pendingChunks[repoName];
              return chunk;
            }).catch((error) => {
              delete pendingChunks[repoName];
              throw error;
            });
          }
          return pendingChunks[repoName];
        }
      };
    }
    function dashboardData() {
      return state.dashboardData;
    }
    function currentPayload() {
      return dashboardData()?.getPayload() || null;
    }
    function hasChunkLoadError(repoName) {
      return !!(repoName && state.chunkLoadErrors && state.chunkLoadErrors[repoName]);
    }
    function currentChunkLoadErrors() {
      return Object.keys(state.chunkLoadErrors || {})
        .sort()
        .map((repoName) => state.chunkLoadErrors[repoName]);
    }
    function normalizeChunkLoadError(repoName, error) {
      const data = dashboardData();
      const stage = error?.dashboardDataStage || error?.dashboardChunkStage || 'runtime';
      const chunkId = error?.chunkId || data?.getRepoChunkId?.(repoName) || '';
      return {
        repoName,
        chunkId,
        mode: error?.mode || (data?.isEncrypted?.() ? 'encrypted' : 'plaintext'),
        stage: CHUNK_FAILURE_LABELS[stage] ? stage : 'runtime',
        label: CHUNK_FAILURE_LABELS[stage] || CHUNK_FAILURE_LABELS.runtime,
        summaryDecrypted: !!error?.summaryDecrypted,
        exceptionName: error?.originalName || error?.name || '',
        exceptionMessage: error?.originalMessage || error?.message || String(error || ''),
        missingField: error?.missingField || ''
      };
    }
    function recordChunkLoadErrors(diagnostics) {
      diagnostics.forEach((diagnostic) => {
        state.chunkLoadErrors[diagnostic.repoName] = diagnostic;
        console.error('Dashboard repository chunk load failed', diagnostic);
      });
    }
    function clearChunkLoadErrors(repoNames) {
      if (!repoNames) {
        state.chunkLoadErrors = {};
        return;
      }
      repoNames.forEach((repoName) => {
        delete state.chunkLoadErrors[repoName];
      });
    }
    function chunkDiagnosticsText(errors) {
      return errors.map((error) => {
        return [
          'repo=' + error.repoName,
          'chunk_id=' + (error.chunkId || '(none)'),
          'mode=' + error.mode,
          'stage=' + error.stage,
          'summary_decrypted=' + (error.summaryDecrypted ? 'true' : 'false'),
          error.missingField ? 'missing_field=' + error.missingField : '',
          error.exceptionName ? 'exception_name=' + error.exceptionName : '',
          error.exceptionMessage ? 'exception_message=' + error.exceptionMessage : ''
        ].filter(Boolean).join('\n');
      }).join('\n\n');
    }
    function summarizeChunkErrors(errors) {
      const counts = {};
      errors.forEach((error) => {
        counts[error.stage] = (counts[error.stage] || 0) + 1;
      });
      return Object.keys(counts).sort().map((stage) => {
        return counts[stage] + ' ' + (CHUNK_FAILURE_LABELS[stage] || stage).toLowerCase();
      }).join(', ');
    }
    function renderDashboardNotice() {
      const region = document.getElementById('dashboard-notice-region');
      if (!region) return;
      const errors = currentChunkLoadErrors();
      region.textContent = '';
      if (!errors.length && !hasTrafficLag()) {
        region.hidden = true;
        region.removeAttribute('role');
        return;
      }
      if (hasTrafficLag()) {
        region.appendChild(buildTrafficLagNotice());
      }
      if (!errors.length) {
        region.hidden = false;
        return;
      }

      const notice = document.createElement('div');
      notice.className = 'dashboard-notice error';
      notice.setAttribute('role', 'alert');

      const main = document.createElement('div');
      main.className = 'dashboard-notice-main';
      const copy = document.createElement('div');
      copy.className = 'dashboard-notice-copy';
      const title = document.createElement('div');
      title.className = 'dashboard-notice-title';
      title.textContent = errors.length === 1
        ? 'Repository data could not be loaded'
        : 'Some repository data could not be loaded';
      const message = document.createElement('div');
      message.className = 'dashboard-notice-message';
      const names = errors.slice(0, 3).map((error) => error.repoName).join(', ');
      const more = errors.length > 3 ? ' +' + (errors.length - 3) + ' more' : '';
      message.textContent = errors.length === 1
        ? errors[0].repoName + ' failed at ' + errors[0].label.toLowerCase() + '. Charts omit this repository until it loads successfully.'
        : errors.length + ' repositories failed to load (' + summarizeChunkErrors(errors) + '): ' + names + more + '. Charts omit these repositories until they load successfully.';
      copy.appendChild(title);
      copy.appendChild(message);

      const actions = document.createElement('div');
      actions.className = 'dashboard-notice-actions';
      const retryButton = document.createElement('button');
      retryButton.type = 'button';
      retryButton.className = 'toolbar-button visible';
      retryButton.dataset.noticeAction = 'retry-chunks';
      retryButton.textContent = 'Retry';
      actions.appendChild(retryButton);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        const copyButton = document.createElement('button');
        copyButton.type = 'button';
        copyButton.className = 'toolbar-button visible';
        copyButton.dataset.noticeAction = 'copy-diagnostics';
        copyButton.textContent = 'Copy details';
        actions.appendChild(copyButton);
      }

      main.appendChild(copy);
      main.appendChild(actions);
      notice.appendChild(main);

      const details = document.createElement('details');
      details.className = 'dashboard-notice-details';
      const summary = document.createElement('summary');
      summary.textContent = 'Diagnostics';
      const diagnostics = document.createElement('pre');
      diagnostics.className = 'dashboard-notice-diagnostics';
      diagnostics.textContent = chunkDiagnosticsText(errors);
      details.appendChild(summary);
      details.appendChild(diagnostics);
      notice.appendChild(details);

      region.appendChild(notice);
      region.hidden = false;
    }

    function hasTrafficLag() {
      const reporting = currentPayload()?.traffic_reporting || {};
      return !!reporting.has_lag;
    }

    function buildTrafficLagNotice() {
      const reporting = currentPayload()?.traffic_reporting || {};
      const lagDays = Number(reporting.lag_days || 0);
      const affected = reporting.affected_repos || [];
      const unreportedStart = reporting.unreported_start_date || '';
      const unreportedEnd = reporting.unreported_end_date || '';
      const latestCollection = reporting.latest_collection_date || 'unknown';
      const notice = document.createElement('div');
      notice.className = 'dashboard-notice warning';
      notice.setAttribute('role', 'status');

      const main = document.createElement('div');
      main.className = 'dashboard-notice-main';
      const copy = document.createElement('div');
      copy.className = 'dashboard-notice-copy';
      const title = document.createElement('div');
      title.className = 'dashboard-notice-title';
      title.textContent = 'GitHub traffic data is behind';
      const message = document.createElement('div');
      message.className = 'dashboard-notice-message';
      const repoText = affected.length
        ? ' across ' + formatNumber(affected.length) + ' repositories'
        : '';
      const rangeText = unreportedStart && unreportedEnd
        ? ' for ' + (unreportedStart === unreportedEnd ? unreportedStart : unreportedStart + ' through ' + unreportedEnd)
        : '';
      message.textContent = (
        'Latest collection is ' + latestCollection
        + ', but GitHub traffic is unreported' + rangeText
        + (lagDays > 0 ? ' (' + formatNumber(lagDays) + ' day gap)' : '')
        + repoText
        + '. Charts show the missing trailing dates as unreported, not zero traffic.'
      );
      copy.appendChild(title);
      copy.appendChild(message);
      main.appendChild(copy);
      notice.appendChild(main);
      return notice;
    }
