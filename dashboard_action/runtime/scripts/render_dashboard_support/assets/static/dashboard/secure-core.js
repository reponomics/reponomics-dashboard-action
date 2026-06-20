const EXPECTED_DASHBOARD_DATA_VERSION = 2;
const EXPECTED_CIPHER = 'AES-GCM';
const EXPECTED_KDF_NAME = 'PBKDF2';
const EXPECTED_KDF_HASH = 'SHA-256';
const EXPECTED_KDF_ITERATIONS = __PBKDF2_ITERATIONS__;
const EXPECTED_SALT_BYTES = 16;
const EXPECTED_IV_BYTES = 12;
const UNLOCK_ATTEMPT_STORAGE_PREFIX = 'reponomics-unlock-attempts:';
const UNLOCK_DELAY_STARTS_AT = 3;
const UNLOCK_DELAY_BASE_MS = 2000;
const UNLOCK_DELAY_MAX_MS = 30000;

function dashboardDataError(stage, message, details) {
  const error = new Error(message);
  error.dashboardDataStage = stage;
  if (details) {
    Object.keys(details).forEach((key) => {
      error[key] = details[key];
    });
  }
  return error;
}

function unlockAttemptStorageKey(
  encryptedDashboardData,
  prefix = UNLOCK_ATTEMPT_STORAGE_PREFIX,
) {
  const fingerprint = [
    encryptedDashboardData.version,
    encryptedDashboardData.cipher,
    encryptedDashboardData.salt,
    String(encryptedDashboardData.summary || '').slice(0, 32),
    String(encryptedDashboardData.chunk_count || 0),
  ].join(':');
  return prefix + fingerprint;
}

function nextUnlockDelayMs(failures) {
  if (failures < UNLOCK_DELAY_STARTS_AT) {
    return 0;
  }
  const exponent = failures - UNLOCK_DELAY_STARTS_AT;
  return Math.min(
    UNLOCK_DELAY_MAX_MS,
    UNLOCK_DELAY_BASE_MS * Math.pow(2, exponent),
  );
}

function formatDelay(seconds) {
  return seconds === 1 ? '1 second' : seconds + ' seconds';
}

function b64ToBytes(value) {
  if (typeof value !== 'string' || !value) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function b64urlToBytes(value) {
  if (typeof value !== 'string' || !value) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const padded = value.replace(/-/g, '+').replace(/_/g, '/')
    + '='.repeat((4 - (value.length % 4)) % 4);
  return b64ToBytes(padded);
}

function bytesToHex(bytes) {
  return Array.from(bytes)
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

function buildExportFilename(prefix, now = new Date()) {
  const stamp = now.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
  const safePrefix = String(prefix || 'reponomics-export')
    .replace(/\.zip$/i, '')
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'reponomics-export';
  return safePrefix + '-' + stamp + '.zip';
}

function validateEncryptedBlob(token) {
  if (typeof token !== 'string') {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const parts = token.split('.');
  if (parts.length !== 2) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const iv = b64urlToBytes(parts[0]);
  const ciphertext = b64urlToBytes(parts[1]);
  if (iv.length !== EXPECTED_IV_BYTES || ciphertext.length === 0) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  return { iv, ciphertext };
}

function validateEncryptedDashboardData(data) {
  if (!data || data.version !== EXPECTED_DASHBOARD_DATA_VERSION) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  if (data.cipher !== EXPECTED_CIPHER) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  if (
    !data.kdf ||
    data.kdf.name !== EXPECTED_KDF_NAME ||
    data.kdf.hash !== EXPECTED_KDF_HASH ||
    data.kdf.iterations !== EXPECTED_KDF_ITERATIONS
  ) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  if (data.encoding !== 'gzip+json') {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const salt = b64ToBytes(data.salt);
  if (salt.length !== EXPECTED_SALT_BYTES) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  validateEncryptedBlob(data.summary);
  if (!data.chunks || typeof data.chunks !== 'object' || Array.isArray(data.chunks)) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  const chunkIds = Object.keys(data.chunks);
  if (data.chunk_count !== chunkIds.length) {
    throw new Error('Invalid encrypted dashboard data.');
  }
  chunkIds.forEach((chunkId) => {
    if (!/^c[0-9]{4,}$/.test(chunkId)) {
      throw new Error('Invalid encrypted dashboard data.');
    }
    validateEncryptedBlob(data.chunks[chunkId]);
  });
  return { salt };
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
    ['deriveKey'],
  );
  return crypto.subtle.deriveKey(
    {
      name: EXPECTED_KDF_NAME,
      salt,
      iterations: EXPECTED_KDF_ITERATIONS,
      hash: EXPECTED_KDF_HASH,
    },
    keyMaterial,
    { name: EXPECTED_CIPHER, length: 256 },
    false,
    ['decrypt'],
  );
}

async function decryptBytes(key, iv, ciphertext) {
  return crypto.subtle.decrypt(
    { name: EXPECTED_CIPHER, iv },
    key,
    ciphertext,
  );
}

async function gunzipJson(bytes, context) {
  if (!globalThis.DecompressionStream) {
    throw dashboardDataError(
      'decompress',
      'Browser does not support gzip decompression.',
      context,
    );
  }
  let decompressed;
  try {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    decompressed = await new Response(stream).arrayBuffer();
  } catch (error) {
    throw dashboardDataError(
      'decompress',
      error.message || 'Dashboard data could not be decompressed.',
      {
        ...context,
        originalName: error.name || '',
        originalMessage: error.message || String(error),
      },
    );
  }
  try {
    return JSON.parse(new TextDecoder().decode(decompressed));
  } catch (error) {
    throw dashboardDataError(
      'parse',
      error.message || 'Dashboard data was not valid JSON.',
      {
        ...context,
        originalName: error.name || '',
        originalMessage: error.message || String(error),
      },
    );
  }
}

async function decryptDashboardBlob(key, token, context) {
  const details = context || {};
  let blob;
  try {
    blob = validateEncryptedBlob(token);
  } catch (error) {
    throw dashboardDataError(
      'schema',
      error.message || 'Encrypted dashboard blob was malformed.',
      {
        ...details,
        originalName: error.name || '',
        originalMessage: error.message || String(error),
      },
    );
  }
  let compressed;
  try {
    compressed = await decryptBytes(key, blob.iv, blob.ciphertext);
  } catch (error) {
    throw dashboardDataError(
      'decrypt',
      error.message || 'Encrypted dashboard blob failed authentication.',
      {
        ...details,
        originalName: error.name || '',
        originalMessage: error.message || String(error),
      },
    );
  }
  return gunzipJson(new Uint8Array(compressed), details);
}

async function decryptDashboardData(dashboardKey, data) {
  const validatedData = validateEncryptedDashboardData(data);
  const displayKey = await deriveAesKey(dashboardKey, validatedData.salt);
  const summary = await decryptDashboardBlob(displayKey, data.summary, {
    mode: 'encrypted',
    summaryDecrypted: false,
    stageTarget: 'summary',
  });
  const repoChunks = summary.repo_chunks || {};
  return {
    summary,
    loadRepoChunk: async function(repoName) {
      const chunkId = repoChunks[repoName];
      if (!chunkId || !data.chunks[chunkId]) {
        throw dashboardDataError('missing', 'Encrypted dashboard chunk was missing.', {
          repoName,
          chunkId: chunkId || '',
          mode: 'encrypted',
          summaryDecrypted: true,
          stageTarget: 'chunk',
        });
      }
      const chunk = await decryptDashboardBlob(displayKey, data.chunks[chunkId], {
        repoName,
        chunkId,
        mode: 'encrypted',
        summaryDecrypted: true,
        stageTarget: 'chunk',
      });
      if (!chunk.repo || chunk.repo !== repoName) {
        throw dashboardDataError(
          'schema',
          'Encrypted dashboard chunk did not match the requested repository.',
          {
            repoName,
            chunkId,
            mode: 'encrypted',
            summaryDecrypted: true,
            stageTarget: 'chunk',
          },
        );
      }
      return chunk;
    },
  };
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return bytesToHex(new Uint8Array(digest));
}

export {
  EXPECTED_CIPHER,
  EXPECTED_DASHBOARD_DATA_VERSION,
  EXPECTED_KDF_HASH,
  EXPECTED_KDF_ITERATIONS,
  EXPECTED_KDF_NAME,
  b64urlToBytes,
  buildExportFilename,
  bytesToHex,
  decryptBytes,
  decryptDashboardData,
  deriveAesKey,
  formatDelay,
  nextUnlockDelayMs,
  sha256Hex,
  unlockAttemptStorageKey,
  validateEncryptedDashboardData,
  validateEncryptedExportManifest,
};
