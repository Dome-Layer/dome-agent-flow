/**
 * The id segment of a dynamic route, read from the URL path. The dashboard is a static export
 * (Sprint H phase 2): every /events/<id> and /runs/<id> is served from one prebuilt page
 * (/events/_, /runs/_; see worker/site.ts) whose route params always say "_", so the real id
 * only exists in the address bar. The bare shell yields "".
 */
export function idFromPath(pathname: string | null, index = 2): string {
  const id = decodeURIComponent((pathname ?? "").split("/")[index] ?? "");
  return id === "_" ? "" : id;
}
