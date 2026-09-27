import { useRef } from 'react';
import { CheckCircle2, Expand, X } from 'lucide-react';
import type { HelpWalkthrough as Walkthrough } from '../lib/help/types';
import { capturesForStep, type HelpCapture } from '../lib/help/visuals';

function StepImage({ capture }: { capture: HelpCapture }) {
  const dialog = useRef<HTMLDialogElement>(null);
  return <figure className="help-step-capture">
    <button className="help-image-open" type="button" onClick={() => dialog.current?.showModal()}
      aria-label={`Enlarge screenshot: ${capture.alt}`}>
      <img src={capture.src} alt={capture.alt} loading="lazy" />
      <span><Expand size={15} aria-hidden="true" /> Enlarge screenshot</span>
    </button>
    <figcaption>{capture.caption}</figcaption>
    <dialog ref={dialog} className="help-image-dialog" aria-label={capture.alt}
      onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
      <button autoFocus className="help-image-close" type="button"
        onClick={() => dialog.current?.close()} aria-label="Close enlarged screenshot"><X size={22}/></button>
      <img src={capture.src} alt={capture.alt} />
      <p>{capture.caption}</p>
    </dialog>
  </figure>;
}

export function HelpWalkthrough({ path, guide }: { path: string; guide: Walkthrough }) {
  return <div className="help-walkthrough">
    <section className="help-callout" aria-labelledby="before-you-start">
      <h2 id="before-you-start">Before you start</h2>
      <ul>{guide.beforeYouStart.map(item => <li key={item}>{item}</li>)}</ul>
    </section>
    <details className="help-step-index" open>
      <summary>In this guide</summary>
      <ol>{guide.steps.map(step => <li key={step.id}><a href={`#${step.id}`}>{step.title}</a></li>)}</ol>
      <a href="#check-your-work">Check your work</a>
      <a href="#help-troubleshooting">Troubleshooting</a>
    </details>
    <div className="help-article-sections help-detailed-steps">
      {guide.steps.map((step, index) => <section id={step.id} key={step.id}>
        <span className="help-section-number">Step {index + 1} of {guide.steps.length}</span>
        <h2>{step.title}</h2>
        {step.warning ? <div className="help-step-warning"><strong>Before you do this</strong><p>{step.warning}</p></div> : null}
        <div className="help-step-instructions">{step.instructions.map((item, n) => <p key={n}>{item}</p>)}</div>
        {step.fields?.length ? <div className="help-fields-wrap">
          <table className="help-fields">
            <caption>What to enter or choose</caption>
            <thead><tr><th scope="col">Field</th><th scope="col">What goes here</th></tr></thead>
            <tbody>{step.fields.map(field => <tr key={field.label}>
              <th scope="row"><span>{field.label}</span><small>{field.requirement}</small></th>
              <td>{field.guidance}{field.example ? <p className="help-field-example"><strong>Example:</strong> {field.example}</p> : null}</td>
            </tr>)}</tbody>
          </table>
        </div> : null}
        {capturesForStep(path, step.id).map(capture => <StepImage key={capture.src} capture={capture}/>)}
        <div className="help-step-result"><CheckCircle2 size={19} aria-hidden="true"/>
          <div><strong>What you should see</strong><p>{step.expected}</p></div>
        </div>
      </section>)}
    </div>
    <section className="help-completion" id="check-your-work">
      <h2>Check your work</h2>
      <ul>{guide.completion.map(item => <li key={item}><CheckCircle2 size={17} aria-hidden="true"/><span>{item}</span></li>)}</ul>
    </section>
    <section className="help-troubleshooting" id="help-troubleshooting">
      <h2>Something not working?</h2>
      {guide.troubleshooting.map(item => <details key={item.symptom}>
        <summary>{item.symptom}</summary><p>{item.resolution}</p>
      </details>)}
    </section>
  </div>;
}
