export async function readJsonAsset(document, metaName, legacyScriptId, options = {}) {
  const meta = document.querySelector(`meta[name="${metaName}"]`);
  const href = meta?.getAttribute('content');
  if (href) {
    const response = await fetch(href, { cache: options.cache || 'no-store' });
    if (!response.ok) {
      throw new Error(`Failed to load dashboard asset: ${href}`);
    }
    return response.json();
  }

  const legacyScript = legacyScriptId ? document.getElementById(legacyScriptId) : null;
  if (legacyScript) {
    return JSON.parse(legacyScript.textContent || 'null');
  }

  if (options.optional) {
    return null;
  }
  throw new Error(`Dashboard asset metadata was not found: ${metaName}`);
}
