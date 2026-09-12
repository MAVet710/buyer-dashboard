import { useEffect, useState } from "react";
import {
  ArrowRight,
  Check,
  Factory,
  Layers3,
  Sprout,
  Store,
} from "lucide-react";
import { solutions } from "./content";
import { replaceSolutionHash } from "./solutionNavigation";
import { trackMarketingEvent } from "../../lib/marketingAnalytics";
const icons = [Sprout, Factory, Store, Layers3];

export function Solutions() {
  const [active, setActive] = useState(3);
  useEffect(() => {
    const selectFromHash = () => {
      const index = solutions.findIndex(
        (item) => `#solution-${item.id}` === window.location.hash,
      );
      if (index !== -1) setActive(index);
    };
    selectFromHash();
    window.addEventListener("hashchange", selectFromHash);
    window.addEventListener("popstate", selectFromHash);
    return () => {
      window.removeEventListener("hashchange", selectFromHash);
      window.removeEventListener("popstate", selectFromHash);
    };
  }, []);
  const solution = solutions[active];
  const Icon = icons[active];
  return (
    <section
      className="mh-section mh-container"
      id="solutions"
      aria-labelledby="solutions-heading"
    >
      <div className="mh-section-top">
        <div>
          <span className="mh-eyebrow">02 / Built around your operation</span>
          <h2 id="solutions-heading">
            Same industry.
            <br />
            Different days on the floor.
          </h2>
        </div>
        <p>
          A grow room, a production line and a retail vault need different
          tools. Start with the work your team actually does.
        </p>
      </div>
      <div className="mh-solutions-select" role="group" aria-label="Choose your operation">
        {solutions.map((item, index) => {
          const ItemIcon = icons[index];
          return (
            <button
              id={`solution-${item.id}`}
              aria-pressed={index === active}
              type="button"
              key={item.id}
              onClick={() => {
                setActive(index);
                replaceSolutionHash(item.id, window.history);
                trackMarketingEvent(`solution_${item.id}`, {
                  placement: "solutions",
                });
              }}
            >
              <ItemIcon size={23} />
              <strong>{item.name}</strong>
              <span>{item.short}</span>
              <ArrowRight className="mh-solution-arrow" size={18} />
            </button>
          );
        })}
      </div>
      <div className="mh-solution-detail" aria-live="polite">
        <div>
          <span className="mh-label">BETA WORKFLOWS / {solution.name}</span>
          <h3>{solution.title}</h3>
          <p>{solution.description}</p>
          <a
            className="mh-text-link"
            href="/beta#apply"
            onClick={() =>
              trackMarketingEvent("homepage_primary_cta", {
                placement: "solutions",
                item: solution.id,
              })
            }
          >
            Explore your beta fit <ArrowRight size={17} />
          </a>
        </div>
        <div className="mh-solution-note">
          <Icon size={36} />
          <ul>
            {solution.points.map((point) => (
              <li key={point}>
                <Check size={16} />
                {point}
              </li>
            ))}
          </ul>
          <p>{solution.question}</p>
        </div>
      </div>
    </section>
  );
}
