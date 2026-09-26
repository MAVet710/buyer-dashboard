import { useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { useIntelligence, useIntelligenceWrite } from "./cultivationIntelligenceQueries";
import { historicalWindow, evidenceTimestamp } from "./telemetryReview";

type Deviation = { exception_id: string; metric: string; unit: string; direction: string; started_at: string; ended_at: string; duration_seconds: number; threshold_seconds: number; work_item_id: string | null; return_route: string };
type Evidence = { items: Deviation[]; window: { start: string; end: string }; truncated: boolean; can_create_work?: boolean };
export function ImportedDeviationWork({ roomId, summary, canManage, focus = "" }: { roomId: string; summary: unknown; canManage: boolean; focus?: string }) {
  const window = historicalWindow(summary);
  const [opened, setOpened] = useState(Boolean(focus));
  const path = `/rooms/${encodeURIComponent(roomId)}/deviations`;
  const query = useIntelligence<Evidence>(`${path}?${new URLSearchParams(window)}`, opened && Boolean(window.start && window.end));
  return <section aria-label="Historical deviation Work"><h4>Review historical deviations for Work</h4><p>Only server-confirmed continuous deviations in the selected historical window qualify. Creating Work requires your explicit review.</p><button className="secondary" disabled={!window.start || !window.end || query.isFetching} onClick={() => { setOpened(true); if (opened) void query.refetch(); }}>Review eligible deviations</button>
    {opened && (!window.start || !window.end) && <p>Historical evidence is unavailable. Select a persisted aggregate window.</p>}
    {opened && query.isLoading && <p role="status">Loading historical evidence...</p>}
    {opened && query.isError && <p role="alert">Deviation evidence is unavailable. Refresh the room and try again.</p>}
    {opened && query.data && !query.isError && <>{query.data.truncated ? <p>Evidence is incomplete. Refresh before creating Work.</p> : !query.data.items.length ? <p>No eligible duration-qualified deviations in this window. Missing coverage remains unknown.</p> : query.data.items.map(item => <DeviationReview key={item.exception_id} item={item} path={path} window={query.data.window} canManage={canManage && query.data.can_create_work === true} focused={focus === item.exception_id} refresh={() => { void query.refetch(); }} />)}{focus && !query.data.items.some(item => item.exception_id === focus) && <p role="status">The selected exception is no longer available in this window. Review refreshed evidence.</p>}</>}
  </section>;
}
function DeviationReview({ item, path, window, canManage, focused, refresh }: { item: Deviation; path: string; window: Evidence["window"]; canManage: boolean; focused: boolean; refresh: () => void }) {
  const [reviewing, setReviewing] = useState(false);
  const element = useRef<HTMLElement>(null);
  const save = useIntelligenceWrite<{ work_item_id: string; existing: boolean; return_route: string }>(`${path}/${encodeURIComponent(item.exception_id)}/work`);
  const conflict = save.error instanceof ApiError && save.error.status === 409;
  useEffect(() => { if (focused) element.current?.focus(); }, [focused]);
  const workId = save.data?.work_item_id || item.work_item_id;
  return <article className="ci-stage" ref={element} tabIndex={-1} aria-label={`Deviation ${item.exception_id}`} data-focused={focused || undefined}><h5>{item.metric}: {item.direction}</h5><p>{evidenceTimestamp(item.started_at)} to {evidenceTimestamp(item.ended_at)}. Continuous duration: {item.duration_seconds} seconds. Required duration: {item.threshold_seconds} seconds.</p>
    {workId ? <div className="ci-actions"><a className="secondary" href={`/work?item=${encodeURIComponent(workId)}`}>Open Work</a><a className="secondary" href={save.data?.return_route || item.return_route}>Return to this room exception</a></div> : canManage ? <><button className="secondary" disabled={save.isPending || conflict} onClick={() => setReviewing(true)}>Review Work action</button>{reviewing && <><p>Create one canonical Work item for this historical exception. Existing Work, including completed Work, will be reused.</p><button className="primary" disabled={save.isPending || conflict} onClick={() => save.mutate(window, { onError: failure => { if (failure instanceof ApiError && failure.status === 409) { setReviewing(false); refresh(); } } })}>Create Doobie Work</button></>}</> : <p>Read only. Ask an authorized operator to create Work.</p>}
    {conflict ? <><p role="alert">Evidence changed. Refreshed evidence requires another review.</p><button className="secondary" onClick={() => { save.reset(); setReviewing(false); refresh(); }}>Review refreshed evidence</button></> : save.error ? <p role="alert">{save.error instanceof ApiError && save.error.status === 403 ? "Permission denied. Work was not created." : "Work could not be confirmed. Refresh evidence before retrying."}</p> : null}
  </article>;
}
