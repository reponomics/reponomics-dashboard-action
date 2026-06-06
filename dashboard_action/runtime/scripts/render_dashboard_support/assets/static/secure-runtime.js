
    const EXPECTED_PAYLOAD_VERSION = 1;
    const EXPECTED_CIPHER = 'AES-GCM';
    const EXPECTED_KDF_NAME = 'PBKDF2';
    const EXPECTED_KDF_HASH = 'SHA-256';
    const EXPECTED_KDF_ITERATIONS = __PBKDF2_ITERATIONS__;
    const EXPECTED_SALT_BYTES = 16;
    const EXPECTED_IV_BYTES = 12;

    const encryptedPayload = JSON.parse(
      document.getElementById('encrypted-payload').textContent
    );
    const exportManifestNode = document.getElementById('export-manifest');
    const exportManifestPayload = exportManifestNode
      ? JSON.parse(exportManifestNode.textContent)
      : null;
    const authShell = document.getElementById('auth-shell');
    const unlockForm = document.getElementById('unlock-form');
    const dashboardKeyInput = document.getElementById('dashboard-key');
    const unlockButton = document.getElementById('unlock-button');
    const unlockStatus = document.getElementById('unlock-status');
    const authThemeToggle = document.getElementById('auth-theme-toggle');
    const exportButton = document.getElementById('export-button');
    const exportHashButton = document.getElementById('export-hash-button');
    const exportStatus = document.getElementById('export-status');
    const EXPORT_BUTTON_LABEL = '📄 Export to CSV';
    const EXPORT_BUTTON_WORKING_LABEL = 'Preparing…';
    const UNLOCK_ATTEMPT_STORAGE_PREFIX = 'reponomics-unlock-attempts:';
    const UNLOCK_DELAY_STARTS_AT = 3;
    const UNLOCK_DELAY_BASE_MS = 2000;
    const UNLOCK_DELAY_MAX_MS = 30000;
    let unlockedDashboardKey = '';
    let unlockDelayTimer = null;

    function setUnlockStatus(message, type) {
      unlockStatus.textContent = message;
      unlockStatus.className = 'auth-status' + (type ? ' ' + type : '');
    }

    function unlockAttemptStorageKey() {
      const fingerprint = [
        encryptedPayload.version,
        encryptedPayload.cipher,
        encryptedPayload.salt,
        encryptedPayload.iv,
        String(encryptedPayload.ciphertext || '').slice(0, 32)
      ].join(':');
      return UNLOCK_ATTEMPT_STORAGE_PREFIX + fingerprint;
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

    function nextUnlockDelayMs(failures) {
      if (failures < UNLOCK_DELAY_STARTS_AT) {
        return 0;
      }
      const exponent = failures - UNLOCK_DELAY_STARTS_AT;
      return Math.min(
        UNLOCK_DELAY_MAX_MS,
        UNLOCK_DELAY_BASE_MS * Math.pow(2, exponent)
      );
    }

    function formatDelay(seconds) {
      return seconds === 1 ? '1 second' : seconds + ' seconds';
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

    function b64ToBytes(value) {
      if (typeof value !== 'string' || !value) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      const binary = atob(value);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) {
        bytes[i] = binary.charCodeAt(i);
      }
      return bytes;
    }

    function bytesToHex(bytes) {
      return Array.from(bytes)
        .map((value) => value.toString(16).padStart(2, '0'))
        .join('');
    }

    function buildExportFilename(prefix) {
      const now = new Date();
      const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
      const safePrefix = String(prefix || 'reponomics-export')
        .replace(/\.zip$/i, '')
        .replace(/[^A-Za-z0-9._-]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'reponomics-export';
      return safePrefix + '-' + stamp + '.zip';
    }

    function validateEncryptedPayload(payload) {
      if (!payload || payload.version !== EXPECTED_PAYLOAD_VERSION) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      if (payload.cipher !== EXPECTED_CIPHER) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      if (
        !payload.kdf ||
        payload.kdf.name !== EXPECTED_KDF_NAME ||
        payload.kdf.hash !== EXPECTED_KDF_HASH ||
        payload.kdf.iterations !== EXPECTED_KDF_ITERATIONS
      ) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      const salt = b64ToBytes(payload.salt);
      const iv = b64ToBytes(payload.iv);
      const ciphertext = b64ToBytes(payload.ciphertext);
      if (
        salt.length !== EXPECTED_SALT_BYTES ||
        iv.length !== EXPECTED_IV_BYTES ||
        ciphertext.length === 0
      ) {
        throw new Error('Invalid encrypted dashboard payload.');
      }
      return { salt, iv, ciphertext };
    }

    function validateEncryptedExportManifest(manifest) {
      if (!manifest || manifest.version !== 1) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (manifest.cipher !== EXPECTED_CIPHER) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (
        !manifest.kdf ||
        manifest.kdf.name !== EXPECTED_KDF_NAME ||
        manifest.kdf.hash !== EXPECTED_KDF_HASH ||
        manifest.kdf.iterations !== EXPECTED_KDF_ITERATIONS
      ) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (typeof manifest.asset !== 'string' || !manifest.asset) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (typeof manifest.filename !== 'string' || !manifest.filename) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (!Number.isInteger(manifest.ciphertext_size) || manifest.ciphertext_size <= 0) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (
        typeof manifest.ciphertext_sha256 !== 'string' ||
        !/^[a-f0-9]{64}$/.test(manifest.ciphertext_sha256)
      ) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (
        typeof manifest.plaintext_sha256 !== 'string' ||
        !/^[a-f0-9]{64}$/.test(manifest.plaintext_sha256)
      ) {
        throw new Error('Invalid encrypted export metadata.');
      }
      if (!/^assets\/export-data-[a-f0-9]{16}\.enc$/.test(manifest.asset)) {
        throw new Error('Invalid encrypted export metadata.');
      }
      const salt = b64ToBytes(manifest.salt);
      const iv = b64ToBytes(manifest.iv);
      if (salt.length !== EXPECTED_SALT_BYTES || iv.length !== EXPECTED_IV_BYTES) {
        throw new Error('Invalid encrypted export metadata.');
      }
      return { ...manifest, salt, iv };
    }

    async function deriveAesKey(dashboardKey, salt) {
      const encoder = new TextEncoder();
      const keyMaterial = await crypto.subtle.importKey(
        'raw',
        encoder.encode(dashboardKey),
        'PBKDF2',
        false,
        ['deriveKey']
      );
      return crypto.subtle.deriveKey(
        {
          name: EXPECTED_KDF_NAME,
          salt,
          iterations: EXPECTED_KDF_ITERATIONS,
          hash: EXPECTED_KDF_HASH
        },
        keyMaterial,
        { name: EXPECTED_CIPHER, length: 256 },
        false,
        ['decrypt']
      );
    }

    async function decryptBytes(dashboardKey, salt, iv, ciphertext) {
      const key = await deriveAesKey(dashboardKey, salt);
      return crypto.subtle.decrypt(
        { name: EXPECTED_CIPHER, iv },
        key,
        ciphertext
      );
    }

    async function decryptDashboardPayload(dashboardKey, payload) {
      const validatedPayload = validateEncryptedPayload(payload);
      const plaintext = await decryptBytes(
        dashboardKey,
        validatedPayload.salt,
        validatedPayload.iv,
        validatedPayload.ciphertext
      );
      return JSON.parse(new TextDecoder().decode(plaintext));
    }

    async function sha256Hex(bytes) {
      const digest = await crypto.subtle.digest('SHA-256', bytes);
      return bytesToHex(new Uint8Array(digest));
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
        if (!unlockedDashboardKey) {
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
            unlockedDashboardKey,
            validatedManifest.salt,
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
      authThemeToggle.addEventListener('click', toggleTheme);
      applyTheme(preferredTheme(), false);
    }

    unlockForm.addEventListener('submit', async function(event) {
      event.preventDefault();
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
        const payload = await decryptDashboardPayload(
          dashboardKeyInput.value,
          encryptedPayload
        );
        unlockedDashboardKey = dashboardKeyInput.value;
        authShell.style.display = 'none';
        document.body.classList.remove('auth-locked');
        document.body.removeAttribute('data-screen-label');
        renderDashboard(payload);
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
        unlockedDashboardKey = '';
        if (delayMs) {
          startUnlockDelay(
            delayMs,
            'Wrong dashboard key or corrupted payload. Try again in '
          );
        } else {
          unlockButton.disabled = false;
          setUnlockStatus('Wrong dashboard key or corrupted payload.', 'error');
        }
      }
    });
