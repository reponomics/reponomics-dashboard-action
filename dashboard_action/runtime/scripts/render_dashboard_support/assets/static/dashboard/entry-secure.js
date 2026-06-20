import { createDashboardApp } from './app.js';
import { readJsonAsset } from './json-assets.js';
import { buildExportFilename, decryptBytes, decryptDashboardData, deriveAesKey, formatDelay, nextUnlockDelayMs, sha256Hex, unlockAttemptStorageKey as buildUnlockAttemptStorageKey, validateEncryptedExportManifest } from './secure-core.js';

const app = createDashboardApp();
const encryptedDashboardData = await readJsonAsset(
  document,
  'reponomics-encrypted-dashboard-data',
  'encrypted-dashboard-data'
);
const exportManifestPayload = await readJsonAsset(
  document,
  'reponomics-export-manifest',
  'export-manifest',
  { optional: true }
);

    const authShell = document.getElementById('auth-shell');
    const unlockForm = document.getElementById('unlock-form');
    const dashboardKeyInput = document.getElementById('dashboard-key');
    const demoUnlockButton = document.getElementById('demo-unlock-button');
    const demoUnlockKey = document.getElementById('demo-unlock-key');
    const unlockButton = document.getElementById('unlock-button');
    const unlockStatus = document.getElementById('unlock-status');
    const authThemeToggle = document.getElementById('auth-theme-toggle');
    const exportButton = document.getElementById('export-button');
    const exportHashButton = document.getElementById('export-hash-button');
    const exportStatus = document.getElementById('export-status');
    const EXPORT_BUTTON_LABEL = '📄 Export to CSV';
    const EXPORT_BUTTON_WORKING_LABEL = 'Preparing…';
    let unlockedExportKey = null;
    let unlockDelayTimer = null;

    function setUnlockStatus(message, type) {
      unlockStatus.textContent = message;
      unlockStatus.className = 'auth-status' + (type ? ' ' + type : '');
    }

    function unlockAttemptStorageKey() {
      return buildUnlockAttemptStorageKey(encryptedDashboardData);
    }

    function readUnlockAttemptState() {
      try {
        const raw = localStorage.getItem(unlockAttemptStorageKey());
        const parsed = raw ? JSON.parse(raw) : null;
        if (
          parsed &&
          Number.isInteger(parsed.failures) &&
          Number.isFinite(parsed.nextAllowedAt)
        ) {
          return parsed;
        }
      } catch (_error) { /* ignore */ }
      return { failures: 0, nextAllowedAt: 0 };
    }

    function writeUnlockAttemptState(state) {
      try {
        localStorage.setItem(unlockAttemptStorageKey(), JSON.stringify(state));
      } catch (_error) { /* ignore */ }
    }

    function resetUnlockAttemptState() {
      try {
        localStorage.removeItem(unlockAttemptStorageKey());
      } catch (_error) { /* ignore */ }
    }

    function startUnlockDelay(delayMs, prefix) {
      if (unlockDelayTimer) {
        clearTimeout(unlockDelayTimer);
        unlockDelayTimer = null;
      }
      const target = Date.now() + Math.max(0, delayMs);
      unlockButton.disabled = true;

      const updateDelay = function() {
        const remainingMs = target - Date.now();
        if (remainingMs <= 0) {
          unlockButton.disabled = false;
          unlockDelayTimer = null;
          setUnlockStatus('', '');
          dashboardKeyInput.focus();
          return;
        }
        setUnlockStatus(
          prefix + formatDelay(Math.ceil(remainingMs / 1000)) + '.',
          'error'
        );
        unlockDelayTimer = setTimeout(updateDelay, Math.min(1000, remainingMs));
      };
      updateDelay();
    }

    function setExportStatus(message, type) {
      if (!exportStatus) return;
      const rawMessage = String(message || '');
      const useMultiline = rawMessage.includes('\n');
      exportStatus.textContent = rawMessage;
      exportStatus.className = 'auth-status'
        + (type ? ' ' + type : '')
        + (rawMessage ? ' visible' : '')
        + (useMultiline ? ' multiline' : '');
    }

    function setExportHashState(digest, filename) {
      if (!exportHashButton) return;
      if (!digest || !filename) {
        exportHashButton.classList.remove('visible');
        exportHashButton.removeAttribute('data-digest');
        exportHashButton.removeAttribute('data-filename');
        exportHashButton.disabled = true;
        return;
      }
      exportHashButton.classList.add('visible');
      exportHashButton.setAttribute('data-digest', digest);
      exportHashButton.setAttribute('data-filename', filename);
      exportHashButton.disabled = false;
    }

    async function deriveExportKey(dashboardKey) {
      if (!exportManifestPayload) return null;
      const manifest = validateEncryptedExportManifest(exportManifestPayload);
      return deriveAesKey(dashboardKey, manifest.salt);
    }

    function triggerDownload(filename, bytes) {
      const blob = new Blob([bytes], { type: 'application/zip' });
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      anchor.rel = 'noopener';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(function() { URL.revokeObjectURL(objectUrl); }, 0);
    }

    function enableExport() {
      if (!exportButton || !exportManifestPayload) {
        return;
      }
      let validatedManifest = null;
      try {
        validatedManifest = validateEncryptedExportManifest(exportManifestPayload);
      } catch (_error) {
        setExportStatus('Export metadata is invalid for this dashboard build.', 'error');
        return;
      }
      if (exportHashButton) {
        exportHashButton.disabled = true;
        exportHashButton.addEventListener('click', async function() {
          const digest = exportHashButton.getAttribute('data-digest') || '';
          const filename = exportHashButton.getAttribute('data-filename') || 'export.zip';
          if (!digest) {
            setExportStatus('📄 Export first to capture a checksum.', 'error');
            return;
          }
          const checksumLine = digest + '  ' + filename;
          try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(checksumLine);
            } else {
              throw new Error('clipboard-unavailable');
            }
            setExportStatus('📄 SHA-256 copied (hash + filename).', 'success');
          } catch (_error) {
            setExportStatus('📄 SHA-256: ' + checksumLine, 'success');
          }
        });
      }
      exportButton.classList.add('visible');
      exportButton.textContent = EXPORT_BUTTON_LABEL;
      exportButton.addEventListener('click', async function() {
        if (!unlockedExportKey) {
          setExportStatus('📄 Unlock the dashboard before exporting.', 'error');
          return;
        }
        exportButton.disabled = true;
        exportButton.textContent = EXPORT_BUTTON_WORKING_LABEL;
        exportButton.setAttribute('aria-busy', 'true');
        setExportHashState('', '');
        setExportStatus('📄 Preparing encrypted export bundle...', 'pending');
        let ciphertext = null;
        let plaintextView = null;
        try {
          const response = await fetch(validatedManifest.asset, { cache: 'no-store' });
          if (!response.ok) {
            throw new Error('fetch-failed');
          }
          ciphertext = new Uint8Array(await response.arrayBuffer());
          if (ciphertext.length !== validatedManifest.ciphertext_size) {
            throw new Error('size-mismatch');
          }
          const ciphertextSha256 = await sha256Hex(ciphertext);
          if (ciphertextSha256 !== validatedManifest.ciphertext_sha256) {
            throw new Error('digest-mismatch');
          }
          const plaintext = await decryptBytes(
            unlockedExportKey,
            validatedManifest.iv,
            ciphertext
          );
          plaintextView = new Uint8Array(plaintext);
          const plaintextSha256 = await sha256Hex(plaintextView);
          if (plaintextSha256 !== validatedManifest.plaintext_sha256) {
            throw new Error('plaintext-digest-mismatch');
          }
          const filename = buildExportFilename(validatedManifest.filename);
          triggerDownload(filename, plaintextView);
          setExportHashState(plaintextSha256, filename);
          setExportStatus('📄 CSV export ready.\nSHA-256: ' + plaintextSha256, 'success');
        } catch (error) {
          if (String(error) === 'Error: fetch-failed') {
            setExportStatus(
              '📄 Unable to fetch export asset from this context. Try the hosted dashboard or serve extracted files over HTTP.',
              'error'
            );
          } else if (
            String(error) === 'Error: size-mismatch'
            || String(error) === 'Error: digest-mismatch'
            || String(error) === 'Error: plaintext-digest-mismatch'
          ) {
            setExportStatus('📄 Export integrity check failed. Republish and try again.', 'error');
          } else {
            setExportStatus('📄 Export failed. Verify key and dashboard assets.', 'error');
          }
        } finally {
          if (ciphertext) {
            ciphertext.fill(0);
          }
          if (plaintextView) {
            plaintextView.fill(0);
          }
          exportButton.disabled = false;
          exportButton.textContent = EXPORT_BUTTON_LABEL;
          exportButton.setAttribute('aria-busy', 'false');
        }
      });
    }

    if (!window.crypto || !window.crypto.subtle) {
      unlockButton.disabled = true;
      if (exportButton) {
        exportButton.disabled = true;
      }
      setUnlockStatus(
        'This browser cannot decrypt the dashboard here. Open it over HTTPS or serve the extracted dashboard artifact over local HTTP.',
        'error'
      );
    } else {
      const storedAttemptState = readUnlockAttemptState();
      const storedDelayMs = storedAttemptState.nextAllowedAt - Date.now();
      if (storedDelayMs > 0) {
        startUnlockDelay(storedDelayMs, 'Too many failed attempts. Try again in ');
      } else {
        dashboardKeyInput.focus();
      }
    }

    if (authThemeToggle) {
      authThemeToggle.addEventListener('click', app.toggleTheme);
      app.applyTheme(app.preferredTheme(), false);
    }

    async function unlockWithCurrentInput() {
      if (!dashboardKeyInput.value) {
        setUnlockStatus('Enter the dashboard key.', 'error');
        return;
      }

      const attemptState = readUnlockAttemptState();
      const now = Date.now();
      if (attemptState.nextAllowedAt > now) {
        startUnlockDelay(
          attemptState.nextAllowedAt - now,
          'Too many failed attempts. Try again in '
        );
        dashboardKeyInput.select();
        return;
      }

      unlockButton.disabled = true;
      setUnlockStatus('Unlocking dashboard...', 'pending');

      try {
        const dashboardKey = dashboardKeyInput.value;
        const payload = await decryptDashboardData(
          dashboardKey,
          encryptedDashboardData
        );
        try {
          unlockedExportKey = await deriveExportKey(dashboardKey);
        } catch (_error) {
          unlockedExportKey = null;
        }
        dashboardKeyInput.value = '';
        authShell.style.display = 'none';
        document.body.classList.remove('auth-locked');
        document.body.removeAttribute('data-screen-label');
        app.renderDashboard(payload);
        enableExport();
        if (unlockDelayTimer) {
          clearTimeout(unlockDelayTimer);
          unlockDelayTimer = null;
        }
        resetUnlockAttemptState();
        setUnlockStatus('', '');
      } catch (error) {
        const failures = attemptState.failures + 1;
        const delayMs = nextUnlockDelayMs(failures);
        writeUnlockAttemptState({
          failures,
          nextAllowedAt: delayMs ? Date.now() + delayMs : 0
        });
        dashboardKeyInput.select();
        unlockedExportKey = null;
        if (delayMs) {
          startUnlockDelay(
            delayMs,
            'Wrong dashboard key or corrupted data. Try again in '
          );
        } else {
          unlockButton.disabled = false;
          setUnlockStatus('Wrong dashboard key or corrupted data.', 'error');
        }
      }
    }

    unlockForm.addEventListener('submit', async function(event) {
      event.preventDefault();
      await unlockWithCurrentInput();
    });

    if (demoUnlockButton && demoUnlockKey) {
      demoUnlockButton.addEventListener('click', async function() {
        dashboardKeyInput.value = demoUnlockKey.textContent.trim();
        await unlockWithCurrentInput();
      });
    }
