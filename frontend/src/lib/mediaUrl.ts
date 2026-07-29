/**
 * 私有媒体 URL 与短时 media_token 管理。
 * JWT 走 API 请求头；<img>/<video> 等原生标签通过 query token 鉴权。
 *
 * @author wanghaobo
 */

import { getAuthHeader } from "@/utils/auth";

const API_BASE = "/api/v1";
const TOKEN_BUFFER_MS = 30_000;

interface CachedToken {
  token: string;
  expiresAt: number;
}

const projectTokenCache = new Map<string, CachedToken>();
const assetTokenCache = new Map<string, CachedToken>();
let authEnabled: boolean | null = null;

export function clearMediaTokenCache(): void {
  projectTokenCache.clear();
  assetTokenCache.clear();
  authEnabled = null;
}

export function isPrivateMediaUrl(url: string | null | undefined): boolean {
  if (!url) return false;
  return url.includes("/api/v1/files/") || url.includes("/api/v1/global-assets/");
}

async function fetchAuthEnabled(): Promise<boolean> {
  if (authEnabled !== null) return authEnabled;
  try {
    const res = await fetch("/api/v1/auth/status");
    if (!res.ok) {
      authEnabled = true;
      return authEnabled;
    }
    const data = (await res.json()) as { enabled?: boolean };
    authEnabled = data.enabled === true;
  } catch {
    authEnabled = true;
  }
  return authEnabled;
}

function readCachedToken(cache: Map<string, CachedToken>, key: string): string | null {
  const cached = cache.get(key);
  if (!cached) return null;
  if (cached.expiresAt <= Date.now() + TOKEN_BUFFER_MS) {
    cache.delete(key);
    return null;
  }
  return cached.token;
}

function storeCachedToken(
  cache: Map<string, CachedToken>,
  key: string,
  token: string,
  expiresIn: number,
): void {
  cache.set(key, {
    token,
    expiresAt: Date.now() + expiresIn * 1000,
  });
}

export function appendMediaToken(url: string, token: string | null | undefined): string {
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}media_token=${encodeURIComponent(token)}`;
}

export function buildMediaUrl(
  baseUrl: string,
  opts?: { mediaToken?: string | null; cacheBust?: number | string | null },
): string {
  let url = baseUrl;
  if (opts?.cacheBust != null && opts.cacheBust !== "") {
    const sep = url.includes("?") ? "&" : "?";
    url = `${url}${sep}v=${encodeURIComponent(String(opts.cacheBust))}`;
  }
  return appendMediaToken(url, opts?.mediaToken);
}

export async function ensureProjectMediaToken(projectName: string): Promise<string | null> {
  const enabled = await fetchAuthEnabled();
  if (!enabled) return null;

  const cached = readCachedToken(projectTokenCache, projectName);
  if (cached) return cached;

  const headers: HeadersInit = {};
  const auth = getAuthHeader();
  if (auth) headers.Authorization = auth;

  try {
    const res = await fetch(
      `${API_BASE}/media-token?project=${encodeURIComponent(projectName)}`,
      { headers },
    );
    if (!res.ok) return null;

    const payload = (await res.json()) as { media_token: string; expires_in: number };
    storeCachedToken(projectTokenCache, projectName, payload.media_token, payload.expires_in);
    return payload.media_token;
  } catch {
    return null;
  }
}

export async function ensureAssetMediaToken(assetPath: string): Promise<string | null> {
  const enabled = await fetchAuthEnabled();
  if (!enabled) return null;

  const cached = readCachedToken(assetTokenCache, assetPath);
  if (cached) return cached;

  const headers: HeadersInit = {};
  const auth = getAuthHeader();
  if (auth) headers.Authorization = auth;

  try {
    const res = await fetch(
      `${API_BASE}/media-token?asset_path=${encodeURIComponent(assetPath)}`,
      { headers },
    );
    if (!res.ok) return null;

    const payload = (await res.json()) as { media_token: string; expires_in: number };
    storeCachedToken(assetTokenCache, assetPath, payload.media_token, payload.expires_in);
    return payload.media_token;
  } catch {
    return null;
  }
}

export function invalidateProjectMediaToken(projectName: string): void {
  projectTokenCache.delete(projectName);
}

export function invalidateAssetMediaToken(assetPath: string): void {
  assetTokenCache.delete(assetPath);
}

export function parseProjectFromMediaUrl(url: string): string | null {
  const match = url.match(/\/api\/v1\/files\/([^/?]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

export interface GlobalAssetPathParts {
  type: string;
  filename: string;
  assetPath?: string;
}

export function parseGlobalAssetPath(imagePath: string | null): GlobalAssetPathParts | null {
  if (!imagePath) return null;
  const parts = imagePath.split("/");
  if (parts[0] === "_global_assets" && parts.length >= 3) {
    return { type: parts[1], filename: parts.slice(2).join("/") };
  }
  if (parts[0] === "users" && parts[2] === "assets" && parts.length >= 5) {
    return {
      type: parts[3],
      filename: parts.slice(4).join("/"),
      assetPath: imagePath,
    };
  }
  return null;
}

export function getProjectFileUrlSync(
  projectName: string,
  path: string,
  cacheBust?: number | string | null,
): string {
  const base = `${API_BASE}/files/${encodeURIComponent(projectName)}/${path}`;
  const token = readCachedToken(projectTokenCache, projectName);
  return buildMediaUrl(base, { mediaToken: token, cacheBust });
}

export async function getProjectFileUrl(
  projectName: string,
  path: string,
  cacheBust?: number | string | null,
): Promise<string> {
  await ensureProjectMediaToken(projectName);
  return getProjectFileUrlSync(projectName, path, cacheBust);
}

export function getGlobalAssetUrlSync(
  imagePath: string | null,
  fp?: string | null,
  mediaToken?: string | null,
): string | null {
  const parsed = parseGlobalAssetPath(imagePath);
  if (!parsed) return null;
  const qs = fp ? `?fp=${encodeURIComponent(fp)}` : "";
  const base = `${API_BASE}/global-assets/${parsed.type}/${parsed.filename}${qs}`;
  const token =
    mediaToken ??
    (parsed.assetPath ? readCachedToken(assetTokenCache, parsed.assetPath) : null);
  return appendMediaToken(base, token);
}

export async function getGlobalAssetUrl(
  imagePath: string | null,
  fp?: string | null,
  mediaToken?: string | null,
): Promise<string | null> {
  const parsed = parseGlobalAssetPath(imagePath);
  if (!parsed) return null;
  if (!mediaToken && parsed.assetPath) {
    await ensureAssetMediaToken(parsed.assetPath);
  }
  return getGlobalAssetUrlSync(imagePath, fp, mediaToken);
}

export function resolveAssetImageUrl(asset: {
  image_path: string | null;
  image_url?: string | null;
  media_token?: string | null;
  updated_at?: string | null;
}): string | null {
  if (asset.image_url) {
    return buildMediaUrl(asset.image_url, { mediaToken: asset.media_token });
  }
  return getGlobalAssetUrlSync(asset.image_path, asset.updated_at ?? null);
}

export async function refreshMediaUrl(url: string): Promise<string | null> {
  if (!isPrivateMediaUrl(url)) return url;

  const baseUrl = url.split(/[?#]/)[0] ?? url;
  const params = new URL(url, "http://local").searchParams;
  const cacheBust = params.get("v") ?? params.get("fp");

  const projectName = parseProjectFromMediaUrl(baseUrl);
  if (projectName) {
    invalidateProjectMediaToken(projectName);
    const token = await ensureProjectMediaToken(projectName);
    const pathMatch = baseUrl.match(/\/api\/v1\/files\/[^/]+\/(.+)$/);
    if (!pathMatch?.[1]) return null;
    return buildMediaUrl(`${API_BASE}/files/${encodeURIComponent(projectName)}/${pathMatch[1]}`, {
      mediaToken: token,
      cacheBust,
    });
  }

  const globalMatch = baseUrl.match(/\/api\/v1\/global-assets\/([^/]+)\/(.+)$/);
  if (globalMatch) {
    const [, assetType, filename] = globalMatch;
    const tokenFromUrl = params.get("media_token");
    if (tokenFromUrl) {
      try {
        const payload = JSON.parse(atob(tokenFromUrl.split(".")[1] ?? "")) as {
          asset_path?: string;
        };
        if (typeof payload.asset_path === "string") {
          invalidateAssetMediaToken(payload.asset_path);
          const token = await ensureAssetMediaToken(payload.asset_path);
          return buildMediaUrl(`${API_BASE}/global-assets/${assetType}/${filename}`, {
            mediaToken: token,
            cacheBust: cacheBust ?? undefined,
          });
        }
      } catch {
        // fall through
      }
    }
  }

  return null;
}
