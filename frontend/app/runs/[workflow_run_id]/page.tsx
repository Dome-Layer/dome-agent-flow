import RunDetailClient from "./RunDetailClient";

// Static export (Sprint H): one prebuilt page serves every workflow run id. The Worker maps
// /runs/<id> to /runs/_ (worker/site.ts), and RunDetailClient reads the id from the URL. Any
// other id 404s at build time, which is why dynamicParams is off.
export const dynamicParams = false;

export function generateStaticParams() {
  return [{ workflow_run_id: "_" }];
}

export default function Page() {
  return <RunDetailClient />;
}
