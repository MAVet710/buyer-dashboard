from pathlib import Path
import hashlib

root = Path.cwd()
EXPECTED = {'ExtractionUnifiedPage.tsx': 'cb0a1690e005313f6f371f8119b0facd405063b514f332e3092c256857e05795', 'ExtractionOperatorWorkspace.tsx': 'bc2352c9ee31b872d4711897fe6e8469adf4449a18bb92e85b918369ad1a0e72', 'ExtractionPage.tsx': '0a47c0045e07d400c0417a9cfaec3e11ae3e629ceb8e47810bf4d45f7b3e1cdb'}
for name, digest in EXPECTED.items():
    path = root / 'frontend/src/pages' / name
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f'Source changed; reconcile {name} before applying this patch.')

p=root/'frontend/src/pages/ExtractionUnifiedPage.tsx'
s=p.read_text().replace('import { useState } from "react";', 'import { useCallback } from "react";\nimport { useSearchParams } from "react-router-dom";')
s=s.replace('type AdvancedView = "run" | "management";', 'type AdvancedView = "run" | "management" | "board";\ntype AccountContext = { organization?: { id?:string } | null; facility_id?:string; user?: { id?:string } };')
start=s.index('  const [view,setView]')
end=s.index('  const lots=useQuery', start)
s=s[:start]+'''  const context=useQuery({queryKey:["account-context"],queryFn:({signal})=>apiGet<AccountContext>("/api/v1/account/context",signal)});
  if(context.isError)return <div className="state error" role="alert">Facility context is unavailable. Extraction records were not opened.</div>;
  if(!context.data?.organization?.id||!context.data.facility_id)return <div className="state">Loading extraction facility context…</div>;
  const scope=`${context.data.organization.id}:${context.data.facility_id}:${context.data.user?.id??""}`;
  return <ExtractionWorkspace key={scope} scope={scope} onNavigate={onNavigate}/>;
}

function ExtractionWorkspace({scope,onNavigate}:{scope:string;onNavigate:(page:string)=>void}) {
  const [params,setParams]=useSearchParams();
  const requestedView=params.get("extractionView");
  const view:View=requestedView==="runs"||requestedView==="inventory"||requestedView==="analytics"?requestedView:"today";
  const selectedRunId=params.get("extractionRun")??"";
  const requestedPanel=params.get("extractionPanel");
  const advancedOpen=requestedPanel==="run"||requestedPanel==="management"||requestedPanel==="board";
  const advancedView:AdvancedView=requestedPanel==="management"?"management":requestedPanel==="board"?"board":"run";
  const setView=(next:View)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionView",next);return updated;});
  const selectRun=useCallback((id:string,replace=false)=>{
    setParams(previous=>{const updated=new URLSearchParams(previous);if(id)updated.set("extractionRun",id);else updated.delete("extractionRun");return updated;},{replace});
  },[setParams]);
  const setAdvancedView=(next:AdvancedView)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionPanel",next);return updated;});
  const openAdvanced=(runId?:string)=>setParams(previous=>{
    const updated=new URLSearchParams(previous);
    if(runId)updated.set("extractionRun",runId);
    updated.set("extractionPanel",updated.get("extractionRun")?"run":"board");
    return updated;
  });
  const closeAdvanced=()=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.delete("extractionPanel");return updated;});
  const selectAdvancedRun=(id:string)=>setParams(previous=>{const updated=new URLSearchParams(previous);updated.set("extractionRun",id);updated.set("extractionPanel","run");return updated;});
''' + s[end:]
s=s.replace('queryKey:["extraction-eligible-lots"]','queryKey:["extraction-eligible-lots",scope]')
s=s.replace('onClick={openAdvanced}>Advanced Run 360', 'onClick={()=>openAdvanced()}>Advanced Run 360')
s=s.replace('    {view==="today"?<ExtractionOperatorWorkspace mode="today" onOpenAdvanced={openAdvanced}/>:null}\n    {view==="runs"?<ExtractionOperatorWorkspace mode="runs" onOpenAdvanced={openAdvanced}/>:null}', '    {view==="today"||view==="runs"?<ExtractionOperatorWorkspace mode={view} scope={scope} selectedRunId={selectedRunId} onSelectRun={selectRun} onOpenAdvanced={openAdvanced}/>:null}')
s=s.replace('onClose={()=>setAdvancedOpen(false)}','onClose={closeAdvanced}')
s=s.replace('className={advancedView==="run"?"active":""}', 'className={advancedView!=="management"?"active":""}')
s=s.replace('{advancedView==="run"?<ExtractionPage onNavigate={onNavigate}/>', '{advancedView!=="management"?<ExtractionPage scope={scope} selectedRunId={advancedView==="run"?selectedRunId:""} onSelectRun={selectAdvancedRun} onCloseRun={()=>setAdvancedView("board")} onNavigate={onNavigate}/>')
p.write_text(s)
p=root/'frontend/src/pages/ExtractionOperatorWorkspace.tsx'
s=p.read_text().replace('import { useEffect, useMemo, useState }', 'import { useCallback, useEffect, useMemo, useState }')
s=s.replace('export function ExtractionOperatorWorkspace({ mode, onOpenAdvanced }: { mode:OperatorMode; onOpenAdvanced:(runId?:string)=>void }) {', '''export function ExtractionOperatorWorkspace({ mode, onOpenAdvanced, selectedRunId, onSelectRun, scope="" }: {
  mode:OperatorMode; onOpenAdvanced:(runId?:string)=>void; selectedRunId?:string;
  onSelectRun?:(runId:string,replace?:boolean)=>void; scope?:string;
}) {''')
s=s.replace('const [selected, setSelected] = useState("");', 'const [localSelected, setLocalSelected] = useState("");\n  const selected=selectedRunId??localSelected;')
s=s.replace('queryKey:["extraction-runs"]','queryKey:["extraction-runs",scope]',1)
s=s.replace('const detail = useQuery({ queryKey:["extraction-run", selected], enabled:Boolean(selected), queryFn:({signal})=>apiGet<Detail>(`/api/v1/extraction/runs/${selected}`, signal) });', '''const detail = useQuery({ queryKey:["extraction-run", selected, scope], enabled:Boolean(selected), retry:false, staleTime:0, refetchOnMount:"always", refetchOnWindowFocus:false, queryFn:({signal})=>apiGet<Detail>(`/api/v1/extraction/runs/${encodeURIComponent(selected)}`, signal) });
  const wrongRecord=Boolean(detail.data&&detail.data.run.id!==selected);
  const detailUnavailable=detail.isError||wrongRecord;''')
s=s.replace('const selectRun=(runId:string)=>{setSelected(runId);setCreating(false)};\n  const openNewRun=()=>{setSelected("");setCreating(true)};', '''const selectRun=useCallback((runId:string,replace=false)=>{setLocalSelected(runId);onSelectRun?.(runId,replace);setCreating(false)},[onSelectRun]);
  const openNewRun=()=>{setLocalSelected("");onSelectRun?.("");setCreating(true)};''')
s=s.replace('if (preferred) setSelected(preferred.id);','if (preferred) selectRun(preferred.id,true);')
s=s.replace('[attentionRuns, creating, filtered, nextRuns, runningRuns, selected]', '[attentionRuns, creating, filtered, nextRuns, runningRuns, selected, selectRun]')
s=s.replace('{detail.isError ? <div className="state error">{detail.error.message}</div> : null}', '{detailUnavailable ? <div className="state error" role="alert">The requested extraction run could not be opened. No other run was selected in its place. <button className="secondary" type="button" onClick={()=>void detail.refetch()}>Retry requested run</button></div> : null}')
s=s.replace('{detail.data ? <CurrentRun detail={detail.data}', '{selected&&detail.data&&!detailUnavailable ? <CurrentRun key={`${scope}:${selected}`} detail={detail.data}')
p.write_text(s)
p=root/'frontend/src/pages/ExtractionPage.tsx'
s=p.read_text()
s=s.replace('export function ExtractionPage({onNavigate}:{onNavigate?:(page:string)=>void}={}){', '''export function ExtractionPage({onNavigate,selectedRunId,onSelectRun,onCloseRun,scope=""}:{
 onNavigate?:(page:string)=>void;selectedRunId?:string;onSelectRun?:(runId:string)=>void;onCloseRun?:()=>void;scope?:string;
}={}){''')
s=s.replace('const [selected,setSelected]=useState("");', 'const [localSelected,setLocalSelected]=useState("");const selected=selectedRunId??localSelected;const setSelected=(id:string)=>{setLocalSelected(id);onSelectRun?.(id)};')
s=s.replace('queryKey:["extraction-runs"]','queryKey:["extraction-runs",scope]',1)
s=s.replace('queryKey:["extraction-parity-overview"]','queryKey:["extraction-parity-overview",scope]',1)
s=s.replace('const detail=useQuery({queryKey:["extraction-run",selected],enabled:Boolean(selected),queryFn:({signal})=>apiGet<Detail>(`/api/v1/extraction/runs/${selected}`,signal)});', '''const detail=useQuery({queryKey:["extraction-run",selected,scope],enabled:Boolean(selected),retry:false,staleTime:0,refetchOnMount:"always",refetchOnWindowFocus:false,queryFn:({signal})=>apiGet<Detail>(`/api/v1/extraction/runs/${encodeURIComponent(selected)}`,signal)});
 const wrongRecord=Boolean(detail.data&&detail.data.run.id!==selected);
 const detailError=detail.isError||wrongRecord?"The requested extraction run could not be opened. No other run was selected in its place.":"";''')
s=s.replace('<Run360 detail={detail.data} loading={detail.isLoading&&Boolean(selected)} open={Boolean(selected)} onClose={()=>setSelected("")}', '<Run360 key={`${scope}:${selected}`} detail={detailError||detail.isFetching?undefined:detail.data} error={detailError} loading={detail.isFetching&&Boolean(selected)} open={Boolean(selected)} onRetry={()=>void detail.refetch()} onClose={()=>{if(onCloseRun)onCloseRun();else setSelected("")}}')
s=s.replace('function Run360({detail,loading,open,onClose,onSaved,onNavigate}:{detail?:Detail;loading:boolean;open:boolean;onClose:()=>void;onSaved:()=>void;onNavigate?:(page:string)=>void})', 'function Run360({detail,error,loading,open,onClose,onSaved,onNavigate,onRetry}:{detail?:Detail;error?:string;loading:boolean;open:boolean;onClose:()=>void;onSaved:()=>void;onNavigate?:(page:string)=>void;onRetry?:()=>void})')
s=s.replace('title={detail?.run.batch_number??"Run 360"}', 'title={error?"Run unavailable":detail?.run.batch_number??"Run 360"}')
s=s.replace('subtitle={detail?', 'subtitle={error?"The saved run link was retained. Retry it or close this view.":detail?')
s=s.replace('{loading||!detail?<div className="state">Loading durable run context…</div>:<>', '{error?<div className="state error" role="alert">{error}<button className="secondary" type="button" onClick={onRetry}>Retry requested run</button></div>:loading||!detail?<div className="state">Loading durable run context…</div>:<>')
p.write_text(s)
EXPECTED_OUTPUT = {'ExtractionUnifiedPage.tsx': '1f96eb45dcc0ad6cf9e9f60eb9ee66b05bde1de70cdef4af0fa8dd48c77077f2', 'ExtractionOperatorWorkspace.tsx': '9a822a65e259942dc528146779d789272439427e834d98c2e0a674b8b2a399c5', 'ExtractionPage.tsx': '297a531bffe995b50d7ceba0eb4990d8dbac46dda5441f79b6281deebc265bac'}
for name, digest in EXPECTED_OUTPUT.items():
    if hashlib.sha256((root/'frontend/src/pages'/name).read_bytes()).hexdigest()!=digest:
        raise SystemExit(f'Patch output differs from reviewed candidate: {name}')
print('Verified all three exact candidate source hashes.')
