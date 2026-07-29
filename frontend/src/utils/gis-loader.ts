// @author wanghaobo

const GIS_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
const GIS_SCRIPT_ID = "google-gsi-client";
const GIS_POLL_INTERVAL_MS = 50;
const GIS_LOAD_TIMEOUT_MS = 10_000;

let gisScriptPromise: Promise<void> | null = null;

function watchGisScript(script: HTMLScriptElement): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let settled = false;

    const cleanup = () => {
      settled = true;
      clearInterval(pollTimer);
      script.removeEventListener("load", onLoad);
      script.removeEventListener("error", onError);
    };
    const succeed = () => {
      if (settled) return;
      cleanup();
      resolve();
    };
    const fail = () => {
      if (settled) return;
      cleanup();
      reject(new Error("gis load failed"));
    };

    function onLoad() {
      succeed();
    }
    function onError() {
      fail();
    }

    script.addEventListener("load", onLoad);
    script.addEventListener("error", onError);

    // A script tag that finished loading before these listeners attached never fires
    // "load" again, so poll the global it installs instead of waiting forever.
    const startedAt = Date.now();
    const pollTimer = setInterval(() => {
      if (window.google?.accounts?.id) {
        succeed();
      } else if (Date.now() - startedAt > GIS_LOAD_TIMEOUT_MS) {
        fail();
      }
    }, GIS_POLL_INTERVAL_MS);
  });
}

// Failures must clear the cache so a later mount can retry the load.
function track(promise: Promise<void>): Promise<void> {
  gisScriptPromise = promise;
  promise.catch(() => {
    if (gisScriptPromise === promise) gisScriptPromise = null;
  });
  return promise;
}

export function loadGisScript(locale = "zh_CN"): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("no window"));
  }
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (gisScriptPromise) return gisScriptPromise;

  const existing = document.getElementById(GIS_SCRIPT_ID) as HTMLScriptElement | null;
  if (existing) {
    return track(watchGisScript(existing));
  }

  const script = document.createElement("script");
  script.id = GIS_SCRIPT_ID;
  script.src = `${GIS_SCRIPT_SRC}?hl=${encodeURIComponent(locale)}`;
  script.async = true;
  script.defer = true;
  const promise = track(watchGisScript(script));
  document.head.appendChild(script);
  return promise;
}
